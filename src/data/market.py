"""
Datos de mercado: precios actuales y benchmark (S&P 500) via FMP.

Endpoints verificados (23 jul 2026):
  - /stable/quote?symbol=       (precio actual, cualquier ticker o indice como ^GSPC)
  - /stable/historical-price-eod/full?symbol=   (historico OHLCV, incluye indices)

/stable/quote resulto estar bloqueado por ticker en el plan actual de FMP — no solo para
analyst-estimates (ver src/data/fundamentals.py): 0/14 tickers reales del S&P 500 probados
fuera de un puñado de mega-caps conocidos devolvieron 200 (verificado en vivo el 26 de agosto
de 2026). get_price() ahora scrapea stockanalysis.com/stocks/<ticker>/ en su lugar — mismo
sustituto que get_analyst_forecast(), consolidado aca porque todos los callers reales
(src/reporting/portfolio.py, src/reporting/performance.py, scripts/brain_fundamentals.py)
solo pasan tickers de acciones en cartera/candidatas, nunca el simbolo de indice ^GSPC (ese
camino sigue via _get()/get_sp500_historical(), sin tocar).

Fase 1.
"""

import re

import requests

from src.config import require_fmp_key
from src.data.cache import cached_call

BASE_URL = "https://financialmodelingprep.com/stable"
SP500_INDEX_SYMBOL = "^GSPC"

# Fuente primaria: stockanalysis.com embebe un objeto de cotizacion estructurado en el HTML
# (`quote:{c:...,p:<precio>,...}`), que es dato, no texto de presentacion. Se prefiere sobre
# _PRICE_RE porque no depende del copy de la pagina: verificado el 7 de septiembre de 2026
# contra ATO/AVY/AWK/BALL/AVGO/AAPL/BRK.B/AMD (8/8), incluyendo tickers con punto.
_QUOTE_PRICE_RE = re.compile(r"quote:\{[^}]*?\bp:(-?[\d.]+)")

# Respaldo: el precio renderizado en el encabezado. Depende del literal "At close:", que NO
# aparece en todos los tickers — ATO/AVY/AWK/BALL renderizan el precio y van directo a la
# fecha, sin esa frase, y por eso fallaban con un RuntimeError pese a tener precio valido
# (diagnosticado el 7 de septiembre de 2026). Se conserva solo como segunda linea de defensa
# por si cambia el formato del objeto embebido.
_PRICE_RE = re.compile(r"([\d,]+\.\d+)\s+[+-][\d.]+\s+\([+-]?[\d.]+%\)\s+At close:")


def _get(path: str, params: dict | None = None) -> dict | list:
    params = dict(params or {})
    params["apikey"] = require_fmp_key()
    resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_price(ticker: str) -> float:
    """Precio actual de una accion, via scraping de stockanalysis.com (ver nota arriba —
    /stable/quote de FMP esta bloqueado para la mayoria de tickers reales en el plan actual).
    Lanza RuntimeError si la pagina cargo pero el patron de precio no matcheo (probable
    cambio de formato) — no confundir con un ticker invalido, que ya falla antes via
    raise_for_status()."""
    def fetch():
        resp = requests.get(
            f"https://stockanalysis.com/stocks/{ticker.lower()}/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; AtaraxiaResearchBot/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()

        # Primero el objeto de cotizacion embebido (sobre el HTML crudo, no sobre el texto
        # sin tags — el literal vive en un <script>).
        match = _QUOTE_PRICE_RE.search(resp.text)
        if match:
            return {"price": float(match.group(1))}

        # Respaldo sobre el texto renderizado.
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", resp.text))
        match = _PRICE_RE.search(text)
        if not match:
            raise RuntimeError(
                f"No se pudo extraer el precio de {ticker} desde stockanalysis.com/stocks/"
                f"{ticker.lower()}/ — fallaron tanto el objeto de cotizacion embebido como el "
                f"precio renderizado, asi que la pagina probablemente cambio de formato. "
                f"Revisar _QUOTE_PRICE_RE y _PRICE_RE en src/data/market.py."
            )
        return {"price": float(match.group(1).replace(",", ""))}
    result = cached_call("price_scraped", {"ticker": ticker}, fetch)
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
