#!/usr/bin/env python3
"""
Registro manual de la verdad de la cuenta — para la arquitectura donde el humano ejecuta
TODO en IBKR directamente (ver PROJECT_PLAN.md / el review de arquitectura: se decidio
mimetizar a The Claude Portfolio de cerca, sin executor automatizado).

El brain (Cowork/Routine) solo propone — nunca escribe aqui. `executed_trades` y
`cash_events` siguen siendo, por diseno, las UNICAS tablas que definen que hay realmente en
la cuenta (ver supabase/migrations/20260727120000_executor_tables.sql), asi que este script
corre con el rol `ataraxia_executor` (via EXECUTOR_DB_USER/EXECUTOR_DB_PASSWORD en .env, o
directamente SUPABASE_DB_USER/PASSWORD si preferis un solo rol ahora que el executor sos vos
mismo) — no con ataraxia_brain, que solo tiene SELECT sobre estas dos tablas.

Uso:
    # Deposito inicial (u otro movimiento de cash que no es un trade)
    python scripts/log_manual_trade.py deposit --amount 10000 --note "capital inicial paper"
    python scripts/log_manual_trade.py cash-event --type dividend --amount 12.34 --note "AAPL"

    # Fill real que ejecutaste a mano en IBKR
    python scripts/log_manual_trade.py fill --ticker AAPL --action buy --quantity 10 \\
        --price 230.50 --decision-id 42

    # Todos aceptan --date YYYY-MM-DD (default: hoy) y --dry-run (imprime, no escribe)
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Cargar .env aca, ANTES del override de abajo y antes de importar src.config: sin esto,
# os.getenv("EXECUTOR_DB_USER") siempre da None (nada habia leido .env todavia) y el override
# es un no-op silencioso — src.config termina usando el default ataraxia_brain, que solo tiene
# SELECT sobre executed_trades/cash_events. load_dotenv() no pisa variables ya exportadas en
# el shell, asi que esto es seguro incluso si el usuario ya las exporto a mano.
load_dotenv(ROOT_DIR / ".env")

# Debe pasar ANTES de importar src.config: ese modulo lee las variables de entorno a nivel
# de modulo, una sola vez, al importarse.
if os.getenv("EXECUTOR_DB_USER"):
    os.environ["SUPABASE_DB_USER"] = os.environ["EXECUTOR_DB_USER"]
if os.getenv("EXECUTOR_DB_PASSWORD"):
    os.environ["SUPABASE_DB_PASSWORD"] = os.environ["EXECUTOR_DB_PASSWORD"]

from src.db import models as db  # noqa: E402


def _today() -> str:
    return date.today().isoformat()


def cmd_deposit(args):
    _record_cash_event("deposit", args.amount, args.date, args.note, args.dry_run)


def cmd_cash_event(args):
    _record_cash_event(args.type, args.amount, args.date, args.note, args.dry_run)


def _record_cash_event(event_type: str, amount: float, when: str, note: str | None, dry_run: bool):
    if event_type in ("withdrawal", "fee") and amount > 0:
        print(
            f"AVISO: '{event_type}' normalmente lleva monto negativo (sale cash) — "
            f"recibido +{amount}. Se guarda tal cual si seguis; Ctrl+C para cancelar y "
            f"corregir el signo."
        )
    if dry_run:
        print(f"[dry-run] cash_event: date={when} type={event_type} amount={amount} note={note!r}")
        return
    db.record_cash_event(date=when, event_type=event_type, amount=amount, note=note)
    print(f"Registrado: {event_type} de {amount:+,.2f} el {when}.")


def cmd_fill(args):
    if args.dry_run:
        print(
            f"[dry-run] fill: date={args.date} ticker={args.ticker} action={args.action} "
            f"quantity={args.quantity} price={args.price} decision_id={args.decision_id}"
        )
        return
    db.record_fill(
        date=args.date,
        ticker=args.ticker,
        action=args.action,
        quantity=args.quantity,
        price=args.price,
        decision_id=args.decision_id,
    )
    print(
        f"Registrado: {args.action} {args.quantity} {args.ticker} @ {args.price} el {args.date}"
        + (f" (decision #{args.decision_id})" if args.decision_id else "")
    )
    if args.decision_id is not None:
        # Cierra el ciclo de la propuesta para que scripts/run_daily.py deje de mostrarla
        # como pendiente — sin esto quedaria 'pending' para siempre aunque ya se ejecuto.
        db.mark_execution_status(args.decision_id, "executed")
        print(f"decision #{args.decision_id} marcada como 'executed'.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_deposit = sub.add_parser("deposit", help="Atajo para un cash_event de tipo 'deposit'")
    p_deposit.add_argument("--amount", type=float, required=True)
    p_deposit.add_argument("--date", default=_today())
    p_deposit.add_argument("--note", default=None)
    p_deposit.add_argument("--dry-run", action="store_true")
    p_deposit.set_defaults(func=cmd_deposit)

    p_cash = sub.add_parser("cash-event", help="Cualquier movimiento de cash que no es un trade")
    p_cash.add_argument("--type", required=True,
                         choices=["deposit", "withdrawal", "dividend", "fee", "interest"])
    p_cash.add_argument("--amount", type=float, required=True,
                         help="Positivo = entra cash, negativo = sale (withdrawal/fee)")
    p_cash.add_argument("--date", default=_today())
    p_cash.add_argument("--note", default=None)
    p_cash.add_argument("--dry-run", action="store_true")
    p_cash.set_defaults(func=cmd_cash_event)

    p_fill = sub.add_parser("fill", help="Un fill real que ejecutaste a mano en IBKR")
    p_fill.add_argument("--ticker", required=True)
    p_fill.add_argument("--action", required=True, choices=["buy", "sell"])
    p_fill.add_argument("--quantity", type=float, required=True)
    p_fill.add_argument("--price", type=float, required=True)
    p_fill.add_argument("--date", default=_today())
    p_fill.add_argument("--decision-id", type=int, default=None,
                         help="id de la propuesta en decisions que este fill ejecuta, si aplica")
    p_fill.add_argument("--dry-run", action="store_true")
    p_fill.set_defaults(func=cmd_fill)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
