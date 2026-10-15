#!/usr/bin/env python3
"""
Reconstruye snapshots historicos del portafolio desde el export de transacciones de Schwab.

Por que existe: Supabase solo tenia 3 snapshots, todos de sept-oct 2026 — el momento en que
el proyecto empezo a registrar el portafolio. LP arranco a invertir el 23-dic-2024, casi dos
anos antes, y pidio que el dashboard compare el portafolio real contra el S&P 500 desde esa
fecha, no desde que arranco el tracking. Sin snapshots historicos no hay con que graficar
esa ventana.

Este script no inventa datos: repite cronologicamente cada transaccion del export de Schwab
(compras, ventas, reinversiones, splits, spin-offs) para reconstruir que tenia LP en cartera
en cada fecha de deposito real, y le pide a yfinance el cierre de cada ticker en esa fecha
para calcular el valor de mercado. Precision exacta en eventos corporativos (decision de LP
2026-10-14): split 3-por-2 de Brookfield (BN) el 10-oct-2025 (verificado via busqueda web,
ver SPLITS abajo), reverse split + cash-in-lieu de STRIVE/ASST que la cierra por completo,
warrants de Opendoor nacidos de un spin-off y vendidos despues — todos trazables exactamente
desde las filas del propio CSV, sin aproximar.

Cadencia (decision de LP 2026-10-14): un snapshot por cada deposito real (Wire Received /
Journal entrante), no un corte arbitrario de calendario — cada punto coincide con un cambio
real de capital.

Validacion incorporada: al terminar de repetir TODAS las transacciones (hasta la ultima,
13-oct-2026), las tenencias resultantes se comparan contra el snapshot real mas reciente en
Supabase. Si no coinciden, el script avisa en vez de escribir snapshots que podrian estar mal
— la reconstruccion completa tiene que aterrizar exactamente en la realidad conocida, o algo
en el parseo esta mal.

Uso:
    venv/bin/python scripts/backfill_historical_snapshots.py data/schwab-transactions-2026-10-14.csv --dry-run
    venv/bin/python scripts/backfill_historical_snapshots.py data/schwab-transactions-2026-10-14.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.market import get_ticker_close_on  # noqa: E402
from src.data.schwab_lots import classify_asset  # noqa: E402

# Splits verificados externamente (LP pidio precision exacta, 2026-10-14) — no asumidos.
# Brookfield Corp (BN): 3-por-2 el 10-oct-2025 (ex-distribution date), confirmado via
# busqueda web (record date 3-oct-2025, payable 9-oct-2025). Es el UNICO split real de todo
# el historial de transacciones: se verifico leyendo las 184 filas del CSV completo.
SPLITS: dict[tuple[str, str], float] = {
    ("BN", "2025-10-10"): 1.5,
}

# El export de Schwab pone el CUSIP, no el ticker, en la fila de "Reverse Split" de STRIVE.
# Es el unico caso en todo el historial — ASST es la unica posicion con reverse split.
CUSIP_TO_TICKER = {"862945102": "ASST"}

# Acciones que mueven cash pero NUNCA cantidad de acciones. "Qual Div Reinvest" y
# "Reinvest Dividend" son el registro informativo del dividendo — la compra de acciones de
# la reinversion llega en una fila separada "Reinvest Shares" el mismo dia, con su propio
# qty/price. Contar acciones en ambas filas duplicaria la compra.
CASH_ONLY_ACTIONS = {
    "Wire Received", "Journal", "Qualified Dividend", "Cash Dividend",
    "Foreign Tax Paid", "NRA Tax Adj", "Qual Div Reinvest", "Reinvest Dividend",
}

LOT_BUILDING_ACTIONS = {"Buy", "Reinvest Shares", "Spin-off"}


@dataclass
class Lot:
    ticker: str
    open_date: date
    quantity: float
    cost_basis: float  # costo total del lote, no por accion

    @property
    def cost_per_share(self) -> float:
        return self.cost_basis / self.quantity if self.quantity else 0.0


@dataclass
class PortfolioState:
    lots: dict[str, list[Lot]] = field(default_factory=dict)
    cash: float = 0.0

    def add_lot(self, ticker: str, open_date: date, quantity: float, cost_basis: float) -> None:
        self.lots.setdefault(ticker, []).append(Lot(ticker, open_date, quantity, cost_basis))

    def sell(self, ticker: str, quantity: float) -> None:
        """Consume lotes FIFO (el mas viejo primero) hasta cubrir quantity."""
        remaining = quantity
        held = self.lots.get(ticker, [])
        new_held = []
        for lot in held:
            if remaining <= 1e-9:
                new_held.append(lot)
                continue
            if lot.quantity <= remaining + 1e-9:
                remaining -= lot.quantity
                continue  # el lote se consume entero
            # consumo parcial: el costo baja proporcional a la cantidad que sale
            frac_sold = remaining / lot.quantity
            lot.cost_basis -= lot.cost_basis * frac_sold
            lot.quantity -= remaining
            remaining = 0.0
            new_held.append(lot)
        if remaining > 1e-6:
            raise ValueError(
                f"Venta de {quantity} {ticker} excede lo que hay en cartera "
                f"(faltante: {remaining:.4f}) — revisar el CSV, probable transaccion "
                f"no parseada antes de esta."
            )
        self.lots[ticker] = new_held

    def apply_split(self, ticker: str, ratio: float) -> None:
        for lot in self.lots.get(ticker, []):
            lot.quantity *= ratio  # cost_basis no cambia — el split no crea ni destruye valor

    def remove_fractional_cash_in_lieu(self, ticker: str, cash_amount: float, price_hint: float) -> None:
        """Una fraccion de accion se liquido en efectivo (tipicamente tras un split). Se
        quita del lote mas reciente la cantidad fraccional implicita (cash / precio de
        referencia), proporcional al costo. price_hint es el precio del evento de split
        mismo (viene en la fila del CSV), no uno buscado aparte."""
        held = self.lots.get(ticker, [])
        if not held or price_hint <= 0:
            return
        frac_qty = cash_amount / price_hint
        total_qty = sum(l.quantity for l in held)
        if total_qty <= 0:
            return
        frac_qty = min(frac_qty, total_qty)
        remaining = frac_qty
        for lot in held:
            if remaining <= 1e-9:
                break
            take = min(lot.quantity, remaining)
            frac = take / lot.quantity if lot.quantity else 0
            lot.cost_basis -= lot.cost_basis * frac
            lot.quantity -= take
            remaining -= take
        self.lots[ticker] = [l for l in held if l.quantity > 1e-9]

    def holdings_summary(self) -> dict[str, float]:
        return {t: sum(l.quantity for l in lots) for t, lots in self.lots.items() if sum(l.quantity for l in lots) > 1e-9}


def _parse_money(raw: str) -> float:
    if not raw or raw.strip() in ("", "--"):
        return 0.0
    return float(raw.replace("$", "").replace(",", "").strip())


def _parse_date(raw: str) -> date:
    # Algunas filas traen "07/02/2026 as of 07/01/2026" — la fecha efectiva es la primera.
    first = raw.split(" as of ")[0].strip()
    return datetime.strptime(first, "%m/%d/%Y").date()


def load_transactions(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("Date"):
                continue
            rows.append({
                "date": _parse_date(row["Date"]),
                "action": row["Action"],
                "symbol": row["Symbol"].strip(),
                "quantity": float(row["Quantity"]) if row["Quantity"] else None,
                "price": _parse_money(row["Price"]) if row["Price"] else None,
                "amount": _parse_money(row["Amount"]),
            })
    # Schwab exporta mas reciente primero; se necesita cronologico para repetir la historia.
    rows.sort(key=lambda r: r["date"])
    return rows


def snapshot_at(state_holdings: dict[str, float], cash: float, lots_by_ticker: dict[str, list[Lot]],
                 as_of: date) -> dict | None:
    """Arma el payload de un snapshot: para cada ticker con posicion, el precio de cierre
    de ese dia (yfinance) y el detalle de lotes con costo preservado del replay."""
    lots_payload = []
    missing_prices = []
    for ticker, total_qty in state_holdings.items():
        price = get_ticker_close_on(ticker, as_of.isoformat())
        if price is None:
            missing_prices.append(ticker)
            continue
        asset_class, _ = classify_asset(ticker)
        for lot in lots_by_ticker[ticker]:
            if lot.quantity <= 1e-9:
                continue
            lots_payload.append({
                "ticker": ticker,
                "asset_class": asset_class,
                "open_date": lot.open_date.isoformat(),
                "quantity": round(lot.quantity, 6),
                "cost_per_share": round(lot.cost_per_share, 6),
                "cost_basis": round(lot.cost_basis, 2),
                "price_at_snapshot": round(price, 4),
                "market_value": round(lot.quantity * price, 2),
                "holding_period": "Long Term" if (as_of - lot.open_date).days > 365 else "Short Term",
            })
    if missing_prices:
        print(f"  AVISO {as_of}: sin precio historico para {missing_prices} — excluidos "
              f"del snapshot (no se inventa un valor).")
    return {
        "as_of": as_of,
        "cash": round(cash, 2),
        "lots": lots_payload,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="Reconstruye y valida, no escribe")
    args = ap.parse_args()

    transactions = load_transactions(args.csv_path)
    print(f"{len(transactions)} transacciones, {transactions[0]['date']} -> {transactions[-1]['date']}")

    # Replay completo UNA vez, tomando una foto (deep-copy de cantidades/costos) en cada
    # fecha de deposito según se va avanzando — así cada snapshot refleja exactamente lo que
    # había en cartera justo después de ese depósito, no el estado final reproyectado hacia
    # atrás.
    state = PortfolioState()
    pending_split_price: dict[str, float] = {}
    snapshots_to_write = []
    seen_deposit_dates: set[date] = set()

    for tx in transactions:
        action, symbol, qty, price, amount = (
            tx["action"], tx["symbol"], tx["quantity"], tx["price"], tx["amount"],
        )
        state.cash += amount

        if action in CASH_ONLY_ACTIONS:
            pass
        elif action in ("Buy", "Reinvest Shares"):
            state.add_lot(symbol, tx["date"], qty, -amount)
        elif action == "Sell":
            state.sell(symbol, qty)
        elif action == "Spin-off":
            state.add_lot(symbol, tx["date"], qty, 0.0)
        elif action == "Stock Split":
            key = (symbol, tx["date"].isoformat())
            if key not in SPLITS:
                raise ValueError(f"Split no verificado para {symbol} el {tx['date']}")
            state.apply_split(symbol, SPLITS[key])
            pending_split_price[symbol] = price or 0.0
        elif action == "Reverse Split":
            ticker = CUSIP_TO_TICKER.get(symbol, symbol)
            held = sum(l.quantity for l in state.lots.get(ticker, []))
            state.sell(ticker, min(held, abs(qty)))
        elif action == "Cash In Lieu":
            ref_price = pending_split_price.pop(symbol, None)
            if ref_price:
                state.remove_fractional_cash_in_lieu(symbol, amount, ref_price)
        else:
            raise ValueError(f"Accion no reconocida: {action!r} en {tx['date']} {symbol}")

        is_deposit = action in ("Wire Received", "Journal") and amount > 0
        if is_deposit and tx["date"] not in seen_deposit_dates:
            seen_deposit_dates.add(tx["date"])
            holdings = state.holdings_summary()
            snapshots_to_write.append((
                tx["date"],
                dict(holdings),
                state.cash,
                {t: [Lot(l.ticker, l.open_date, l.quantity, l.cost_basis) for l in lots]
                 for t, lots in state.lots.items()},
            ))

    print(f"\n{len(snapshots_to_write)} fechas de deposito -> {len(snapshots_to_write)} snapshots a crear")

    # Validacion: las tenencias finales del replay COMPLETO (no solo hasta el ultimo
    # deposito) tienen que coincidir con la realidad conocida en Supabase. Si no coinciden,
    # algo en el parseo esta mal y no se escribe nada.
    final_holdings = state.holdings_summary()
    from src.db import models as db
    latest = db.get_latest_snapshot()
    if latest:
        real_lots = db.get_snapshot_lots(latest["id"])
        real_qty = {}
        for l in real_lots:
            real_qty[l["ticker"]] = real_qty.get(l["ticker"], 0.0) + float(l["quantity"])
        print(f"\nValidacion contra snapshot real del {latest['as_of']}:")
        mismatches = []
        for ticker in set(final_holdings) | set(real_qty):
            replayed = round(final_holdings.get(ticker, 0.0), 2)
            real = round(real_qty.get(ticker, 0.0), 2)
            status = "OK" if abs(replayed - real) < 0.05 else "DESAJUSTE"
            if status == "DESAJUSTE":
                mismatches.append(ticker)
            print(f"  {ticker:6} replay={replayed:>10.4f}  real={real:>10.4f}  {status}")
        if mismatches:
            print(f"\nABORTA: {len(mismatches)} ticker(s) no coinciden con la realidad "
                  f"({mismatches}). No se escribe nada hasta corregir el replay.")
            return 1
        print("  Todas las posiciones coinciden. El replay es confiable.")
    else:
        print("\nAVISO: no hay snapshot real en Supabase contra el cual validar.")

    if args.dry_run:
        print("\n[dry-run] Vista previa de los snapshots a crear:")
        for as_of, holdings, cash, _ in snapshots_to_write:
            print(f"  {as_of}: {len(holdings)} tickers, cash ${cash:,.2f} — {sorted(holdings.keys())}")
        print("\n[dry-run] No se escribio nada.")
        return 0

    written = 0
    for as_of, holdings, cash, lots_by_ticker in snapshots_to_write:
        as_of_iso = as_of.isoformat()
        if db.snapshot_exists(as_of_iso):
            print(f"  {as_of_iso}: ya existe, se omite")
            continue
        snap = snapshot_at(holdings, cash, lots_by_ticker, as_of)
        if not snap["lots"]:
            print(f"  {as_of_iso}: sin lotes con precio disponible, se omite")
            continue
        total_value = sum(l["market_value"] for l in snap["lots"])
        total_cost = sum(l["cost_basis"] for l in snap["lots"])
        equity_count = len({l["ticker"] for l in snap["lots"] if l["asset_class"] == "equity"})
        etf_count = len({l["ticker"] for l in snap["lots"] if l["asset_class"] == "etf"})

        from src.data.market import get_sp500_close_on
        sp500_close = get_sp500_close_on(as_of_iso)

        snapshot_id = db.insert_portfolio_snapshot(
            as_of=as_of_iso,
            source_file=f"backfill desde transacciones Schwab (23-dic-2024 a hoy)",
            total_market_value=round(total_value, 2),
            total_cost_basis=round(total_cost, 2),
            cash=snap["cash"],
            equity_count=equity_count,
            etf_count=etf_count,
            lots=snap["lots"],
            sp500_close=sp500_close,
        )
        print(f"  {as_of_iso}: snapshot {snapshot_id} — {len(snap['lots'])} lotes, "
              f"valor ${total_value:,.2f}, S&P500={sp500_close}")
        written += 1

    print(f"\n{written} snapshot(s) historico(s) escrito(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
