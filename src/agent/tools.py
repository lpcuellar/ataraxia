"""
Definiciones de tools que Ataraxia puede invocar via tool use de la API de Claude.

IMPORTANTE: propose_trade() NO ejecuta ordenes directamente. Pasa por
src/guardrails/validator.py antes de convertirse en una orden real contra IBKR. Ver el
principio de diseño "el LLM propone, el codigo decide" en BUILD_PLAN.md.

Stubs — implementar en Fase 1/2 (ver BUILD_PLAN.md).
"""

from typing import Literal


def get_portfolio() -> dict:
    """Devuelve las posiciones actuales desde IBKR: ticker, cantidad, costo promedio,
    valor de mercado actual, % del portafolio total."""
    raise NotImplementedError("Fase 3 — depende de src/broker/ibkr_client.py")


def get_fundamentals(ticker: str) -> dict:
    """Devuelve datos fundamentales desde Financial Modeling Prep: multiplos, crecimiento,
    margenes, estimados de analistas."""
    raise NotImplementedError("Fase 1 — depende de src/data/fundamentals.py")


def get_market_data(ticker: str) -> dict:
    """Devuelve precio actual y datos historicos basicos de un ticker."""
    raise NotImplementedError("Fase 1 — depende de src/data/market.py")


def web_search(query: str) -> list[dict]:
    """Usa la tool nativa de web search de la API de Claude para contexto cualitativo
    (backlog, guidance, noticias) que no viene en la API de datos financieros."""
    raise NotImplementedError("Se configura como server tool nativo en la llamada a la API,"
                               " no requiere implementacion propia — ver Fase 2")


def propose_trade(
    ticker: str,
    action: Literal["buy", "sell"],
    qty: float,
    rationale: str,
    bear_case: str,
    bear_case_probability: float,
) -> dict:
    """Propone una operacion. NO ejecuta directamente — se valida contra los guardrails en
    src/guardrails/validator.py antes de convertirse en una orden real. Devuelve el
    resultado de la validacion (aprobado/rechazado + razon)."""
    raise NotImplementedError("Fase 2 — depende de src/guardrails/validator.py")


def log_review(ticker: str, summary: str) -> None:
    """Registra una revision de tesis sin accion (el caso mas comun en el dia a dia)."""
    raise NotImplementedError("Fase 3 — depende de src/db/models.py")
