#!/usr/bin/env python3
"""
Encola candidatos para analisis profundo, desde noticias (source='noticia') o desde los
nombres que LP propone (source='interes_lp').

Es la pieza que faltaba del embudo: candidate_queue admite source='noticia' desde la
migracion del rediseño Carlson, pero ningun codigo la producia. brain_candidates.py cubre
rotacion_universo, portafolio y watchlist; este script cubre las otras dos entradas.

Quien lo usa:
  - La automation "Ataraxia — barrido diario de noticias" (5:45 L-V) con --source noticia.
  - LP, a mano, con --source interes_lp, para meter nombres que le interesan o que le vayan
    sonando. El reporte de lun/mie consume la cola de a 2-3 nombres.

Por que un script y no que el agente escriba SQL: la cola tiene un unique (ticker, status) y
una semantica de prioridad que conviene aplicar en un solo lugar. Ademas asi el encolado
queda auditable y el agente no necesita credenciales de escritura arbitraria.

Sobre el sesgo de los nombres propuestos por LP — vale tenerlo presente:
PROJECT_PLAN.md descarto explicitamente "una watchlist de 30-50 tickers curada a mano" porque
"introduce sesgo real hacia nombres ya populares/eficientemente valuados, lo opuesto a lo que
esta estrategia busca". Eso sigue siendo cierto. La diferencia es que aca los nombres de LP
NO reemplazan el embudo cuantitativo: son una fuente mas, y la rotacion del universo sigue
corriendo como contrapeso para que el agente mire ocasionalmente empresas que nadie le
sugirio. Si la cola se llena solo de interes_lp y la rotacion nunca llega a consumirse, el
sesgo volvio por la puerta de atras — eso es lo que hay que vigilar, no el mecanismo en si.

Un nombre propuesto por LP entra al EMBUDO, no a la cartera: pasa las mismas tres etapas y se
descarta igual que cualquier otro si falla Etapa 1.

Uso:
    # un nombre que a LP le interesa
    venv/bin/python scripts/enqueue_news_candidate.py --source interes_lp \
        --ticker ASML \
        --reason "Monopolio de litografia EUV; quiero saber si el foso aguanta la
                  desaceleracion de capex de los fabs"

    # desde el barrido de noticias
    venv/bin/python scripts/enqueue_news_candidate.py --ticker ASML \
        --reason "Guidance recortado por retraso de High-NA; el mercado leyo deterioro
                  estructural pero el backlog no se movio" \
        --url https://...

    # varios de una, leyendo JSON de stdin
    echo '[{"ticker":"ASML","reason":"...","url":"..."}]' | \
        venv/bin/python scripts/enqueue_news_candidate.py --stdin

El motivo NO es el titular ni "me suena". Es por que vale la pena gastar un ciclo de research
en esta empresa. Un encolado cuyo motivo no dice nada no sirve: el reporte despues no sabe
que estaba buscando.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import carlson as k  # noqa: E402

# Prioridades en la cola. Referencia de brain_candidates.py: watchlist-a-precio 100,
# revision de portafolio 90, rotacion del universo 10.
#
# interes_lp (70) va por encima de noticia (60) porque es una peticion explicita del humano
# que decide, pero por debajo del portafolio propio: revisar una tesis abierta que se esta
# rompiendo es mas urgente que estrenar una idea nueva. Ninguna de las dos pasa por encima de
# una empresa de la watchlist que llego a su precio objetivo — esa es la unica que tiene una
# ventana que se puede cerrar.
PRIORITY_NEWS = 60
PRIORITY_LP_INTEREST = 70

SOURCE_PRIORITY = {
    "noticia": PRIORITY_NEWS,
    "interes_lp": PRIORITY_LP_INTEREST,
}

MIN_REASON_CHARS = 40
_TICKER_RE = re.compile(r"\A[A-Z][A-Z.\-]{0,5}\Z")


def _validate(ticker: str, reason: str) -> str | None:
    """Devuelve el mensaje de error, o None si esta bien."""
    ticker = ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        return f"{ticker!r} no parece un ticker valido"
    reason = " ".join(reason.split())
    if len(reason) < MIN_REASON_CHARS:
        return (
            f"el motivo de {ticker} tiene {len(reason)} caracteres y se piden al menos "
            f"{MIN_REASON_CHARS}. El motivo no es el titular ni \"me suena\": es por que vale "
            f"la pena gastar un ciclo de research en esta empresa."
        )
    return None


def _enqueue(ticker: str, reason: str, url: str | None, priority: int,
             source: str, dry_run: bool) -> bool:
    ticker = ticker.strip().upper()
    reason = " ".join(reason.split())

    problem = _validate(ticker, reason)
    if problem:
        print(f"RECHAZADO — {problem}", file=sys.stderr)
        return False

    if dry_run:
        print(f"[dry-run] {ticker} ({source}, prioridad {priority}): {reason[:80]}")
        return True

    k.enqueue_candidate(
        ticker=ticker,
        source=source,
        reason=reason,
        url=url,
        priority=priority,
    )
    print(f"OK — {ticker} encolado ({source}, prioridad {priority})")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ticker")
    ap.add_argument("--reason")
    ap.add_argument("--url", default=None)
    ap.add_argument("--source", choices=sorted(SOURCE_PRIORITY), default="noticia",
                    help="noticia (barrido diario) o interes_lp (nombre propuesto por LP)")
    ap.add_argument("--priority", type=int, default=None,
                    help="Sobrescribe la prioridad por defecto del origen")
    ap.add_argument("--stdin", action="store_true",
                    help="Lee una lista JSON de {ticker, reason, url?, source?} de stdin")
    ap.add_argument("--dry-run", action="store_true", help="Valida sin escribir en la DB")
    ap.add_argument("--show", action="store_true", help="Muestra la cola pendiente y sale")
    args = ap.parse_args()

    if args.show:
        queue = k.get_queue(limit=25)
        if not queue:
            print("Cola vacia.")
            return 0
        for row in queue:
            print(f"[{row['priority']:>3}] {row['ticker']:<6} {row['source']:<18} "
                  f"{row['reason'][:70]}")
        return 0

    items: list[dict]
    if args.stdin:
        try:
            items = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            print(f"ERROR: stdin no es JSON valido: {exc}", file=sys.stderr)
            return 1
        if not isinstance(items, list):
            print("ERROR: se esperaba una lista JSON", file=sys.stderr)
            return 1
    else:
        if not args.ticker or not args.reason:
            ap.error("hacen falta --ticker y --reason (o --stdin)")
        items = [{"ticker": args.ticker, "reason": args.reason, "url": args.url}]

    ok = 0
    for item in items:
        source = item.get("source") or args.source
        if source not in SOURCE_PRIORITY:
            print(f"RECHAZADO — origen {source!r} no reconocido; usa uno de "
                  f"{sorted(SOURCE_PRIORITY)}", file=sys.stderr)
            continue
        # Prioridad: la del item, si no la del flag, si no la que corresponde al origen.
        priority = item.get("priority") or args.priority or SOURCE_PRIORITY[source]
        if _enqueue(
            ticker=item.get("ticker", ""),
            reason=item.get("reason", ""),
            url=item.get("url"),
            priority=int(priority),
            source=source,
            dry_run=args.dry_run,
        ):
            ok += 1

    failed = len(items) - ok
    print(f"\n{ok} encolado(s)" + (f", {failed} rechazado(s)" if failed else ""))
    # Exito parcial no es exito: si algo se rechazo, el agente tiene que verlo.
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
