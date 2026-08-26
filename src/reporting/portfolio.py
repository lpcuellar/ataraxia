"""
Reconstruccion del PortfolioState del validator a partir de la verdad de la DB.

Compartido entre el executor (`src/executor/run_executor.py`) y las herramientas del brain
(`scripts/brain_*.py`) — ambos necesitan la misma vision del portafolio, y ninguno de los dos
puede fabricarla: `executed_trades`/`cash_events` son las unicas tablas que definen que hay
realmente en la cuenta (ver supabase/migrations/20260727120000_executor_tables.sql).
"""

from src.data import market
from src.db import models as db
from src.guardrails import validator as v


def build_portfolio_state() -> v.PortfolioState:
    """Reconstruye el PortfolioState del validator desde la verdad de la DB + precios
    actuales de FMP."""
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
