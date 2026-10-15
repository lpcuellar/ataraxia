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


def get_sp500_close_on(as_of: str) -> float | None:
    """Cierre del S&P 500 en una fecha dada (YYYY-MM-DD), para poblar portfolio_snapshots.

    Via FMP primero por consistencia con get_sp500_historical, pero ese endpoint esta
    bloqueado en el plan actual (ver docstring del modulo) incluso para el indice en
    algunos rangos, asi que yfinance ^GSPC es el fallback que de hecho funciona —
    mismo patron que scripts/compute_performance.py._sp500_close().

    Devuelve None (no lanza) si ninguna fuente tiene el dato: un snapshot sin benchmark
    sigue siendo utilizable para ver el portafolio, asi que no vale la pena hacer fallar
    la carga completa por esto. El caller decide si eso es aceptable."""
    from datetime import date, timedelta

    def fetch():
        target = date.fromisoformat(as_of)
        try:
            history = get_sp500_historical(as_of, as_of)
            closes = [row["close"] for row in history if "close" in row]
            if closes:
                return {"close": closes[0]}
        except Exception:
            pass

        try:
            import warnings

            import yfinance as yf

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Ventana de +1 dia: Yahoo indexa por la fecha de la sesion, y un end
                # exclusivo igual al start no devuelve filas.
                hist = yf.Ticker(SP500_INDEX_SYMBOL).history(
                    start=as_of, end=(target + timedelta(days=1)).isoformat()
                )
            if not hist.empty:
                return {"close": float(hist["Close"].iloc[-1])}
        except Exception:
            pass

        return {"close": None}

    result = cached_call("sp500_close_on", {"as_of": as_of}, fetch)
    return result["close"]


def get_ticker_close_on(ticker: str, as_of: str, lookback_days: int = 5) -> float | None:
    """Cierre historico de CUALQUIER ticker en una fecha dada, via yfinance — para
    reconstruir snapshots historicos de portafolio a partir de transacciones (scripts/
    backfill_historical_snapshots.py). FMP esta bloqueado para tickers individuales (ver
    docstring del modulo), asi que yfinance es la unica fuente, no un fallback.

    Si as_of cae en fin de semana o feriado (frecuente: las fechas de deposito de Schwab
    no siempre son dias habiles), busca hacia atras hasta lookback_days el ultimo cierre
    disponible — nunca hacia adelante, para no usar un precio que todavia no existia en
    esa fecha."""
    from datetime import date, timedelta

    def fetch():
        import warnings

        import yfinance as yf

        target = date.fromisoformat(as_of)
        start = target - timedelta(days=lookback_days)
        end = target + timedelta(days=1)  # end exclusivo en yfinance
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                hist = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat())
            if hist.empty:
                return {"close": None}
            return {"close": float(hist["Close"].iloc[-1])}
        except Exception:
            return {"close": None}

    result = cached_call("ticker_close_on", {"ticker": ticker.upper(), "as_of": as_of}, fetch)
    return result["close"]


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
