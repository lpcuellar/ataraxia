"""
Cliente de datos fundamentales — Financial Modeling Prep (FMP), API "stable".

Decision documentada en BUILD_PLAN.md: FMP elegido sobre Polygon.io (sin tier gratis) y
Finnhub (fuerte en tiempo real, irrelevante para revision diaria). Free tier: 250
llamadas/dia — de sobra para ~30-50 tickers/dia.

Endpoints verificados contra la documentacion oficial (site.financialmodelingprep.com/
developer/docs/stable/*) el 23 de julio de 2026:
  - /stable/quote?symbol=
  - /stable/key-metrics?symbol=
  - /stable/ratios?symbol=
  - /stable/analyst-estimates?symbol=&period=annual
  - /stable/sp500-constituent
  - /stable/company-screener?marketCapMoreThan=...

Fase 1.
"""

import requests

from src.config import require_fmp_key
from src.data.cache import cached_call

BASE_URL = "https://financialmodelingprep.com/stable"


def _get(path: str, params: dict | None = None) -> dict | list:
    """GET generico contra la API stable de FMP. Lanza excepcion si la respuesta no es 200 —
    mejor fallar ruidosamente aqui que dejar que Ataraxia razone sobre datos vacios/erroneos
    sin darse cuenta."""
    params = dict(params or {})
    params["apikey"] = require_fmp_key()
    resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_key_metrics(ticker: str) -> dict:
    """Multiplos de valuation clave (P/E, P/S, retorno sobre capital, etc.)."""
    def fetch():
        data = _get("key-metrics", {"symbol": ticker})
        return data[0] if isinstance(data, list) and data else {}
    return cached_call("key_metrics", {"ticker": ticker}, fetch)


def get_ratios(ticker: str) -> dict:
    """Margenes, liquidez, eficiencia — usado para el criterio de 'poder de fijacion de
    precios' del framework de screening."""
    def fetch():
        data = _get("ratios", {"symbol": ticker})
        return data[0] if isinstance(data, list) and data else {}
    return cached_call("ratios", {"ticker": ticker}, fetch)


def get_analyst_estimates(ticker: str, limit: int = 8) -> list[dict]:
    """Estimados de crecimiento futuro (ingresos, EPS) — proxy de backlog/visibilidad
    cuando no hay guidance explicito de la empresa."""
    def fetch():
        return _get("analyst-estimates", {"symbol": ticker, "period": "annual", "limit": limit})
    return cached_call("analyst_estimates", {"ticker": ticker, "limit": limit}, fetch)


def get_sp500_constituents() -> list[dict]:
    """Lista completa de constituyentes del S&P 500 con sector/sub-sector — base del filtro
    cuantitativo del universo de candidatos (ver src/data/universe.py)."""
    def fetch():
        return _get("sp500-constituent")
    return cached_call("sp500_constituents", {}, fetch)


def screen_by_market_cap(min_market_cap_usd: float, limit: int = 1000) -> list[dict]:
    """Screener cuantitativo — usado para el filtro objetivo de la Etapa 1 del embudo de
    universo (sin juicio humano, ver BUILD_PLAN.md)."""
    def fetch():
        return _get(
            "company-screener",
            {
                "marketCapMoreThan": min_market_cap_usd,
                "isActivelyTrading": "true",
                "limit": limit,
            },
        )
    return cached_call(
        "screener", {"min_market_cap": min_market_cap_usd, "limit": limit}, fetch
    )
