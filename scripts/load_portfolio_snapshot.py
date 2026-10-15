#!/usr/bin/env python
"""
Carga un snapshot del portafolio real de LP a Supabase, con detalle de lotes.

Por que existe: antes el portafolio vivia como un CSV en data/ que se sobreescribia. Decision
de LP (2026-10-11): subirlo a Supabase para tener historico versionado — cada corte queda
guardado con su fecha, y la serie de snapshots es lo que despues permite medir el retorno
contra el S&P 500 sin trabajo extra.

Uso:
    # ver que haria, sin escribir nada
    venv/bin/python scripts/load_portfolio_snapshot.py data/schwab-lots/2026-10-08 \
        --cash 100.84 --dry-run

    # cargar de verdad
    venv/bin/python scripts/load_portfolio_snapshot.py data/schwab-lots/2026-10-08 \
        --cash 100.84

El directorio debe contener los exports "Lot Details" de Schwab (uno por ticker, todos del
mismo corte). Ver src/data/schwab_lots.py para el formato y por que se usan los Lot Details
en vez del export "Positions".
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.schwab_lots import (  # noqa: E402
    SchwabLotParseError,
    parse_lot_details_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Directorio con los Lot Details de Schwab")
    parser.add_argument("--cash", type=float, default=0.0,
                        help="Cash disponible en la cuenta al momento del corte")
    parser.add_argument("--pattern", default="*.csv", help="Glob de archivos (default: *.csv)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parsea y resume, sin escribir en la DB")
    parser.add_argument("--sp500-close", type=float, default=None,
                        help="Override manual del cierre del S&P 500 ese dia. Si se omite, "
                             "se obtiene automaticamente (src.data.market.get_sp500_close_on)")
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"ERROR: {directory} no es un directorio", file=sys.stderr)
        return 1

    try:
        snap = parse_lot_details_dir(directory, pattern=args.pattern, cash=args.cash)
    except SchwabLotParseError as exc:
        print(f"ERROR de parseo: {exc}", file=sys.stderr)
        return 1

    equities = snap.equities_only()
    eq_cost = sum(l.cost_basis for l in equities)
    eq_value = sum(l.market_value or 0.0 for l in equities)
    total_account = snap.total_market_value + snap.cash

    print(f"Corte:            {snap.as_of}")
    print(f"Archivos leidos:  {len(snap.source_files)}")
    print(f"Lotes:            {len(snap.lots)} en {len(snap.tickers)} posiciones")
    print(f"  equities:       {snap.count_by_class('equity')}")
    print(f"  ETFs:           {snap.count_by_class('etf')}")
    print()
    print(f"Costo total:      ${snap.total_cost_basis:,.2f}")
    print(f"Valor de mercado: ${snap.total_market_value:,.2f}")
    print(f"Cash:             ${snap.cash:,.2f}")
    print(f"Cuenta total:     ${total_account:,.2f}")
    print()
    # El alpha de Ataraxia se mide solo sobre equities (decision de LP 2026-10-11): los ETFs
    # amplios son ancla pasiva fuera del mandato, y VOO *es* el benchmark.
    if eq_cost:
        print(f"SOLO EQUITIES (lo que se mide contra el S&P 500):")
        print(f"  costo ${eq_cost:,.2f} | valor ${eq_value:,.2f} | "
              f"P/L ${eq_value - eq_cost:,.2f} ({(eq_value - eq_cost) / eq_cost * 100:+.2f}%)")
        print()

    if snap.unknown_asset_classes:
        print("AVISO — tickers que no se pudieron clasificar con evidencia y se asumieron")
        print("equity. Si alguno es un ETF, agregalo a KNOWN_ETFS en src/data/schwab_lots.py")
        print("antes de cargar, porque entraria en la medicion de alpha:")
        print(f"  {', '.join(snap.unknown_asset_classes)}")
        print()

    if args.dry_run:
        print("[dry-run] No se escribio nada en la DB.")
        return 0

    # El import se hace aca y no arriba para que --dry-run funcione sin credenciales de DB.
    from src.db import models as db  # noqa: E402

    as_of = snap.as_of.isoformat()
    if db.snapshot_exists(as_of):
        print(f"ERROR: ya existe un snapshot con fecha {as_of}.", file=sys.stderr)
        print("Un snapshot es un hecho historico fechado y no se edita. Si el corte anterior",
              file=sys.stderr)
        print("estaba mal, bajalo de nuevo con otra fecha o borralo a mano desde Supabase.",
              file=sys.stderr)
        return 1

    lots_payload = [dict(
        ticker=l.ticker,
        asset_class=l.asset_class,
        open_date=l.open_date.isoformat(),
        quantity=l.quantity,
        cost_per_share=l.cost_per_share,
        cost_basis=l.cost_basis,
        price_at_snapshot=l.price_at_snapshot,
        market_value=l.market_value,
        holding_period=l.holding_period,
    ) for l in snap.lots]

    sp500_close = args.sp500_close
    if sp500_close is None:
        from src.data.market import get_sp500_close_on
        sp500_close = get_sp500_close_on(as_of)
        if sp500_close is None:
            print(f"AVISO: no se pudo obtener el cierre del S&P 500 del {as_of} — "
                  "el snapshot se guarda sin benchmark.")

    snapshot_id = db.insert_portfolio_snapshot(
        as_of=as_of,
        source_file=f"{directory.name} ({len(snap.source_files)} archivos Lot Details)",
        total_market_value=snap.total_market_value,
        total_cost_basis=snap.total_cost_basis,
        cash=snap.cash,
        equity_count=snap.count_by_class("equity"),
        etf_count=snap.count_by_class("etf"),
        lots=lots_payload,
        sp500_close=sp500_close,
    )

    print(f"OK — snapshot {snapshot_id} cargado con {len(lots_payload)} lotes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
