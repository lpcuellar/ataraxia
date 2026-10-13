"""
Cliente de SEC EDGAR — fuente primaria de filings oficiales.

Por qué EDGAR y no scrapers de terceros: los 8-K, 10-K y 10-Q son documentos legales que
las empresas presentan bajo juramento. No hay mejor fuente para hechos materiales, estados
financieros completos y earnings releases. El API es público, gratuito y estable.

Lo que provee este módulo:
  - Mapeo ticker → CIK via company_tickers.json (cacheado 30 días)
  - Lista de filings recientes por tipo (8-K, 10-K, 10-Q)
  - Texto de documentos individuales (press releases, MD&A, transcripts)
  - Helpers de alto nivel: get_earnings_releases(), get_material_8k(), get_latest_10k_text()

Convención de items en 8-K:
  2.02 = Results of Operations (earnings release) — siempre tiene Ex-99.1 con datos financieros
  7.01 = Regulation FD Disclosure — a veces contiene transcript de earnings call
  8.01 = Other Events — idem
  1.01, 1.02 = acuerdos/terminaciones de contratos materiales
  2.01 = acquisitions/dispositions
  5.02 = cambios en management

Rate limiting: SEC pide máximo 10 requests/segundo. cached_call con TTL de 1 día es más que
suficiente para el patrón de uso de Ataraxia (una empresa a la vez, una vez por semana).
"""

import re
import time
from typing import Optional

import requests

from src.data.cache import cached_call

_SEC_HEADERS = {
    # SEC requiere User-Agent identificable. Ver https://www.sec.gov/os/accessing-edgar-data
    "User-Agent": "AtaraxiaResearch lpcuellar14@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

_EDGAR_HEADERS = {
    "User-Agent": "AtaraxiaResearch lpcuellar14@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

_SEC_BASE = "https://data.sec.gov"
_EDGAR_BASE = "https://www.sec.gov"

# Items de 8-K que indican earnings release o transcript
_EARNINGS_ITEMS = {"2.02", "7.01", "8.01"}

# Items de 8-K que indican eventos materiales (no earnings)
_MATERIAL_ITEMS = {"1.01", "1.02", "2.01", "5.02", "8.01", "9.01"}


def _get_sec(url: str, base: str = _SEC_BASE) -> dict | list | str:
    time.sleep(0.12)  # max ~8 req/s, bien por debajo del límite de 10
    resp = requests.get(url, headers=_SEC_HEADERS if "data.sec.gov" in url else _EDGAR_HEADERS,
                        timeout=20)
    resp.raise_for_status()
    ct = resp.headers.get("content-type", "")
    if "json" in ct:
        return resp.json()
    return resp.text


def get_cik(ticker: str) -> int:
    """Devuelve el CIK (Company Identifier) de un ticker en EDGAR.

    Usa el JSON maestro de SEC (company_tickers.json) que mapea ~12,000 empresas.
    Cacheado 30 días: el CIK de una empresa no cambia.

    Lanza KeyError si el ticker no está en el listado — puede ser una empresa muy pequeña
    o un ADR sin registros en EDGAR."""
    def fetch():
        data = requests.get(
            f"{_EDGAR_BASE}/files/company_tickers.json",
            headers=_EDGAR_HEADERS,
            timeout=20,
        ).json()
        # El JSON está indexado 0..N, cada valor tiene cik_str, ticker, title
        mapping = {v["ticker"].upper(): v["cik_str"] for v in data.values()}
        return mapping

    mapping = cached_call("edgar_ticker_cik_map", {}, fetch)
    ticker = ticker.upper()
    if ticker not in mapping:
        raise KeyError(
            f"Ticker {ticker!r} no encontrado en el directorio de EDGAR. "
            f"Puede ser una empresa sin obligación de reporte en SEC (privada, muy pequeña, "
            f"o listada solo en mercados extranjeros sin ADR registrado)."
        )
    return int(mapping[ticker])


def get_recent_filings(ticker: str, form_type: str, days: int = 180) -> list[dict]:
    """Lista de filings recientes del tipo dado.

    Devuelve dicts con: accession, filing_date, form, items, primary_doc.
    'items' es una lista de strings (ej. ['2.02', '9.01']) para 8-K, vacío para 10-K/10-Q.

    days controla cuántos días hacia atrás se busca. El API de EDGAR devuelve los últimos
    ~1,000 filings de cualquier tipo; days filtra por fecha."""
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    def fetch():
        cik = get_cik(ticker)
        cik_padded = f"CIK{cik:010d}"
        data = _get_sec(f"{_SEC_BASE}/submissions/{cik_padded}.json")

        recent = data["filings"]["recent"]
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        items_list = recent.get("items", [""] * len(forms))
        primary_docs = recent.get("primaryDocument", [""] * len(forms))

        results = []
        for form, date_str, acc, items_raw, primary_doc in zip(
            forms, dates, accessions, items_list, primary_docs
        ):
            if form != form_type:
                continue
            if date_str < cutoff:
                continue
            # items viene como string "2.02,9.01" o "" — normalizar a lista
            items = [i.strip() for i in items_raw.split(",") if i.strip()] if items_raw else []
            results.append({
                "accession": acc,
                "filing_date": date_str,
                "form": form,
                "items": items,
                "primary_doc": primary_doc,
                "cik": cik,
            })
        return results

    return cached_call(
        "edgar_filings",
        {"ticker": ticker.upper(), "form_type": form_type, "days": days},
        fetch,
    )


def get_filing_document(cik: int, accession: str, filename: str) -> str:
    """Descarga el texto de un documento dentro de un filing.

    accession formato: '0000320193-26-000018' (con guiones)
    filename: nombre del archivo dentro del filing (ej. 'a8-kex991q3202606272026.htm')

    Devuelve el texto plano (HTML o txt según el archivo). Para HTML, limpiar tags
    antes de pasarlo al LLM."""
    acc_clean = accession.replace("-", "")
    url = f"{_EDGAR_BASE}/Archives/edgar/data/{cik}/{acc_clean}/{filename}"
    return _get_sec(url)


def _strip_html(html: str) -> str:
    """Limpieza básica de HTML a texto plano para pasarlo al LLM."""
    # Quitar scripts y style
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Quitar tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Normalizar espacios
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get_exhibit_99_1(cik: int, accession: str) -> Optional[str]:
    """Busca y descarga el Exhibit 99.1 de un 8-K (press release con datos financieros).

    El exhibit 99.1 es donde está la tabla de resultados con detalle de revenue, EPS y
    guidance — mucho más útil que la portada del 8-K. Lo identifica por nombre de archivo
    (patrones comunes: ex991*.htm, ex99-1*.htm, exhibit99*.htm)."""
    acc_clean = accession.replace("-", "")
    index_url = (
        f"{_EDGAR_BASE}/Archives/edgar/data/{cik}/{acc_clean}/{accession}-index.htm"
    )
    try:
        html = _get_sec(index_url)
    except Exception:
        return None

    # Buscar links a exhibits 99.1 por nombre de archivo
    links = re.findall(
        r'href="(/Archives/edgar/data/[^"]+\.htm)"',
        html,
        re.IGNORECASE,
    )
    _EX991_RE = re.compile(r"ex99[-_]?1[^/]*\.htm$", re.IGNORECASE)
    for link in links:
        filename = link.split("/")[-1]
        if _EX991_RE.search(filename):
            try:
                full_url = f"{_EDGAR_BASE}{link}"
                resp = requests.get(
                    full_url, headers=_EDGAR_HEADERS, timeout=20
                )
                resp.raise_for_status()
                return resp.text
            except Exception:
                continue
    return None


def get_earnings_releases(ticker: str, count: int = 2) -> list[dict]:
    """Últimos N earnings releases (8-K item 2.02) con el texto del press release.

    El press release (Ex-99.1) contiene los estados financieros condensados y el guidance —
    es la fuente más directa para entender si un salto de earnings fue orgánico o por items
    extraordinarios. Mucho más confiable que una noticia de terceros.

    Devuelve lista de dicts con: filing_date, text (texto limpio del Exhibit 99.1)."""
    filings = get_recent_filings(ticker, "8-K", days=400)
    earnings = [f for f in filings if "2.02" in f["items"]][:count]

    results = []
    for f in earnings:
        try:
            # Intentar Exhibit 99.1 primero (el press release con datos financieros)
            raw = _get_exhibit_99_1(f["cik"], f["accession"])
            if not raw and f["primary_doc"]:
                raw = get_filing_document(f["cik"], f["accession"], f["primary_doc"])
            if not raw:
                raise ValueError("no se encontró documento del earnings release")
            text = _strip_html(raw) if "<" in raw[:200] else raw
            # Limitar a 10,000 chars — suficiente para tablas de resultados y guidance
            results.append({
                "filing_date": f["filing_date"],
                "accession": f["accession"],
                "text": text[:10000],
            })
        except Exception as exc:
            results.append({
                "filing_date": f["filing_date"],
                "accession": f["accession"],
                "text": f"[error al descargar: {type(exc).__name__}: {exc}]",
            })
    return results


def get_material_8k(ticker: str, days: int = 180) -> list[dict]:
    """8-K de eventos materiales (no earnings) de los últimos N días.

    Filtra 8-K que contengan items de eventos materiales: acuerdos importantes,
    acquisitions, cambios de management, etc. Excluye los earnings-only (solo 2.02 + 9.01).

    Devuelve lista de dicts con: filing_date, items, summary (primera línea del doc)."""
    filings = get_recent_filings(ticker, "8-K", days=days)

    results = []
    for f in filings:
        item_set = set(f["items"])
        # Excluir si SOLO tiene items de earnings (2.02, 9.01) sin otros materiales
        non_earnings = item_set - {"2.02", "9.01"}
        if not non_earnings:
            continue
        # Solo incluir si tiene al menos un item realmente material
        if not (non_earnings & _MATERIAL_ITEMS):
            continue

        try:
            if f["primary_doc"]:
                raw = get_filing_document(f["cik"], f["accession"], f["primary_doc"])
                text = _strip_html(raw) if raw.strip().startswith("<") else raw
                # Solo las primeras 1,500 chars — suficiente para saber de qué trata
                summary = text[:1500]
            else:
                summary = "[documento principal no disponible]"
        except Exception as exc:
            summary = f"[error: {type(exc).__name__}]"

        results.append({
            "filing_date": f["filing_date"],
            "items": f["items"],
            "summary": summary,
        })
    return results


def get_latest_10k_text(ticker: str, max_chars: int = 20000) -> dict:
    """Texto del 10-K más reciente, limitado a max_chars.

    Prioriza las secciones más útiles para el análisis: Item 1 (Business), Item 7 (MD&A),
    y los estados financieros condensados. El 10-K completo puede tener 200+ páginas —
    max_chars controla cuánto se pasa al LLM.

    Devuelve dict con: filing_date, text."""
    filings = get_recent_filings(ticker, "10-K", days=400)
    if not filings:
        return {"filing_date": None, "text": "No se encontró 10-K en los últimos 400 días."}

    latest = filings[0]
    try:
        if not latest["primary_doc"]:
            return {"filing_date": latest["filing_date"],
                    "text": "[documento principal del 10-K no disponible en EDGAR]"}
        raw = get_filing_document(latest["cik"], latest["accession"], latest["primary_doc"])
        text = _strip_html(raw) if raw.strip().startswith("<") else raw
        return {"filing_date": latest["filing_date"], "text": text[:max_chars]}
    except Exception as exc:
        return {
            "filing_date": latest["filing_date"],
            "text": f"[error al descargar 10-K: {type(exc).__name__}: {exc}]",
        }
