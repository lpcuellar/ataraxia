#!/usr/bin/env python3
"""
Encola un candidato originado en una noticia (source='noticia').

Es la pieza que faltaba del embudo: candidate_queue admite source='noticia' desde la
migracion del rediseño Carlson, pero ningun codigo la producia. brain_candidates.py cubre
rotacion_universo, portafolio y watchlist; este script cubre el barrido diario de noticias.

Lo usa la automation "Ataraxia — barrido diario de noticias" (6:00 L-V): el agente lee
noticias, decide que amerita analisis profundo, y encola. El reporte de lun/mie consume la
cola de a 2-3 nombres.

Por que un script y no que el agente escriba SQL: la cola tiene un unique (ticker, status) y
una semantica de prioridad que conviene aplicar en un solo lugar. Ademas asi el encolado
queda auditable y el agente no necesita credenciales de escritura arbitraria.

Uso:
    venv/bin/python scripts/enqueue_news_candidate.py \
        --ticker ASML \
        --reason "Guidance recortado por retraso de High-NA; el mercado leyo deterioro
                  estructural pero el backlog no se movio" \
        --url https://...

    # varios de una, leyendo JSON de stdin
    echo '[{"ticker":"ASML","reason":"...","url":"..."}]' | \
        venv/bin/python scripts/enqueue_news_candidate.py --stdin

El motivo NO es el titular. Es por que el titular podria implicar una brecha entre precio y
negocio. Un encolado cuyo motivo solo repite la noticia no sirve: el reporte despues no
sabe que estaba buscando.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import carlson as k  # noqa: E402

# Prioridad de las noticias en la cola. Por debajo de watchlist-a-precio (100) y de las
# revisiones del propio portafolio: una noticia es una hipotesis, no una obligacion.
PRIORITY_NEWS = 60

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
            f"{MIN_REASON_CHARS}. El motivo no es el titular: es por que el titular podria "
            f"implicar una brecha entre precio y negocio."
        )
    return None


def _enqueue(ticker: str, reason: str, url: str | None, priority: int, dry_run: bool) -> bool:
    ticker = ticker.strip().upper()
    reason = " ".join(reason.split())

    problem = _validate(ticker, reason)
    if problem:
        print(f"RECHAZADO — {problem}", file=sys.stderr)
        return False

    if dry_run:
        print(f"[dry-run] {ticker} (prioridad {priority}): {reason[:90]}")
        return True

    k.enqueue_candidate(
        ticker=ticker,
        source="noticia",
        reason=reason,
        url=url,
        priority=priority,
    )
    print(f"OK — {ticker} encolado (prioridad {priority})")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ticker")
    ap.add_argument("--reason")
    ap.add_argument("--url", default=None)
    ap.add_argument("--priority", type=int, default=PRIORITY_NEWS)
    ap.add_argument("--stdin", action="store_true",
                    help="Lee una lista JSON de {ticker, reason, url?} de stdin")
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
        if _enqueue(
            ticker=item.get("ticker", ""),
            reason=item.get("reason", ""),
            url=item.get("url"),
            priority=int(item.get("priority", args.priority)),
            dry_run=args.dry_run,
        ):
            ok += 1

    failed = len(items) - ok
    print(f"\n{ok} encolado(s)" + (f", {failed} rechazado(s)" if failed else ""))
    # Exito parcial no es exito: si algo se rechazo, el agente tiene que verlo.
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
