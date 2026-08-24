#!/usr/bin/env python3
"""
Calcula el snapshot de performance de hoy (alpha vs. S&P 500, Sharpe, drawdown) y lo guarda
en la tabla `performance`. Correrlo una vez por dia (despues de que cualquier fill del dia
ya este registrado via scripts/log_manual_trade.py) para construir el historico que
alimenta la metrica de exito principal del proyecto (PROJECT_PLAN.md Seccion 1).

Uso:
    python scripts/compute_performance.py            # calcula y guarda
    python scripts/compute_performance.py --dry-run  # calcula e imprime, no guarda
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import models as db  # noqa: E402
from src.reporting.performance import compute_daily_snapshot  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    snapshot = compute_daily_snapshot()

    alpha = snapshot["cumulative_return_pct"] - snapshot["sp500_cumulative_return_pct"]
    print(f"Fecha: {snapshot['date']}")
    print(f"Valor del fondo: ${snapshot['fund_value']:,.2f}")
    print(f"Equivalente S&P 500: ${snapshot['sp500_equivalent_value']:,.2f}")
    print(f"Retorno acumulado — fondo: {snapshot['cumulative_return_pct']:.2%}  "
          f"S&P 500: {snapshot['sp500_cumulative_return_pct']:.2%}  "
          f"Alpha: {alpha:+.2%}")
    print(f"Drawdown actual: {snapshot['current_drawdown_pct']:.2%}  "
          f"Maximo: {snapshot['max_drawdown_pct']:.2%}")
    sharpe = snapshot["sharpe_ratio"]
    print(f"Sharpe ratio: {sharpe:.2f}" if sharpe is not None
          else "Sharpe ratio: N/A (todavia no hay suficiente historico)")

    if args.dry_run:
        print("\n[dry-run] no se guardo.")
        return

    db.log_performance_snapshot(**snapshot)
    print("\nGuardado en la tabla performance.")


if __name__ == "__main__":
    main()
