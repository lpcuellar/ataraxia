"""
Executor de Ataraxia — el UNICO proceso con autoridad sobre la cuenta de IBKR.

Corre separado del brain (Docker en la maquina del usuario, junto al Client Portal Gateway).
El brain (Cowork) nunca toca IBKR; escribe propuestas aprobadas en Supabase y este proceso
las recoge. Flujo por corrida:

  1. flush_pending_writes()            — reintenta escrituras encoladas de corridas previas
  2. get_pending_proposals()           — propuestas con execution_status='pending'
  3. Por cada propuesta:
     a. Reconstruye PortfolioState desde executed_trades/cash_events + precios actuales
     b. RE-VALIDA con src/guardrails/validator.py — NUNCA confia en que el brain ya la
        aprobo (principio central: el codigo del executor decide por su cuenta)
     c. Si pasa: ejecuta contra IBKR (paper), registra el fill en executed_trades,
        marca la propuesta 'executed'
     d. Si no pasa: marca 'skipped' con la razon — y eso queda en el registro de auditoria
  4. Notifica el resultado por WhatsApp (fallo de notificacion no frena nada)

Kill switch operacional (no es veto de trades): si existe el archivo KILL_SWITCH_FILE, el
executor no ejecuta nada y avisa. Para frenar el sistema: `touch data/KILL_SWITCH`.
Esto es para fallas operacionales (bug, gateway en loop, datos corruptos) — no para
desacuerdos con el criterio del agente, que invalidarian el experimento.

Estado: la integracion con IBKR (_execute_on_ibkr) es un stub hasta tener el Gateway
corriendo (ver docker/). Todo lo demas — polling, re-validacion, registro, notificacion —
es funcional y testeable sin broker.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import DATA_DIR
from src.data import market
from src.db import models as db
from src.executor import notifier
from src.guardrails import validator as v

KILL_SWITCH_FILE = DATA_DIR / "KILL_SWITCH"


def build_portfolio_state() -> v.PortfolioState:
    """Reconstruye el PortfolioState del validator desde la verdad de la DB + precios
    actuales de FMP. Esta funcion corre en el executor con datos que el brain no puede
    haber fabricado (solo el executor escribe executed_trades/cash_events)."""
    account = db.get_account_state()
    positions = []
    for ticker, h in account["holdings"].items():
        current_price = market.get_price(ticker)
        positions.append(
            v.Position(
                ticker=ticker,
                quantity=h["quantity"],
                avg_cost=h["avg_cost"],
                current_price=current_price,
            )
        )
    return v.PortfolioState(
        positions=positions,
        cash=account["cash"],
        todays_trades=account["todays_trades"],
        flagged_for_review=db.get_flagged_tickers(),
    )


def _execute_on_ibkr(proposal: dict) -> dict:
    """Ejecuta la orden contra la cuenta paper de IBKR via Client Portal Gateway.

    STUB — se implementa cuando el Gateway este corriendo (src/broker/ibkr_client.py).
    Debe devolver: {"filled": bool, "fill_price": float, "fill_quantity": float}
    """
    raise NotImplementedError(
        "Integracion IBKR pendiente — ver src/broker/ibkr_client.py y docker/README.md"
    )


def process_proposal(proposal: dict, dry_run: bool = False) -> str:
    """Procesa una propuesta pendiente. Devuelve un resumen de una linea para el reporte."""
    pid, ticker = proposal["id"], proposal["ticker"]

    portfolio = build_portfolio_state()
    trade = v.TradeProposal(
        ticker=ticker,
        action=proposal["action"],
        quantity=float(proposal["quantity"]),
        price=float(proposal["price"]),
    )

    result = v.validate_trade_proposal(trade, portfolio)
    if not result.approved:
        db.mark_execution_status(pid, "skipped", f"re-validacion del executor: {result.reason}")
        return f"SKIP {ticker} {proposal['action']} — {result.reason}"

    if dry_run:
        return f"DRY-RUN {ticker} {proposal['action']} {trade.quantity} @ ~{trade.price} — pasaria"

    try:
        fill = _execute_on_ibkr(proposal)
    except NotImplementedError:
        db.mark_execution_status(pid, "failed", "integracion IBKR no implementada todavia")
        return f"FAIL {ticker} — IBKR no integrado todavia (propuesta marcada 'failed')"
    except Exception as e:
        db.mark_execution_status(pid, "failed", f"error de ejecucion: {e}")
        return f"FAIL {ticker} — {e}"

    if not fill["filled"]:
        db.mark_execution_status(pid, "failed", "orden no ejecutada (no fill)")
        return f"FAIL {ticker} — orden sin fill"

    today = date.today().isoformat()
    db.record_fill(
        date=today,
        ticker=ticker,
        action=proposal["action"],
        quantity=fill["fill_quantity"],
        price=fill["fill_price"],
        decision_id=pid,
    )
    db.mark_execution_status(pid, "executed")
    return (
        f"OK {ticker} {proposal['action']} {fill['fill_quantity']} @ {fill['fill_price']}"
    )


def run(dry_run: bool = False) -> None:
    if KILL_SWITCH_FILE.exists():
        msg = (
            "Ataraxia executor: KILL SWITCH activo — no se ejecuta nada. "
            f"(borrar {KILL_SWITCH_FILE} para reactivar)"
        )
        print(msg)
        notifier.notify_safe(msg)
        return

    flushed = db.flush_pending_writes()
    if flushed:
        print(f"Reenviadas {flushed} escrituras encoladas de corridas anteriores.")

    proposals = db.get_pending_proposals()
    if not proposals:
        print("Sin propuestas pendientes.")
        return

    lines = [process_proposal(p, dry_run=dry_run) for p in proposals]
    report = "Ataraxia — reporte de ejecucion:\n" + "\n".join(f"- {l}" for l in lines)
    print(report)
    if not dry_run:
        notifier.notify_safe(report)


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
