#!/usr/bin/env python3
"""
Estado actual del portafolio — primer paso del ciclo diario del brain (ver src/agent/prompt.py,
paso 1: "Revision diaria de posiciones existentes"). Invocado por bash desde la sesion
programada de Cowork/Routine, no pensado para uso interactivo (aunque funciona igual).

Solo lectura — nunca escribe. La verdad viene de executed_trades/cash_events (ver
src/reporting/portfolio.build_portfolio_state), nunca de lo que el brain crea recordar.

Uso:
    python scripts/brain_portfolio.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.guardrails import validator as v  # noqa: E402
from src.reporting.portfolio import build_portfolio_state  # noqa: E402


def main():
    portfolio = build_portfolio_state()

    print(f"Cash: ${portfolio.cash:,.2f}")
    print(f"Valor total (mercado): ${portfolio.total_value:,.2f}")
    print(f"Valor total (costo): ${portfolio.total_cost_basis:,.2f}")
    print(f"Posiciones: {len(portfolio.positions)} "
          f"(objetivo: {v.TARGET_MIN_POSITIONS}-{v.TARGET_MAX_POSITIONS})\n")

    if not portfolio.positions:
        print("Sin posiciones abiertas.")
    else:
        for p in sorted(portfolio.positions, key=lambda p: p.ticker):
            pct_at_cost = (p.cost_basis / portfolio.total_cost_basis * 100
                           if portfolio.total_cost_basis else 0.0)
            flag = " [REVISION DE TESIS OBLIGATORIA]" if p.ticker in portfolio.flagged_for_review else ""
            print(
                f"  {p.ticker}: {p.quantity:g} @ ${p.avg_cost:.2f} costo -> ${p.current_price:.2f} "
                f"actual ({p.unrealized_return_pct:+.1%}), {pct_at_cost:.1f}% de cartera al costo"
                f"{flag}"
            )

    if portfolio.todays_trades:
        print("\nOperaciones ya registradas hoy (no operar el mismo ticker en sentido contrario):")
        for t in portfolio.todays_trades:
            print(f"  {t['ticker']}: {t['action']}")


if __name__ == "__main__":
    main()
