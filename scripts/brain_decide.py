#!/usr/bin/env python3
"""
Registro de decisiones del brain — el unico camino de escritura a `decisions` desde el brain
(ver src/agent/prompt.py, paso 4-5: toda decision de compra/venta, y toda revision sin accion,
se reporta). Invocado por bash desde la sesion programada de Cowork/Routine.

`propose` es el camino que de verdad importa para el principio "el LLM propone, el codigo
decide": arma el PortfolioState en vivo (misma fuente que scripts/brain_portfolio.py) y corre
src.guardrails.validator.validate_trade_proposal() — el resultado que se guarda es el que
calcula el codigo, nunca lo que el brain crea que deberia pasar. Si el guardrail rechaza la
propuesta, igual queda registrada (con la razon) para el historial y para que
scripts/run_daily.py nunca la muestre como pendiente de ejecutar.

Uso:
    python scripts/brain_decide.py propose --ticker AAPL --action buy --quantity 10 \\
        --price 230.50 --rationale "..." --bear-case "..." --bear-case-prob 0.15

    python scripts/brain_decide.py review --ticker AAPL --rationale "sin cambios: ..."

    # Ambos aceptan --date YYYY-MM-DD (default: hoy) y --dry-run (imprime, no escribe)
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import models as db  # noqa: E402
from src.guardrails import validator as v  # noqa: E402
from src.reporting.portfolio import build_portfolio_state  # noqa: E402


def _today() -> str:
    return date.today().isoformat()


def cmd_propose(args):
    portfolio = build_portfolio_state()
    trade = v.TradeProposal(
        ticker=args.ticker,
        action=args.action,
        quantity=args.quantity,
        price=args.price,
        bear_case=args.bear_case,
        bear_case_probability=args.bear_case_prob,
    )
    result = v.validate_trade_proposal(trade, portfolio)
    guardrail_result = "approved" if result.approved else "rejected"

    print(f"Guardrail: {guardrail_result.upper()} — {result.reason}")
    for w in result.warnings:
        print(f"  aviso: {w}")

    if args.dry_run:
        print("[dry-run] no se guardo.")
        return

    db.log_trade_proposal(
        date=args.date,
        ticker=args.ticker,
        action=args.action,
        quantity=args.quantity,
        price=args.price,
        rationale=args.rationale,
        guardrail_result=guardrail_result,
        bear_case=args.bear_case,
        bear_case_probability=args.bear_case_prob,
        guardrail_rejection_reason=None if result.approved else result.reason,
    )
    if result.approved:
        print("Registrado como propuesta pendiente de ejecucion manual "
              "(la vas a ver en scripts/run_daily.py).")
    else:
        print("Registrado como rechazado por guardrail — no queda pendiente de ejecucion.")


def cmd_review(args):
    if args.dry_run:
        print(f"[dry-run] review: date={args.date} ticker={args.ticker} "
              f"rationale={args.rationale!r}")
        return
    db.log_decision(
        date=args.date,
        ticker=args.ticker,
        entry_type="review",
        rationale=args.rationale,
        guardrail_result="n/a",
    )
    print(f"Registrado: revision sin accion de {args.ticker} el {args.date}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_propose = sub.add_parser("propose", help="Propuesta de compra o venta, guardrail-validada")
    p_propose.add_argument("--ticker", required=True)
    p_propose.add_argument("--action", required=True, choices=["buy", "sell"])
    p_propose.add_argument("--quantity", type=float, required=True)
    p_propose.add_argument("--price", type=float, required=True)
    p_propose.add_argument("--rationale", required=True)
    p_propose.add_argument("--bear-case", required=True, dest="bear_case")
    p_propose.add_argument("--bear-case-prob", type=float, required=True, dest="bear_case_prob")
    p_propose.add_argument("--date", default=_today())
    p_propose.add_argument("--dry-run", action="store_true")
    p_propose.set_defaults(func=cmd_propose)

    p_review = sub.add_parser("review", help="Revision sin accion de una posicion existente")
    p_review.add_argument("--ticker", required=True)
    p_review.add_argument("--rationale", required=True)
    p_review.add_argument("--date", default=_today())
    p_review.add_argument("--dry-run", action="store_true")
    p_review.set_defaults(func=cmd_review)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
