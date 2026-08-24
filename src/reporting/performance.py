"""
Metricas de performance de Ataraxia: alpha relativo vs. S&P 500, Sharpe ratio, drawdown.

Esta es la metrica de exito PRINCIPAL del proyecto (PROJECT_PLAN.md Seccion 1) y no existia
en codigo antes de esto — solo la tabla `performance` y el fetch del benchmark
(src/data/market.get_sp500_return). compute_daily_snapshot() es lo que las junta.

Simplificacion conocida — retorno del benchmark money-weighted simple, no time-weighted:
si hubo mas de un cash_event de tipo 'deposit' en fechas distintas, el equivalente de S&P
500 usa la fecha del PRIMER deposito para toda la serie (como si todo el capital hubiera
entrado ese dia). Correcto y suficiente para una cuenta que arranca con un solo deposito
(el caso actual); si el fondeo se vuelve mas complejo (varios depositos grandes en fechas
distintas) esto subestima o sobreestima el benchmark segun el timing — revisar entonces.

Sharpe ratio asume una tasa libre de riesgo de 0% — razonable como simplificacion para una
ventana corta de paper trading, no para evaluar la estrategia contra bonos en el largo plazo.
Requiere al menos MIN_POINTS_FOR_SHARPE puntos de historico (incluyendo el de hoy) para que
el desvio estandar signifique algo; devuelve None si no hay suficientes.
"""

import statistics
from datetime import date

from src.data import market
from src.db import models as db

MIN_POINTS_FOR_SHARPE = 5
TRADING_DAYS_PER_YEAR = 252


def compute_daily_snapshot(today: str | None = None) -> dict:
    """Arma el snapshot de performance de hoy. No lo guarda — el caller decide cuando
    persistirlo con db.log_performance_snapshot(**resultado). Lanza RuntimeError si todavia
    no hay ningun deposito registrado (no hay como calcular retorno sin saber desde cuando
    ni cuanto capital entro — ver scripts/log_manual_trade.py deposit)."""
    today = today or date.today().isoformat()

    account = db.get_account_state()
    fund_value = account["cash"]
    for ticker, holding in account["holdings"].items():
        price = market.get_price(ticker)
        if price is not None:
            fund_value += holding["quantity"] * price
        # Si el precio no esta disponible hoy, se omite esa posicion del NAV en vez de
        # reventar todo el snapshot — mejor un numero levemente incompleto que ninguno.

    deposits = db.get_cash_events(event_type="deposit")
    if not deposits:
        raise RuntimeError(
            "No hay ningun cash_event de tipo 'deposit' todavia — registra el capital "
            "inicial con: python scripts/log_manual_trade.py deposit --amount <monto>"
        )
    inception_date = min(d["date"].isoformat() if hasattr(d["date"], "isoformat") else d["date"]
                          for d in deposits)
    total_deposited = sum(float(d["amount"]) for d in deposits)

    sp500_return = market.get_sp500_return(inception_date, today)
    sp500_equivalent_value = total_deposited * (1 + sp500_return)

    cumulative_return_pct = (
        (fund_value - total_deposited) / total_deposited if total_deposited else 0.0
    )

    history = db.get_performance_history()
    fund_values = [float(row["fund_value"]) for row in history] + [fund_value]
    running_max = max(fund_values)
    current_drawdown_pct = (
        (fund_value - running_max) / running_max if running_max > 0 else 0.0
    )
    past_drawdowns = [float(row["current_drawdown_pct"]) for row in history]
    max_drawdown_pct = min(past_drawdowns + [current_drawdown_pct])

    sharpe_ratio = _compute_sharpe(fund_values)

    return dict(
        date=today,
        fund_value=fund_value,
        sp500_equivalent_value=sp500_equivalent_value,
        cumulative_return_pct=cumulative_return_pct,
        sp500_cumulative_return_pct=sp500_return,
        current_drawdown_pct=current_drawdown_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
    )


def _compute_sharpe(chronological_fund_values: list[float]) -> float | None:
    """chronological_fund_values debe venir ya en orden de fecha ascendente, terminando en
    el valor de hoy. None si no hay suficiente historico para que el numero signifique algo."""
    if len(chronological_fund_values) < MIN_POINTS_FOR_SHARPE:
        return None

    daily_returns = [
        (chronological_fund_values[i] - chronological_fund_values[i - 1])
        / chronological_fund_values[i - 1]
        for i in range(1, len(chronological_fund_values))
        if chronological_fund_values[i - 1] != 0
    ]
    if len(daily_returns) < MIN_POINTS_FOR_SHARPE - 1:
        return None

    stdev = statistics.stdev(daily_returns)  # desvio muestral, requiere n >= 2
    if stdev == 0:
        return None

    return (statistics.mean(daily_returns) / stdev) * (TRADING_DAYS_PER_YEAR ** 0.5)
