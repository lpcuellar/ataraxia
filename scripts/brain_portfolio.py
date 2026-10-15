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
    load_latest,
)
from src.guardrails.validator import MAX_POSITION_PCT  # noqa: E402

# Concentracion Carlson. MAX_POSITION_PCT se importa del validator en vez de duplicarse aca:
# un numero repetido en dos archivos es un numero que se desincroniza, que es justo lo que
# paso con el 15% viejo cuando el limite subio a 25% y este archivo se quedo atras.
TARGET_MIN_POSITIONS = 8
TARGET_MAX_POSITIONS = 15


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", help="CSV especifico; por defecto el snapshot de la DB")
    ap.add_argument("--no-db", action="store_true",
                    help="Ignora la DB y lee el CSV mas reciente de data/")
    args = ap.parse_args()

    try:
        s = load_latest(
            Path(args.file) if args.file else None,
            prefer_db=not args.no_db,
        )
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

    def line(p, is_equity: bool) -> str:
        flags = []
        if p.gain_pct <= -20:
            flags.append("REVISION DE TESIS OBLIGATORIA (-20%)")
        # weight_at_cost/weight_at_market se definen sobre equity_cost_basis/
        # equity_market_value (sin ETFs), asi que para un ETF siempre darian 0% — un numero
        # que parece bug en vez de "no aplica". Se omiten ambas columnas para ETFs.
        if is_equity:
            w_cost = s.weight_at_cost(p.ticker)
            if w_cost > MAX_POSITION_PCT:
                flags.append(f"EXCEDE {MAX_POSITION_PCT:.0%} AL COSTO")
            cost_txt = f"{w_cost:5.1%} costo"
            mkt_txt = f"{s.weight_at_market(p.ticker):5.1%} mcdo"
        else:
            cost_txt = "   n/a      "
            mkt_txt = "  n/a"
        suffix = "  [" + " | ".join(flags) + "]" if flags else ""
        return (
            f"  {p.ticker:6} {cost_txt} | {mkt_txt} | {p.quantity:>9.4f} "
            f"@ ${p.avg_cost:8.2f} -> ${p.price:8.2f}  {p.gain_pct:+7.2f}%  "
            f"${p.market_value:>9,.2f}{suffix}"
        )

    if s.equities:
        print(f"\nAcciones (sujetas al tope de {MAX_POSITION_PCT:.0%} al costo; el peso a "
              "mercado es solo informativo, no bloquea nada):")
        for p in sorted(s.equities, key=lambda x: -x.cost_basis):
            print(line(p, is_equity=True))

    if s.etfs:
        print(f"\nETFs (el tope de {MAX_POSITION_PCT:.0%} no aplica — ya son canastas diversificadas):")
        for p in sorted(s.etfs, key=lambda x: -x.cost_basis):
            print(line(p, is_equity=False))

    over_limit = [p.ticker for p in s.equities if s.weight_at_cost(p.ticker) > MAX_POSITION_PCT]
    if over_limit:
        print(f"\nAcciones sobre el tope de {MAX_POSITION_PCT:.0%} al costo: {', '.join(over_limit)}")

    # Informativo, no un guardrail: solo senala cuando el peso a mercado se aleja bastante
    # del peso al costo, que es la situacion que motivo agregar esta columna (GOOG al costo
    # 10.2%, a mercado ~17% por apreciacion, sin haberse comprado nada de mas).
    diverging = [
        p.ticker for p in s.equities
        if s.weight_at_market(p.ticker) - s.weight_at_cost(p.ticker) > 0.05
    ]
    if diverging:
        print(f"Peso a mercado bastante arriba del costo (+5pp o mas): {', '.join(diverging)} "
              "— no bloquea, es la plata real concentrandose por apreciacion")

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
