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

    n_eq = len(s.equities)
    fit = "" if TARGET_MIN_POSITIONS <= n_eq <= TARGET_MAX_POSITIONS else "  <- fuera del objetivo"
    print(f"Acciones:         {n_eq} (objetivo Carlson: "
          f"{TARGET_MIN_POSITIONS}-{TARGET_MAX_POSITIONS}){fit}")
    print(f"ETFs:             {len(s.etfs)} (no cuentan para la concentracion)")

    if not s.positions:
        print("\nSin posiciones.")
        return 0

    def line(p, mark_limit: bool) -> str:
        w = s.weight_at_cost(p.ticker)
        flags = []
        if mark_limit and w > MAX_POSITION_AT_COST:
            flags.append("EXCEDE 15% AL COSTO")
        if p.gain_pct <= -20:
            flags.append("REVISION DE TESIS OBLIGATORIA (-20%)")
        suffix = "  [" + " | ".join(flags) + "]" if flags else ""
        return (
            f"  {p.ticker:6} {w:5.1%} costo | {p.quantity:>9.4f} @ ${p.avg_cost:8.2f} "
            f"-> ${p.price:8.2f}  {p.gain_pct:+7.2f}%  ${p.market_value:>9,.2f}{suffix}"
        )

    if s.equities:
        print("\nAcciones (sujetas al limite de 15% al costo):")
        for p in sorted(s.equities, key=lambda x: -x.cost_basis):
            print(line(p, mark_limit=True))

    if s.etfs:
        print("\nETFs (el limite de 15% no aplica — ya son canastas diversificadas):")
        for p in sorted(s.etfs, key=lambda x: -x.cost_basis):
            print(line(p, mark_limit=False))

    over_limit = [p.ticker for p in s.equities if s.weight_at_cost(p.ticker) > MAX_POSITION_AT_COST]
    if over_limit:
        print(f"\nAcciones sobre el limite de 15% al costo: {', '.join(over_limit)}")

    review = [p.ticker for p in s.positions if p.gain_pct <= -20]
    if review:
        print(f"Posiciones que exigen revision de tesis (-20% o peor): {', '.join(review)}")

    if n_eq >= TARGET_MAX_POSITIONS:
        from src.data.portfolio_csv import to_validator_state
        from src.guardrails.validator import substitution_candidates

        print(f"\n{'=' * 66}")
        print(f"CARTERA LLENA ({n_eq}/{TARGET_MAX_POSITIONS} acciones)")
        print("=" * 66)
        print("Agregar un nombre nuevo exige sacar otro. Eso no es un techo: es lo que")
        print("hace que cada lugar sea escaso y haya que ganarselo.\n")
        print("Candidatas a ceder su lugar — punto de partida, no veredicto:")
        for p, reason in substitution_candidates(to_validator_state(s)):
            print(f"  {p.ticker:6} {reason}")
        print("\nLa pregunta no es 'cual esta peor' sino '¿la candidata nueva es mejor")
        print("negocio que esta posicion?'. Si la respuesta es no, no hay sustitucion.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
