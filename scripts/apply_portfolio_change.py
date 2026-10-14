#!/usr/bin/env python
"""
Crea un snapshot nuevo a partir del último, aplicando ventas que LP ya ejecutó en Schwab.

Por qué existe: el camino normal es bajar los Lot Details de Schwab y cargarlos con
load_portfolio_snapshot.py. Pero entre dos exports LP ejecuta órdenes, y hasta que no baja
un export nuevo el brain sigue viendo el portafolio viejo. Eso tiene una consecuencia
concreta: el guardrail valida el cash disponible antes de aprobar una compra, así que un
cash desactualizado hace que rechace compras que en realidad sí se pueden pagar.

Este script cubre ese hueco sin inventar datos. Los lotes no se recalculan: se copian tal
cual del último snapshot, porque una venta total elimina posiciones pero no altera los lotes
de las demás. Lo único que se refresca son los precios, que se bajan en vivo.

Qué NO hace, a propósito:
  - No vende parcialmente. Una venta parcial obliga a decidir qué lotes se fueron (FIFO,
    LIFO, specific lot), y esa decisión la toma Schwab, no este script. Para una venta
    parcial, bajá el export real.
  - No agrega posiciones nuevas. Una compra crea un lote con fecha y costo propios que solo
    Schwab conoce con exactitud.

Para cualquier cosa que no sea una venta total, el export de Schwab es la fuente.

Uso:
    # ver qué haría, sin escribir
    venv/bin/python scripts/apply_portfolio_change.py --sell UNH --cash 506.61 \
        --as-of 2026-10-14 --dry-run

    # aplicarlo
    venv/bin/python scripts/apply_portfolio_change.py --sell UNH --cash 506.61 \
        --as-of 2026-10-14
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import models as db  # noqa: E402


def _live_prices(tickers: list[str]) -> dict[str, float]:
    """Precio actual de cada ticker. Falla ruidosamente si alguno no se puede resolver:
    un snapshot con un precio faltante corrompe la medición de retorno, así que es mejor
    abortar que guardar un valor de mercado incompleto."""
    import warnings

    import yfinance as yf

    prices = {}
    missing = []
    for ticker in tickers:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                hist = yf.Ticker(ticker).history(period="1d")
            if hist.empty:
                missing.append(ticker)
                continue
            prices[ticker] = round(float(hist["Close"].iloc[-1]), 4)
        except Exception:
            missing.append(ticker)

    if missing:
        raise RuntimeError(
            f"No se pudo obtener precio de: {', '.join(missing)}. "
            f"Sin precio no se puede calcular market_value y el snapshot quedaría incompleto."
        )
    return prices


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sell", action="append", default=[], metavar="TICKER",
                    help="Posición vendida por completo. Repetible.")
    ap.add_argument("--cash", type=float, required=True,
                    help="Cash disponible después de las ventas")
    ap.add_argument("--as-of", required=True, help="Fecha del snapshot nuevo (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true", help="Resume sin escribir en la DB")
    args = ap.parse_args()

    base = db.get_latest_snapshot()
    if not base:
        print("ERROR: no hay ningún snapshot previo del cual partir.", file=sys.stderr)
        return 1

    as_of = str(args.as_of)
    if as_of <= str(base["as_of"]):
        print(f"ERROR: --as-of {as_of} no es posterior al último snapshot "
              f"({base['as_of']}). Un snapshot es un hecho fechado: no se puede "
              f"insertar uno en el pasado de la serie.", file=sys.stderr)
        return 1

    lots = db.get_snapshot_lots(base["id"])
    sold = {t.upper() for t in args.sell}

    present = {l["ticker"] for l in lots}
    unknown = sold - present
    if unknown:
        print(f"ERROR: no están en el snapshot del {base['as_of']}: "
              f"{', '.join(sorted(unknown))}", file=sys.stderr)
        return 1

    kept = [l for l in lots if l["ticker"] not in sold]
    dropped = [l for l in lots if l["ticker"] in sold]

    tickers = sorted({l["ticker"] for l in kept})
    print(f"Base:        snapshot {base['id']} del {base['as_of']}")
    print(f"Vendidas:    {', '.join(sorted(sold)) or '(ninguna)'} "
          f"→ {len(dropped)} lote(s) fuera")
    print(f"Quedan:      {len(kept)} lote(s) en {len(tickers)} posiciones")
    print(f"Bajando precios en vivo de {len(tickers)} tickers...")
    prices = _live_prices(tickers)

    # Los lotes se copian; solo se recalcula el precio y el valor de mercado. holding_period
    # se conserva: se verificó que la regla de Schwab (>365 días = Long Term) no cambia la
    # clasificación de ningún lote en este corte.
    payload = []
    for l in kept:
        price = prices[l["ticker"]]
        quantity = float(l["quantity"])
        payload.append(dict(
            ticker=l["ticker"],
            asset_class=l["asset_class"],
            open_date=l["open_date"].isoformat(),
            quantity=quantity,
            cost_per_share=float(l["cost_per_share"]),
            cost_basis=float(l["cost_basis"]),
            price_at_snapshot=price,
            market_value=round(quantity * price, 2),
            holding_period=l["holding_period"],
        ))

    total_value = round(sum(p["market_value"] for p in payload), 2)
    total_cost = round(sum(p["cost_basis"] for p in payload), 2)
    equity_tickers = {p["ticker"] for p in payload if p["asset_class"] == "equity"}
    etf_tickers = {p["ticker"] for p in payload if p["asset_class"] == "etf"}

    print()
    for ticker in tickers:
        ls = [p for p in payload if p["ticker"] == ticker]
        qty = sum(p["quantity"] for p in ls)
        val = sum(p["market_value"] for p in ls)
        cost = sum(p["cost_basis"] for p in ls)
        pl = (val - cost) / cost * 100 if cost else 0.0
        print(f"  {ticker:6} {qty:>10.4f} @ ${prices[ticker]:>9,.2f} = "
              f"${val:>9,.2f}  ({pl:+.1f}%)")

    print()
    print(f"Valor de mercado: ${total_value:,.2f}")
    print(f"Costo total:      ${total_cost:,.2f}")
    print(f"Cash:             ${args.cash:,.2f}")
    print(f"Cuenta total:     ${total_value + args.cash:,.2f}")
    print(f"Posiciones:       {len(equity_tickers)} equities + {len(etf_tickers)} ETFs")

    if args.dry_run:
        print()
        print("[dry-run] No se escribió nada en la DB.")
        return 0

    if db.snapshot_exists(as_of):
        print(f"\nERROR: ya existe un snapshot con fecha {as_of}.", file=sys.stderr)
        return 1

    snapshot_id = db.insert_portfolio_snapshot(
        as_of=as_of,
        source_file=(
            f"reconstruido de {base['as_of']} "
            f"(venta {','.join(sorted(sold))}; precios en vivo {date.today().isoformat()})"
        ),
        total_market_value=total_value,
        total_cost_basis=total_cost,
        cash=args.cash,
        equity_count=len(equity_tickers),
        etf_count=len(etf_tickers),
        lots=payload,
        sp500_close=None,
    )
    print(f"\nOK — snapshot {snapshot_id} del {as_of} con {len(payload)} lotes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
