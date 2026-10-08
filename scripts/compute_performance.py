#!/usr/bin/env python3
"""
Registra un snapshot del portafolio real y muestra la serie historica vs S&P 500.

Cambio respecto al diseño anterior: antes calculaba el valor del fondo simulado desde
executed_trades/cash_events. Ahora el portafolio real vive en el CSV de Schwab, asi que
el snapshot se toma de ahi — una fila por CSV que LP sube.

Esa serie es lo que alimenta la curva de performance del dashboard. Arranca pobre (un
punto por cada CSV subido) y mejora con el tiempo: no hay forma de reconstruir hacia
atras lo que no se registro.

La comparacion contra el S&P 500 es relativa desde el primer snapshot — no un alpha
absoluto, porque el portafolio tiene aportes y retiros que no se modelan aqui.

Uso:
    python scripts/compute_performance.py              # registra el CSV mas reciente
    python scripts/compute_performance.py --dry-run
    python scripts/compute_performance.py --history    # solo muestra la serie
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.portfolio_csv import load_snapshot  # noqa: E402
from src.db import carlson as k  # noqa: E402


def _sp500_close() -> float | None:
    """
    Cierre del S&P 500.

    Via FMP primero por consistencia con el resto del pipeline, pero ese endpoint
    quedo bloqueado (402) igual que los demas de FMP, asi que Yahoo es el camino que
    de hecho funciona. Si ambos fallan, el snapshot se guarda sin benchmark en vez de
    perderse.
    """
    try:
        from src.data.market import SP500_INDEX_SYMBOL, get_price

        return get_price(SP500_INDEX_SYMBOL)
    except Exception:
        pass

    try:
        import yfinance as yf

        hist = yf.Ticker("^GSPC").history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"  AVISO: no se pudo obtener el S&P 500 ({type(e).__name__}) — "
              "el snapshot se guarda sin benchmark.")
    return None


def show_history() -> int:
    rows = k.get_snapshot_history()
    if not rows:
        print("Sin snapshots todavia.")
        print("\nLa serie se construye con cada CSV que LP sube. No se puede")
        print("reconstruir hacia atras lo que no se registro.")
        return 0

    print(f"Serie del portafolio — {len(rows)} snapshot(s)\n")

    base = rows[0]
    base_val = float(base["total_market_value"])
    base_sp = float(base["sp500_close"]) if base.get("sp500_close") else None

    print(f"  {'fecha':12} {'mercado':>12} {'costo':>12} {'gan.':>8} "
          f"{'vs base':>9} {'S&P':>9} {'rel':>8}")
    print("  " + "-" * 74)

    for r in rows:
        mv = float(r["total_market_value"])
        cb = float(r["total_cost_basis"])
        gain = (mv - cb) / cb if cb else 0.0
        chg = (mv - base_val) / base_val if base_val else 0.0

        sp_txt, rel_txt = "—", "—"
        if base_sp and r.get("sp500_close"):
            sp_chg = (float(r["sp500_close"]) - base_sp) / base_sp
            sp_txt = f"{sp_chg:+.2%}"
            rel_txt = f"{chg - sp_chg:+.2%}"

        print(f"  {str(r['as_of']):12} ${mv:>11,.2f} ${cb:>11,.2f} {gain:>+7.2%} "
              f"{chg:>+8.2%} {sp_txt:>9} {rel_txt:>8}")

    if len(rows) < 2:
        print("\n  (con un solo punto no hay serie — subi mas CSVs con el tiempo)")
    elif base_sp is None:
        print("\n  (sin S&P en el primer snapshot no hay comparacion relativa)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Calcula sin guardar")
    ap.add_argument("--history", action="store_true", help="Solo muestra la serie")
    ap.add_argument("--file", help="CSV especifico")
    args = ap.parse_args()

    if args.history:
        return show_history()

    try:
        s = load_snapshot(Path(args.file) if args.file else None)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    sp = _sp500_close()

    print(f"Snapshot al {s.as_of} (fuente: {s.source_file.name})")
    print(f"  mercado: ${s.total_market_value:,.2f}")
    print(f"  costo:   ${s.total_cost_basis:,.2f}")
    print(f"  ganancia:{s.total_gain_usd:>12,.2f} ({s.total_gain_pct:+.2%})")
    print(f"  cash:    ${s.cash:,.2f}")
    print(f"  {len(s.equities)} acciones / {len(s.etfs)} ETFs")
    if sp:
        print(f"  S&P 500: {sp:,.2f}")

    if s.is_stale:
        print(f"\n  AVISO: el CSV tiene {s.age_days} dias.")

    if args.dry_run:
        print("\n[dry-run] no se guardo.")
        return 0

    k.log_portfolio_snapshot(
        as_of=s.as_of,
        source_file=s.source_file.name,
        total_market_value=s.total_market_value,
        total_cost_basis=s.total_cost_basis,
        cash=s.cash,
        equity_count=len(s.equities),
        etf_count=len(s.etfs),
        sp500_close=sp,
    )
    print("\nGuardado. (Idempotente por fecha: subir el mismo CSV dos veces no duplica.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
