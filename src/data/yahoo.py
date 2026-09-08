"""
Cliente de datos via Yahoo Finance (libreria yfinance) — segunda fuente independiente,
alternativa al scraping de stockanalysis.com y a los endpoints bloqueados de FMP.

Motivacion (7 de septiembre de 2026): el primer lote real de 18 candidatos perdio 4 tickers
(ATO, AVY, AWK, BALL — 22% del lote) porque get_price() dependia de un literal de texto
("At close:") que esas paginas no renderizan. Yahoo devuelve datos estructurados, no HTML de
presentacion, asi que no es vulnerable a ese tipo de fallo. Verificado en vivo ese mismo dia:
los 4 tickers que fallaban devuelven precio correcto aca (ATO $167.56, identico al que la
pagina mostraba y el regex rechazaba).

Ventaja adicional sobre el scraper: los margenes vienen poblados para TODOS los sectores.
get_valuation_metrics() de fundamentals.py devuelve None en margenes para aseguradoras
(ACGL/AFL/AIG) y en ROIC para utilities (AEE/AEP), porque stockanalysis.com no publica esas
filas para esos sectores. Yahoo si las trae (verificado contra ACGL y AEE).

Este modulo NO reemplaza a fundamentals.py/market.py — se agrega al lado. La decision de
cual es la fuente primaria de cada campo se toma en los callers; ver la nota sobre
forward_pe abajo, que es justamente un caso donde las dos fuentes no son intercambiables.

Sin API key: yfinance consulta los endpoints publicos de Yahoo. Sujeto a rate limiting si se
abusa, por eso todo pasa por cached_call (una vez al dia por ticker, igual que el resto).

Fase 1.
"""

import yfinance as yf

from src.data.cache import cached_call


def _info(ticker: str) -> dict:
    """Bloque `info` crudo de yfinance, cacheado por dia. Es una sola llamada de red que trae
    precio, multiplos, margenes y cobertura de analistas juntos — por eso los getters de abajo
    comparten esta cache en vez de pedir cada uno lo suyo."""
    def fetch():
        data = yf.Ticker(ticker).info
        if not data or data.get("currentPrice") is None and data.get("regularMarketPrice") is None:
            raise RuntimeError(
                f"Yahoo Finance no devolvio datos de cotizacion para {ticker}. Puede ser un "
                f"ticker invalido, un cambio en la API de yfinance, o rate limiting — "
                f"revisar _info() en src/data/yahoo.py."
            )
        return data
    return cached_call("yahoo_info", {"ticker": ticker}, fetch)


def get_price(ticker: str) -> float:
    """Precio actual. Mismo contrato que market.get_price() (float, lanza ruidosamente si no
    hay dato) para que sea sustituible sin tocar a los callers."""
    info = _info(ticker)
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None:
        raise RuntimeError(f"Yahoo Finance no trae precio para {ticker}.")
    return float(price)


def get_valuation_metrics(ticker: str) -> dict:
    """Multiplos y margenes, con las MISMAS claves que fundamentals.get_valuation_metrics()
    para que ambas fuentes sean comparables campo a campo.

    Dos diferencias de fondo con la version de stockanalysis.com, que NO son bugs de ninguna
    de las dos y por eso no se "arreglan" aca:

    1. forward_pe usa una definicion distinta de "forward". Yahoo lo calcula sobre forwardEps
       (el año fiscal SIGUIENTE: para AVGO, EPS 19.37 -> P/E 18.47), mientras stockanalysis.com
       reporta 20.68. El EPS del año fiscal CORRIENTE lo trae Yahoo por separado en
       epsCurrentYear (11.64 para AVGO -> P/E 30.75). Las tres cifras son correctas sobre bases
       distintas. Se expone forward_eps y eps_current_year junto al multiplo para que quien
       lea sepa sobre que año esta parado, en vez de comparar peras con manzanas.
       Verificado el 7 de septiembre de 2026.

    2. roic no existe en Yahoo. Se deja en None deliberadamente y se expone returnOnEquity /
       returnOnAssets aparte (roe, roa) — son metricas distintas, no sustitutos. El ROIC sigue
       viniendo de stockanalysis.com. Poner ROE en el campo roic seria mezclar definiciones,
       exactamente el error que produjo el bug del forward P/E de FY cerrado.

    Los margenes llegan como fraccion (0.7551) y se convierten a porcentaje redondeado para
    igualar el formato de la otra fuente ("75.52%")."""
    info = _info(ticker)

    def pct(value):
        return None if value is None else f"{value * 100:.2f}%"

    return {
        "symbol": ticker.upper(),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "ps_ratio": info.get("priceToSalesTrailing12Months"),
        # Yahoo no publica ROIC. Ver nota 2 del docstring.
        "roic": None,
        "gross_margin": pct(info.get("grossMargins")),
        "operating_margin": pct(info.get("operatingMargins")),
        "net_margin": pct(info.get("profitMargins")),
        # Campos extra, sin equivalente en la otra fuente:
        "roe": pct(info.get("returnOnEquity")),
        "roa": pct(info.get("returnOnAssets")),
        "forward_eps": info.get("forwardEps"),
        "eps_current_year": info.get("epsCurrentYear"),
        "trailing_eps": info.get("trailingEps"),
    }


def get_analyst_forecast(ticker: str) -> dict:
    """Cobertura y estimados de analistas, con las mismas claves que
    fundamentals.get_analyst_forecast().

    num_analysts=0 cuando Yahoo no reporta cobertura — se trata como "sin cobertura medible",
    igual que la otra fuente, no como error.

    Nota: Yahoo no expone el año fiscal etiquetado del estimado en `info`, asi que fiscal_year
    queda en None y el EPS reportado es el del año corriente (epsCurrentYear). La version de
    stockanalysis.com si trae la etiqueta de año fiscal — si lo que importa es saber SOBRE QUE
    AÑO es el estimado, esa sigue siendo la fuente correcta."""
    info = _info(ticker)
    num = info.get("numberOfAnalystOpinions")

    return {
        "symbol": ticker.upper(),
        "fiscal_year": None,
        "num_analysts": int(num) if num else 0,
        "revenue": info.get("totalRevenue"),
        "eps": info.get("epsCurrentYear"),
    }


def get_company_profile(ticker: str) -> dict:
    """Perfil de negocio — sector, industria, empleados y resumen largo. Sin equivalente en
    las otras fuentes del proyecto: cubre el contexto cualitativo que hasta ahora el brain
    tenia que buscar por web search."""
    info = _info(ticker)
    return {
        "symbol": ticker.upper(),
        "name": info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "employees": info.get("fullTimeEmployees"),
        "country": info.get("country"),
        "website": info.get("website"),
        "market_cap": info.get("marketCap"),
        "beta": info.get("beta"),
        "summary": info.get("longBusinessSummary"),
    }
