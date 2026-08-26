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

analyst-estimates resulto estar bloqueado por ticker (no por endpoint completo) — funciona
para varios large-caps conocidos pero rechaza la mayoria de tickers reales del S&P 500, de
forma inconsistente incluso entre clases de accion de la misma empresa (GOOG bloqueado,
GOOGL no). get_analyst_estimates() se deja tal cual; get_analyst_forecast() (scraping,
ver abajo) es lo que src/data/universe.py y scripts/brain_fundamentals.py usan ahora.

Fase 1.
"""

import re
from io import StringIO

import pandas as pd
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


# ---------------------------------------------------------------------------
# Sustituto de analyst-estimates mientras siga bloqueado por ticker en el plan actual de FMP
# (402 "Premium Query Parameter", verificado el 26 de agosto de 2026).
# ---------------------------------------------------------------------------

def get_analyst_forecast(ticker: str) -> dict:
    """Estimados de analistas via scraping de stockanalysis.com/stocks/<ticker>/forecast/.

    La tabla anual de esa pagina trae una fila "No. Analysts" junto a Revenue/EPS por año
    fiscal (columnas mas alla del año fiscal actual+1 quedan marcadas "Upgrade" — fuera del
    free tier de ESE sitio, no accesibles). Se usa la columna mas reciente con un valor real
    de "No. Analysts" — cae distinto por ticker segun el cierre de año fiscal de cada empresa
    (p.ej. NVDA cae en FY 2027 mientras AAPL cae en FY 2026), por eso se busca por contenido
    en vez de asumir una columna fija.

    num_analysts=0 si no se encuentra ninguna columna con dato real — se trata igual que "sin
    cobertura medible" (mismo comportamiento que antes con el campo roto de FMP), no como
    error. Un error real (tabla no encontrada, ticker sin pagina de forecast) se lanza
    ruidosamente en cambio de devolver un resultado silenciosamente vacio."""
    def fetch():
        resp = requests.get(
            f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; AtaraxiaResearchBot/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))

        fy_table = None
        for t in tables:
            first_col = t.iloc[:, 0].astype(str)
            if first_col.str.contains("No. Analysts").any():
                fy_table = t
                break
        if fy_table is None:
            raise RuntimeError(
                f"No se encontro la tabla de pronostico anual para {ticker} en "
                f"stockanalysis.com/stocks/{ticker.lower()}/forecast/ — la pagina "
                f"probablemente cambio de formato, revisar get_analyst_forecast()."
            )

        fy_table = fy_table.set_index(fy_table.columns[0])
        analysts_row = fy_table.loc["No. Analysts"]
        revenue_row = fy_table.loc["Revenue"] if "Revenue" in fy_table.index else None
        eps_row = fy_table.loc["EPS"] if "EPS" in fy_table.index else None

        chosen_col = None
        for col in reversed(fy_table.columns):
            val = str(analysts_row[col])
            if val.replace(".", "", 1).isdigit():
                chosen_col = col
                break

        if chosen_col is None:
            return {
                "symbol": ticker.upper(), "fiscal_year": None, "num_analysts": 0,
                "revenue": None, "eps": None,
            }

        return {
            "symbol": ticker.upper(),
            "fiscal_year": chosen_col[0] if isinstance(chosen_col, tuple) else chosen_col,
            "num_analysts": int(float(analysts_row[chosen_col])),
            "revenue": revenue_row[chosen_col] if revenue_row is not None else None,
            "eps": eps_row[chosen_col] if eps_row is not None else None,
        }
    return cached_call("analyst_forecast", {"ticker": ticker}, fetch)


# ---------------------------------------------------------------------------
# Sustituto de key-metrics + ratios mientras sigan bloqueados por ticker en el plan actual de
# FMP (402, verificado el 26 de agosto de 2026 — mismo patron que quote/analyst-estimates).
# ---------------------------------------------------------------------------

def _first_data_column(df):
    """Las tablas de stockanalysis.com ponen el periodo mas reciente (TTM/Current) en la
    primera columna de datos, justo despues de la columna de etiqueta — a diferencia de la
    tabla de pronosticos (get_analyst_forecast), aca esa columna siempre trae un valor real,
    nunca "Upgrade", asi que no hace falta buscar la primera columna valida."""
    return df.columns[1]


def get_valuation_metrics(ticker: str) -> dict:
    """P/E, forward P/E, P/S, ROIC y margenes, via scraping de dos paginas de
    stockanalysis.com (financials/ratios/ para multiplos y ROIC, financials/ para margenes) —
    reemplaza a get_key_metrics()/get_ratios() de FMP para estos campos especificos mientras
    esos endpoints sigan bloqueados por ticker en el plan actual."""
    def fetch():
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AtaraxiaResearchBot/1.0)"}
        result = {"symbol": ticker.upper()}

        resp = requests.get(
            f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/ratios/",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        pe_table = next((t for t in tables if t.iloc[:, 0].astype(str).eq("PE Ratio").any()), None)
        roic_table = next(
            (t for t in tables if t.iloc[:, 0].astype(str).str.contains("ROIC", regex=False).any()),
            None,
        )
        if pe_table is None or roic_table is None:
            raise RuntimeError(
                f"No se encontraron las tablas de multiplos/ROIC para {ticker} en "
                f"stockanalysis.com/stocks/{ticker.lower()}/financials/ratios/ — la pagina "
                f"probablemente cambio de formato, revisar get_valuation_metrics()."
            )
        pe_table = pe_table.set_index(pe_table.columns[0])
        roic_table = roic_table.set_index(roic_table.columns[0])
        col = _first_data_column(pe_table)
        result["pe_ratio"] = pe_table.loc["PE Ratio", col]
        result["forward_pe"] = pe_table.loc["Forward PE", col]
        result["ps_ratio"] = pe_table.loc["PS Ratio", col]
        roic_col = _first_data_column(roic_table)
        roic_row = next(i for i in roic_table.index if "ROIC" in i)
        result["roic"] = roic_table.loc[roic_row, roic_col]

        resp = requests.get(
            f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        margin_table = next(
            (t for t in tables if t.iloc[:, 0].astype(str).eq("Gross Margin").any()), None
        )
        if margin_table is None:
            raise RuntimeError(
                f"No se encontro la tabla de margenes para {ticker} en "
                f"stockanalysis.com/stocks/{ticker.lower()}/financials/ — la pagina "
                f"probablemente cambio de formato, revisar get_valuation_metrics()."
            )
        margin_table = margin_table.set_index(margin_table.columns[0])
        mcol = _first_data_column(margin_table)
        result["gross_margin"] = margin_table.loc["Gross Margin", mcol]
        result["operating_margin"] = margin_table.loc["Operating Margin", mcol]
        result["net_margin"] = margin_table.loc["Profit Margin", mcol]

        return result
    return cached_call("valuation_metrics", {"ticker": ticker}, fetch)
