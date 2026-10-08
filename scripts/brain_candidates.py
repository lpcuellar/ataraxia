#!/usr/bin/env python3
"""
Alimenta la cola de candidatos — parte del barrido, no del reporte.

Cambio respecto al diseño anterior: antes devolvia un lote de ~18 tickers que el ciclo
analizaba de corrido. Eso producia 18 revisiones superficiales y ciclos de 60+ minutos
que terminaban en timeout.

Ahora encola candidatos en candidate_queue y el reporte de lun/mie consume solo 2-3 para
analizar a fondo. La profundidad de la Etapa 1 (foso con evidencia, durabilidad como
derivada, caso del atacante) no es compatible con cubrir 18 empresas por ciclo.

Fuentes de candidatos:
  rotacion_universo — el lote rotativo del S&P 500, para cobertura sistematica
  portafolio        — posiciones propias que exigen revision (-20%, o tesis vieja)
  watchlist         — empresas de la lista que llegaron a precio objetivo

Uso:
    python scripts/brain_candidates.py                 # encola de todas las fuentes
    python scripts/brain_candidates.py --source rotacion_universo
    python scripts/brain_candidates.py --show          # solo muestra la cola
    python scripts/brain_candidates.py --batch-size 6
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import universe  # noqa: E402
from src.data.portfolio_csv import load_snapshot  # noqa: E402
from src.db import carlson as k  # noqa: E402

# Cuantos del universo se encolan por corrida. Chico a proposito: la cola se consume
# de a 2-3 por reporte, asi que encolar 18 solo acumula trabajo que envejece.
DEFAULT_BATCH = 6

# Prioridades: lo propio y lo que llego a precio van antes que la exploracion.
PRIORITY_WATCHLIST_AT_TARGET = 100
PRIORITY_PORTFOLIO_REVIEW = 90
PRIORITY_UNIVERSE = 10


def _price(ticker: str) -> float | None:
    try:
        from src.data.market import get_price

        return get_price(ticker)
    except Exception:
        return None


def from_watchlist() -> int:
    """Empresas de la watchlist que llegaron a precio objetivo."""
    n = 0
    for row in k.get_watchlist():
        target = row.get("target_price")
        if target is None:
            continue
        p = _price(row["ticker"])
        if p is None:
            continue
        if p <= float(target):
            k.enqueue_candidate(
                row["ticker"],
                source="watchlist",
                reason=(
                    f"Llego a precio objetivo: ${p:,.2f} <= ${float(target):,.2f}. "
                    f"Gatillo: {row['what_needs_to_happen']}. "
                    "Verificar que la tesis de negocio siga intacta antes de recomendar."
                ),
                priority=PRIORITY_WATCHLIST_AT_TARGET,
            )
            print(f"  [watchlist] {row['ticker']}: ${p:,.2f} <= objetivo ${float(target):,.2f}")
            n += 1
    return n


def from_portfolio() -> int:
    """Posiciones propias que exigen revision de tesis."""
    try:
        s = load_snapshot()
    except FileNotFoundError:
        print("  [portafolio] sin CSV — se omite")
        return 0

    n = 0
    for p in s.positions:
        if p.gain_pct <= -20:
            k.enqueue_candidate(
                p.ticker,
                source="portafolio",
                reason=(
                    f"Cayo {p.gain_pct:.1f}% desde costo — el guardrail exige volver a "
                    "justificar la tesis explicitamente. No es venta automatica."
                ),
                priority=PRIORITY_PORTFOLIO_REVIEW,
            )
            print(f"  [portafolio] {p.ticker}: {p.gain_pct:+.1f}% — revision obligatoria")
            n += 1

    if s.is_stale:
        print(f"  [portafolio] AVISO: snapshot de hace {s.age_days} dias. Pedir CSV nuevo a LP.")
    return n


def from_universe(batch_size: int) -> int:
    """El lote rotativo del S&P 500 — cobertura sistematica del universo."""
    batch = universe.get_weekly_batch()
    if not batch:
        print("  [universo] sin candidatos nuevos en este lote")
        return 0

    taken = batch[:batch_size]
    for t in taken:
        k.enqueue_candidate(
            t,
            source="rotacion_universo",
            reason="Rotacion sistematica del universo S&P 500",
            priority=PRIORITY_UNIVERSE,
        )
    print(f"  [universo] encolados {len(taken)} de {len(batch)}: {', '.join(taken)}")
    if len(batch) > batch_size:
        print(f"             ({len(batch) - len(taken)} quedan fuera — la rotacion ya avanzo)")
    return len(taken)


def show_queue() -> int:
    q = k.get_queue(limit=50)
    if not q:
        print("Cola vacia.")
        return 0
    print(f"Cola de candidatos — {len(q)} pendiente(s), por prioridad:\n")
    for c in q:
        print(f"  [{c['priority']:>3}] {c['ticker']:6} ({c['source']})")
        print(f"        {c['reason']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="Solo muestra la cola, no encola")
    ap.add_argument("--source", choices=["watchlist", "portafolio", "rotacion_universo"],
                    help="Encola solo de esta fuente")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                    help=f"Cuantos del universo encolar (default {DEFAULT_BATCH})")
    args = ap.parse_args()

    if args.show:
        return show_queue()

    total = 0
    print("Encolando candidatos:\n")

    if args.source in (None, "watchlist"):
        total += from_watchlist()
    if args.source in (None, "portafolio"):
        total += from_portfolio()
    if args.source in (None, "rotacion_universo"):
        total += from_universe(args.batch_size)

    print(f"\n{total} candidato(s) encolado(s).")
    pending = len(k.get_queue(limit=200))
    print(f"Cola pendiente total: {pending}")
    if pending > 20:
        print("\nAVISO: la cola esta larga. Se consume de a 2-3 por reporte, asi que")
        print("encolar mas solo acumula trabajo que envejece.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
