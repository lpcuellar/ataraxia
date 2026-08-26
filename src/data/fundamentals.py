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

Verificado en vivo el 26 de agosto de 2026: sp500-constituent y company-screener devuelven
402 "Restricted Endpoint" en el plan actual (los otros cuatro endpoints funcionan bien).
get_sp500_constituents()/screen_by_market_cap() se dejan tal cual (utiles si se sube de plan
mas adelante), pero src/data/universe.py ya no las llama — usa get_sp500_with_market_cap()
en su lugar, ver abajo.

Fase 1.
"""

import re

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


# ---------------------------------------------------------------------------
# Sustituto de sp500-constituent + company-screener mientras esten bloqueados en el plan
# actual de FMP (402 "Restricted Endpoint", verificado el 26 de agosto de 2026).
# ---------------------------------------------------------------------------

SP500_LIST_URL = "https://stockanalysis.com/list/sp-500-stocks/"

# stockanalysis.com embebe los datos como un literal de objeto JS dentro del HTML (no JSON
# valido), asi que se extraen con regex en vez de un parser JSON. Verificado en vivo: matchea
# las 503 filas de la pagina (500 compañias, 3 con dos clases de accion listadas por separado
# — p.ej. GOOG/GOOGL). Fragil frente a un rediseño de la pagina — por eso get_sp500_with_
# market_cap() lanza ruidosamente si el conteo de filas es sospechosamente bajo, en vez de
# devolver un pool silenciosamente incompleto.
_SP500_ROW_RE = re.compile(r'"([A-Z.\-]+)",n:"([^"]+)",marketCap:(\d+)')


def get_sp500_with_market_cap() -> list[dict]:
    """Constituyentes del S&P 500 con market cap exacto, via scraping de stockanalysis.com —
    reemplaza a sp500_constituents + screen_by_market_cap juntos mientras esos dos endpoints
    de FMP esten bloqueados. robots.txt de stockanalysis.com no restringe esta pagina para
    user-agents genericos (revisado el 26 de agosto de 2026); esto la consulta una vez cada
    ~30 dias (ver refresh_pool_if_stale en src/data/universe.py), no en volumen.

    Devuelve dicts con las mismas claves que build_quantitative_pool() ya espera de las
    fuentes de FMP ("symbol"), mas "marketCap" para filtrar en universe.py."""
    def fetch():
        resp = requests.get(
            SP500_LIST_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AtaraxiaResearchBot/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        rows = _SP500_ROW_RE.findall(resp.text)
        if len(rows) < 490:
            raise RuntimeError(
                f"Solo se encontraron {len(rows)} filas al scrapear {SP500_LIST_URL} "
                f"(esperado ~500-505). La pagina probablemente cambio de formato — revisar "
                f"el regex _SP500_ROW_RE en src/data/fundamentals.py."
            )
        return [
            {"symbol": symbol, "name": name, "marketCap": int(market_cap)}
            for symbol, name, market_cap in rows
        ]
    return cached_call("sp500_with_market_cap", {}, fetch)
