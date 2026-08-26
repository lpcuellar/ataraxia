#!/usr/bin/env python3
"""
Datos fundamentales de uno o mas tickers — insumo del framework de screening (ver
src/agent/prompt.py, paso 3). Invocado por bash desde la sesion programada de Cowork/Routine
para cada ticker en revision (posiciones existentes o candidatos del lote de la semana).

No reemplaza la investigacion cualitativa (noticias, guidance, moat) — eso lo hace el brain
via web search por su cuenta. Esto solo trae los numeros: precio, multiplos de valuation,
margenes/eficiencia, y estimados de analistas (proxy de backlog/visibilidad cuando la empresa
no da guidance explicito).

Uso:
    python scripts/brain_fundamentals.py AAPL
    python scripts/brain_fundamentals.py AAPL MSFT NVDA
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import fundamentals, market  # noqa: E402


def _fmt(value, pct=False):
    if value is None:
        return "N/D"
    if pct:
        return f"{value:.1%}" if isinstance(value, (int, float)) else str(value)
    return f"{value:,.2f}" if isinstance(value, (int, float)) else str(value)


def print_ticker(ticker: str):
    price = market.get_price(ticker)
    key_metrics = fundamentals.get_key_metrics(ticker)
    ratios = fundamentals.get_ratios(ticker)
    estimates = fundamentals.get_analyst_estimates(ticker, limit=3)

    print(f"=== {ticker} ===")
    print(f"Precio actual: ${_fmt(price)}")

    if ratios:
        print("Multiplos de valuation:")
        print(f"  P/E: {_fmt(ratios.get('priceToEarningsRatio'))}  "
              f"P/S: {_fmt(ratios.get('priceToSalesRatio'))}  "
              f"ROIC: {_fmt(key_metrics.get('returnOnInvestedCapital'), pct=True)}")
    else:
        print("Multiplos de valuation: sin datos")

    if ratios:
        print("Margenes / eficiencia:")
        print(f"  Margen bruto: {_fmt(ratios.get('grossProfitMargin'), pct=True)}  "
              f"Margen operativo: {_fmt(ratios.get('operatingProfitMargin'), pct=True)}  "
              f"Margen neto: {_fmt(ratios.get('netProfitMargin'), pct=True)}")
    else:
        print("Margenes / eficiencia: sin datos")

    if estimates:
        print("Estimados de analistas (proxy de backlog/visibilidad):")
        for e in estimates:
            year = e.get("date", "?")
            revenue = e.get("revenueAvg")
            eps = e.get("epsAvg")
            n_analysts = e.get("numAnalystsRevenue", "?")
            print(f"  {year}: ingresos est. ${_fmt(revenue)}, EPS est. {_fmt(eps)} "
                  f"({n_analysts} analistas)")
    else:
        print("Estimados de analistas: sin datos")

    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+", help="uno o mas tickers")
    args = parser.parse_args()

    for ticker in args.tickers:
        print_ticker(ticker.upper())


if __name__ == "__main__":
    main()
