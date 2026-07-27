"""
Datos de mercado: precios actuales y benchmark (S&P 500) via FMP.

Endpoints verificados (23 jul 2026):
  - /stable/quote?symbol=       (precio actual, cualquier ticker o indice como ^GSPC)
  - /stable/historical-price-eod/full?symbol=   (historico OHLCV, incluye indices)

Fase 1.
"""

import requests

from src.config import require_fmp_key
from src.data.cache import cached_call

BASE_URL = "https://financialmodelingprep.com/stable"
SP500_INDEX_SYMBOL = "^GSPC"


def _get(path: str, params: dict | None = None) -> dict | list:
    params = dict(params or {})
    params["apikey"] = require_fmp_key()
    resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_price(ticker: str) -> float:
    """Precio actual de un ticker (o indice)."""
    def fetch():
        data = _get("quote", {"symbol": ticker})
        if isinstance(data, list) and data:
            return {"price": data[0].get("price")}
        return {"price": None}
    result = cached_call("quote", {"ticker": ticker}, fetch)
    return result["price"]


def get_sp500_historical(start_date: str, end_date: str) -> list[dict]:
    """OHLCV historico del S&P 500 en el rango dado. Usado para calcular el retorno del
    benchmark en la misma ventana que el fondo (ver PROJECT_PLAN.md Seccion 1, metrica de
    alpha relativo)."""
    def fetch():
        return _get(
            "historical-price-eod/full",
            {"symbol": SP500_INDEX_SYMBOL, "from": start_date, "to": end_date},
        )
    return cached_call(
        "sp500_historical", {"start": start_date, "end": end_date}, fetch
    )


def get_sp500_return(start_date: str, end_date: str) -> float:
    """Retorno porcentual del S&P 500 entre dos fechas. Falla explicitamente (en vez de
    devolver 0.0) si no hay suficientes datos, para no ensuciar la metrica de alpha con un
    numero silenciosamente incorrecto."""
    history = get_sp500_historical(start_date, end_date)
    if not history or len(history) < 2:
        raise ValueError(
            f"No hay suficientes datos historicos del S&P 500 entre {start_date} y "
            f"{end_date} para calcular el retorno del benchmark."
        )
    # FMP devuelve el historico ordenado de mas reciente a mas antiguo.
    closes = [row["close"] for row in history if "close" in row]
    latest_close = closes[0]
    earliest_close = closes[-1]
    return (latest_close - earliest_close) / earliest_close
