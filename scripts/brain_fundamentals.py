#!/usr/bin/env python3
"""
Datos fundamentales de uno o mas tickers — insumo del framework de screening (ver
src/agent/prompt.py, paso 3). Invocado por bash desde la sesion programada para cada ticker
en revision (posiciones existentes o candidatos del lote de la semana).

No reemplaza la investigacion cualitativa (noticias, guidance, moat) — eso lo hace el brain
via web search por su cuenta. Esto solo trae los numeros: precio, multiplos de valuation,
margenes/eficiencia, y estimados de analistas (proxy de backlog/visibilidad cuando la empresa
no da guidance explicito).

Fuentes (7 de septiembre de 2026): stockanalysis.com es la fuente primaria y Yahoo Finance
(src/data/yahoo.py) el respaldo automatico, campo por campo. El respaldo se agrego despues de
que el primer lote real perdiera 4 de 18 tickers (ATO, AVY, AWK, BALL) por un fallo de
scraping que dejaba sin dato a candidatos perfectamente validos.

Cada valor que NO viene de la fuente primaria se marca con su origen entre corchetes, para
que el brain nunca razone sobre un numero sin saber de donde salio. Ver el docstring de
src/data/yahoo.py para las dos diferencias de definicion entre fuentes (forward P/E y ROIC),
que son reales y no se promedian.

Uso:
    python scripts/brain_fundamentals.py AAPL
    python scripts/brain_fundamentals.py AAPL MSFT NVDA
    python scripts/brain_fundamentals.py ATO --source yahoo   # fuerza una sola fuente
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import fundamentals, market, yahoo  # noqa: E402


def _fmt(value, source=None):
    """Formatea un valor y, si vino de una fuente que no es la primaria, lo marca.

    None significa "esta fuente no publica esta metrica para este sector" (p.ej. margen bruto
    para aseguradoras en stockanalysis.com, o ROIC en Yahoo, que no lo calcula) — es un dato
    ausente por diseño, no un error. Ver los docstrings de get_valuation_metrics() en ambos
    modulos."""
    if value is None:
        return "N/D"
    return f"{value} [{source}]" if source else str(value)


def _price_with_source(ticker: str):
    """Precio con respaldo. stockanalysis.com primero; si su scraping falla —el modo de fallo
    que costo 4 tickers del primer lote— cae a Yahoo en vez de tumbar el ticker completo."""
    try:
        return market.get_price(ticker), None
    except Exception as exc:
        price = yahoo.get_price(ticker)
        return price, f"yahoo; stockanalysis fallo: {type(exc).__name__}"


def _merge_valuation(ticker: str):
    """Multiplos y margenes de la fuente primaria, rellenando con Yahoo SOLO los campos que
    la primaria dejo vacios. Devuelve (dict de valores, dict de fuentes por campo).

    Importante: no se sobreescribe ningun campo que la primaria si trajo. Las dos fuentes
    calculan forward_pe sobre años fiscales distintos (18.47 vs 20.68 para AVGO), asi que
    mezclarlos por preferencia produciria un numero que no corresponde a ninguna definicion.
    Yahoo solo llena huecos."""
    sources = {}
    try:
        primary = fundamentals.get_valuation_metrics(ticker)
    except Exception as exc:
        primary = None
        primary_error = f"{type(exc).__name__}"

    if primary is None:
        merged = yahoo.get_valuation_metrics(ticker)
        for key in merged:
            if merged[key] is not None:
                sources[key] = f"yahoo; stockanalysis fallo: {primary_error}"
        return merged, sources

    missing = [k for k, v in primary.items() if v is None]
    if missing:
        try:
            backup = yahoo.get_valuation_metrics(ticker)
            for key in missing:
                if backup.get(key) is not None:
                    primary[key] = backup[key]
                    sources[key] = "yahoo"
        except Exception:
            # Si el respaldo tambien falla, los campos quedan en None y se imprimen como N/D.
            # No es motivo para tumbar el ticker: el resto de los datos sigue siendo util.
            pass

    return primary, sources


def print_ticker(ticker: str, source: str = "auto"):
    if source == "yahoo":
        price, price_src = yahoo.get_price(ticker), "yahoo"
        valuation, val_sources = yahoo.get_valuation_metrics(ticker), {}
        forecast = yahoo.get_analyst_forecast(ticker)
        forecast_src = "yahoo"
    elif source == "stockanalysis":
        price, price_src = market.get_price(ticker), None
        valuation, val_sources = fundamentals.get_valuation_metrics(ticker), {}
        forecast = fundamentals.get_analyst_forecast(ticker)
        forecast_src = None
    else:
        price, price_src = _price_with_source(ticker)
        valuation, val_sources = _merge_valuation(ticker)
        try:
            forecast = fundamentals.get_analyst_forecast(ticker)
            forecast_src = None
        except Exception as exc:
            forecast = yahoo.get_analyst_forecast(ticker)
            forecast_src = f"yahoo; stockanalysis fallo: {type(exc).__name__}"

    print(f"=== {ticker} ===")
    price_note = f" [{price_src}]" if price_src else ""
    print(f"Precio actual: ${price:,.2f}{price_note}")

    print("Multiplos de valuation:")
    print(f"  P/E: {_fmt(valuation['pe_ratio'], val_sources.get('pe_ratio'))}  "
          f"Forward P/E: {_fmt(valuation['forward_pe'], val_sources.get('forward_pe'))}  "
          f"P/S: {_fmt(valuation['ps_ratio'], val_sources.get('ps_ratio'))}  "
          f"ROIC: {_fmt(valuation['roic'], val_sources.get('roic'))}")

    # Yahoo trae ROE/ROA, que stockanalysis no expone en esta tabla. Solo se imprimen si la
    # corrida los tiene (es decir, si el respaldo de Yahoo entro en juego o se forzo --source
    # yahoo): son metricas distintas de ROIC, complementarias, nunca su reemplazo.
    if valuation.get("roe") or valuation.get("roa"):
        print(f"  ROE: {_fmt(valuation.get('roe'))}  ROA: {_fmt(valuation.get('roa'))}")

    print("Margenes / eficiencia:")
    print(f"  Margen bruto: {_fmt(valuation['gross_margin'], val_sources.get('gross_margin'))}  "
          f"Margen operativo: {_fmt(valuation['operating_margin'], val_sources.get('operating_margin'))}  "
          f"Margen neto: {_fmt(valuation['net_margin'], val_sources.get('net_margin'))}")

    if forecast["num_analysts"]:
        note = f" [{forecast_src}]" if forecast_src else ""
        fy = forecast["fiscal_year"] or "año fiscal no etiquetado"
        print("Estimados de analistas (proxy de backlog/visibilidad):")
        print(f"  {fy}: ingresos est. {forecast['revenue']}, "
              f"EPS est. {forecast['eps']} ({forecast['num_analysts']} analistas){note}")
    else:
        print("Estimados de analistas: sin cobertura medible")

    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+", help="uno o mas tickers")
    parser.add_argument(
        "--source", choices=["auto", "stockanalysis", "yahoo"], default="auto",
        help="auto (default): stockanalysis con respaldo de Yahoo por campo. Las otras dos "
             "fuerzan una sola fuente, util para comparar o diagnosticar discrepancias.",
    )
    args = parser.parse_args()

    for ticker in args.tickers:
        print_ticker(ticker.upper(), source=args.source)


if __name__ == "__main__":
    main()
