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


def _fmt(value):
    """Algunos campos de get_valuation_metrics vienen en None cuando ese sector no reporta
    esa metrica en stockanalysis.com (p.ej. margen bruto para aseguradoras) — no es un dato
    faltante por error, ver docstring de get_valuation_metrics()."""
    return "N/D" if value is None else value


def print_ticker(ticker: str):
    price = market.get_price(ticker)
    valuation = fundamentals.get_valuation_metrics(ticker)
    forecast = fundamentals.get_analyst_forecast(ticker)

    print(f"=== {ticker} ===")
    print(f"Precio actual: ${price:,.2f}")

    print("Multiplos de valuation:")
    print(f"  P/E: {_fmt(valuation['pe_ratio'])}  Forward P/E: {_fmt(valuation['forward_pe'])}  "
          f"P/S: {_fmt(valuation['ps_ratio'])}  ROIC: {_fmt(valuation['roic'])}")

    print("Margenes / eficiencia:")
    print(f"  Margen bruto: {_fmt(valuation['gross_margin'])}  "
          f"Margen operativo: {_fmt(valuation['operating_margin'])}  "
          f"Margen neto: {_fmt(valuation['net_margin'])}")

    if forecast["num_analysts"]:
        print("Estimados de analistas (proxy de backlog/visibilidad):")
        print(f"  {forecast['fiscal_year']}: ingresos est. {forecast['revenue']}, "
              f"EPS est. {forecast['eps']} ({forecast['num_analysts']} analistas)")
    else:
        print("Estimados de analistas: sin cobertura medible")

    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+", help="uno o mas tickers")
    args = parser.parse_args()

    for ticker in args.tickers:
        print_ticker(ticker.upper())


if __name__ == "__main__":
    main()
