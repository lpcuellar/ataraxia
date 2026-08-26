#!/usr/bin/env python3
"""
Resumen diario para el humano — arquitectura "mimetizar a The Claude Portfolio de cerca"
(ver el review de arquitectura): el brain (Cowork/Routine) investiga y escribe propuestas
guardrail-aprobadas a `decisions`; el humano las lee ACA, decide, y ejecuta a mano en IBKR.
No ejecuta nada — es de solo lectura.

No reemplaza al brain en si: el brain es la sesion de Claude Code programada siguiendo
src/agent/prompt.py, no un daemon Python (src/agent/loop.py y tools.py, el scaffold viejo
para eso, se eliminaron — ver BUILD_PLAN.md, quedaron obsoletos con el pivote a Cowork).
Este script es el reporte que consultas despues de que el brain corrio.

Uso:
    python scripts/run_daily.py

Despues de ejecutar algo a mano en IBKR, registralo con:
    python scripts/log_manual_trade.py fill --ticker X --action buy --quantity N --price P \\
        --decision-id <el id que se muestra aca>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import models as db  # noqa: E402
from src.guardrails import validator as v  # noqa: E402
from src.reporting.portfolio import build_portfolio_state  # noqa: E402


def main():
    proposals = db.get_pending_proposals()
    portfolio = build_portfolio_state()
    flagged_live = v.check_thesis_review_triggers(portfolio)

    print(f"Ataraxia — resumen del dia ({len(portfolio.positions)} posiciones, "
          f"${portfolio.cash:,.2f} cash, ${portfolio.total_value:,.2f} valor de mercado)\n")

    if not proposals and not flagged_live:
        print("Sin propuestas pendientes y ninguna posicion en revision obligatoria de "
              "tesis. Nada que hacer hoy — eso esta bien.")
        return

    if proposals:
        print(f"=== Propuestas pendientes de tu decision ({len(proposals)}) ===\n")
        for p in proposals:
            print(f"[#{p['id']}] {p['action'].upper()} {p['quantity']} {p['ticker']} @ ~{p['price']}")
            print(f"  Rationale: {p['rationale']}")
            if p.get("bear_case"):
                prob = p.get("bear_case_probability")
                prob_str = f"{prob:.0%}" if prob is not None else "?"
                print(f"  Bear case ({prob_str}): {p['bear_case']}")
            print()
        print("Si ejecutas alguna a mano en IBKR, registrala con "
              "scripts/log_manual_trade.py fill --decision-id <id>.\n")

    if flagged_live:
        trigger_label = f"{v.THESIS_REVIEW_TRIGGER_PCT:.0%} o peor desde costo"
        print(f"=== Posiciones en revision obligatoria de tesis ({trigger_label}) ===\n")
        for ticker in flagged_live:
            pos = portfolio.get_position(ticker)
            print(f"  {ticker}: {pos.unrealized_return_pct:.1%} desde costo "
                  f"(${pos.avg_cost:.2f} -> ${pos.current_price:.2f})")
        print("\nEsto no vende nada automaticamente — es la obligacion de volver a "
              "justificar la tesis explicitamente (ver PROJECT_PLAN.md Seccion 1).\n")


if __name__ == "__main__":
    main()
