#!/usr/bin/env python3
"""
Estado actual del portafolio real de LP — primer paso de cada ciclo.

Lee el CSV mas reciente que LP exporto de Schwab (data/portfolio-YYYY-MM-DD.csv).
Solo lectura, nunca escribe.

Si el snapshot esta viejo lo dice explicitamente: una tesis sobre un portafolio
desactualizado es peor que ninguna.

Uso:
    python scripts/brain_portfolio.py
    python scripts/brain_portfolio.py --file data/portfolio-2026-09-24.csv
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.portfolio_csv import (  # noqa: E402
    STALE_AFTER_DAYS,
    load_snapshot,
)

# Concentracion Carlson. El validator mantiene el limite duro de 15% al costo.
TARGET_MIN_POSITIONS = 8
TARGET_MAX_POSITIONS = 15
MAX_POSITION_AT_COST = 0.15


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", help="CSV especifico; por defecto el mas reciente de data/")
    args = ap.parse_args()

    try:
        s = load_snapshot(Path(args.file) if args.file else None)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"Portafolio al {s.as_of} (fuente: {s.source_file.name}, {s.age_days} dias)")
    if s.is_stale:
        print(
            f"\n  *** SNAPSHOT VIEJO: {s.age_days} dias (umbral: {STALE_AFTER_DAYS}). "
            "Decilo explicitamente en el reporte y pedile a LP un export nuevo. ***\n"
        )

    print(f"\nValor de mercado: ${s.total_market_value:,.2f}")
    print(f"Costo:            ${s.total_cost_basis:,.2f}")
    print(f"Ganancia:         ${s.total_gain_usd:,.2f} ({s.total_gain_pct:+.2%})")
    print(f"Cash:             ${s.cash:,.2f}")

    n = len(s.positions)
    fit = "" if TARGET_MIN_POSITIONS <= n <= TARGET_MAX_POSITIONS else "  <- fuera del objetivo"
    print(f"Posiciones:       {n} (objetivo Carlson: "
          f"{TARGET_MIN_POSITIONS}-{TARGET_MAX_POSITIONS}){fit}")

    if not s.positions:
        print("\nSin posiciones.")
        return 0

    print("\nPosiciones por peso al costo:")
    over_limit = []
    for p in sorted(s.positions, key=lambda x: -x.cost_basis):
        w = s.weight_at_cost(p.ticker)
        flags = []
        if w > MAX_POSITION_AT_COST:
            flags.append("EXCEDE 15% AL COSTO")
            over_limit.append(p.ticker)
        if p.gain_pct <= -20:
            flags.append("REVISION DE TESIS OBLIGATORIA (-20%)")
        suffix = "  [" + " | ".join(flags) + "]" if flags else ""
        print(
            f"  {p.ticker:6} {w:5.1%} costo | {p.quantity:>9.4f} @ ${p.avg_cost:8.2f} "
            f"-> ${p.price:8.2f}  {p.gain_pct:+7.2f}%  ${p.market_value:>9,.2f}{suffix}"
        )

    if over_limit:
        print(f"\nPosiciones sobre el limite de 15% al costo: {', '.join(over_limit)}")

    review = [p.ticker for p in s.positions if p.gain_pct <= -20]
    if review:
        print(f"Posiciones que exigen revision de tesis (-20% o peor): {', '.join(review)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
