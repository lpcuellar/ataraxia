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

import html as html_lib
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


def _strip_html(raw: str) -> str:
    """Limpieza básica de HTML a texto plano para pasarlo al LLM."""
    # Quitar scripts y style
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # Quitar tags
    text = re.sub(r"<[^>]+>", " ", raw)
    # Decodificar entidades: los filings de EDGAR están llenos de &#160; y &#8217;, que sin
    # esto llegan crudos al LLM y le gastan contexto en ruido ilegible.
    text = html_lib.unescape(text)
    # Los espacios tipográficos (nbsp, thin space) se normalizan a espacio normal para que
    # los patrones tipo "Item 8.01" se puedan buscar con \s de forma predecible.
    text = text.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    # Normalizar espacios
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_DOC_FILE_RE = re.compile(r"([A-Za-z0-9_.\-]+\.(?:htm|html|txt))", re.IGNORECASE)


def _filing_documents(cik: int, accession: str) -> list[dict]:
    """Tabla de documentos de un filing: [{description, document, types}].

    Se lee la columna 'Type' del índice en vez de adivinar por nombre de archivo. El nombre
    lo elige cada empresa — UNH llama a su press release 'earningsrelease2q26_7152.htm', no
    'ex991.htm' — pero 'Type' es metadata declarada ante la SEC y es consistente entre
    empresas. Adivinar por nombre fallaba en silencio y devolvía la portada del 8-K (puro
    XBRL de cover page) como si fuera el press release."""
    acc_clean = accession.replace("-", "")
    url = f"{_EDGAR_BASE}/Archives/edgar/data/{cik}/{acc_clean}/{accession}-index.htm"
    html = _get_sec(url)

    docs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 3:
            continue
        plain = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in cells]
        # El nombre del documento es la única celda con un archivo .htm/.txt; la fila de
        # encabezado no tiene ninguno y queda descartada sola.
        filename = None
        for cell in plain:
            m = _DOC_FILE_RE.search(cell)
            if m:
                filename = m.group(1)
                break
        if not filename:
            continue
        docs.append({
            "document": filename,
            # El tipo puede estar en distinta posición según el filing, así que se guardan
            # todas las celdas y se consulta por pertenencia, no por índice fijo.
            "types": {c.upper() for c in plain},
        })
    return docs


def _get_exhibit(
    cik: int,
    accession: str,
    preferred_types: tuple[str, ...] = ("EX-99.1", "EX-99", "EX-99.01"),
) -> Optional[str]:
    """Descarga el primer exhibit del filing cuyo tipo declarado esté en preferred_types.

    El orden de preferred_types manda: EX-99.1 es el press release de resultados en la
    inmensa mayoría de los 8-K item 2.02. Devuelve None si no hay ninguno, para que el
    llamador decida el fallback de forma explícita."""
    try:
        docs = _filing_documents(cik, accession)
    except Exception:
        return None

    for want in preferred_types:
        for d in docs:
            if want in d["types"]:
                try:
                    return get_filing_document(cik, accession, d["document"])
                except Exception:
                    continue
    return None


def get_earnings_releases(ticker: str, count: int = 2) -> list[dict]:
    """Últimos N earnings releases (8-K item 2.02) con el texto del press release.

    El press release (Ex-99.1) contiene los estados financieros condensados y el guidance —
    es la fuente más directa para entender si un salto de earnings fue orgánico o por items
    extraordinarios. Mucho más confiable que una noticia de terceros.

    Devuelve lista de dicts con: filing_date, accession, source, text.

    'source' distingue de dónde salió el texto y no es cosmético: la portada de un 8-K es
    casi toda metadata XBRL y no contiene ni revenue ni EPS. Si el texto viene de ahí, el
    análisis no tiene press release y hay que decirlo en vez de aparentar que sí lo tiene."""
    filings = get_recent_filings(ticker, "8-K", days=400)
    earnings = [f for f in filings if "2.02" in f["items"]][:count]

    results = []
    for f in earnings:
        try:
            raw = _get_exhibit(f["cik"], f["accession"])
            source = "exhibit_99"
            if not raw and f["primary_doc"]:
                raw = get_filing_document(f["cik"], f["accession"], f["primary_doc"])
                source = "cover_page_8k"
            if not raw:
                raise ValueError("no se encontró documento del earnings release")
            text = _strip_html(raw) if "<" in raw[:200] else raw
            if source == "cover_page_8k":
                text = (
                    "[ATENCION: no se pudo extraer el Exhibit 99.1 de este 8-K. Lo que sigue "
                    "es la PORTADA del filing, que es metadata y no trae resultados. No hay "
                    "press release disponible para este trimestre: no cites cifras de aca.]\n\n"
                ) + text
            # Limitar a 10,000 chars — suficiente para tablas de resultados y guidance
            results.append({
                "filing_date": f["filing_date"],
                "accession": f["accession"],
                "source": source,
                "text": text[:10000],
            })
        except Exception as exc:
            results.append({
                "filing_date": f["filing_date"],
                "accession": f["accession"],
                "source": "error",
                "text": f"[error al descargar: {type(exc).__name__}: {exc}]",
            })
    return results


_ITEM_HEADING_RE = re.compile(r"Item\s+\d+\.\d+", re.IGNORECASE)


def _event_body(text: str, max_chars: int = 2500) -> str:
    """Recorta un 8-K desde el primer encabezado 'Item X.XX', donde empieza el hecho.

    Los primeros ~2,800 caracteres de un 8-K son invariablemente lo mismo: metadata XBRL,
    la portada de la SEC, la lista de checkboxes de Rule 425/14a-12 y la tabla de valores
    registrados. Cortar desde el inicio devolvía solo ese boilerplate y dejaba fuera el
    hecho reportado — el agente veía el filing sin poder saber de qué trataba."""
    m = _ITEM_HEADING_RE.search(text)
    return text[m.start():m.start() + max_chars] if m else text[:max_chars]


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
                summary = _event_body(text)
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


def get_entity_info(ticker: str) -> dict:
    """Identidad de la entidad a la que EDGAR mapea un ticker, y la antigüedad de su historia.

    Sirve para distinguir una empresa con décadas de filings de una entidad recién registrada.
    Cuando una empresa se reorganiza (holdco sucesora, fusión, redomicilio), el ticker pasa a
    la entidad nueva mientras los filings históricos se quedan bajo el CIK del predecesor,
    que deja de tener ticker asignado. Sin esta distinción, la ausencia de un 10-K parece un
    error de red cuando en realidad es un hecho material del negocio."""
    def fetch():
        cik = get_cik(ticker)
        data = _get_sec(f"{_SEC_BASE}/submissions/CIK{cik:010d}.json")
        recent = data["filings"]["recent"]
        dates = recent.get("filingDate", [])
        return {
            "cik": cik,
            "name": data.get("name"),
            "former_names": [fn.get("name") for fn in data.get("formerNames", [])],
            "filing_count": len(dates),
            "earliest_filing": dates[-1] if dates else None,
            "latest_filing": dates[0] if dates else None,
        }

    return cached_call("edgar_entity_info", {"ticker": ticker.upper()}, fetch)


_10K_SECTIONS = (
    ("Item 1 — Business", r"Item\s+1\.?\s*Business"),
    ("Item 7 — MD&A", r"Item\s+7\.?\s*Management"),
)


def _pick_section_start(text: str, pattern: str) -> Optional[int]:
    """Posición donde arranca de verdad una sección, descartando el índice del 10-K.

    El encabezado de cada sección aparece al menos dos veces: una en la tabla de contenidos
    y otra en la sección real. Se elige la ocurrencia con más texto por delante hasta la
    siguiente repetición del mismo encabezado. Las entradas del índice están pegadas entre
    sí, así que puntúan bajo; la sección real puntúa alto. El criterio también descarta una
    referencia cruzada al final del documento, que tendría poco texto detrás."""
    starts = [m.start() for m in re.finditer(pattern, text, re.IGNORECASE)]
    if not starts:
        return None
    bounds = starts[1:] + [len(text)]
    return max(zip(starts, bounds), key=lambda p: p[1] - p[0])[0]


def _extract_10k_sections(text: str, max_chars: int) -> str:
    """Devuelve Item 1 (Business) y Item 7 (MD&A), repartiendo max_chars entre las dos.

    Tomar los primeros max_chars de un 10-K no sirve: el documento abre con decenas de miles
    de caracteres de contexto XBRL (us-gaap:*Member con sus rangos de fechas) y después la
    portada y el índice. En el 10-K de UNH el negocio recién empieza cerca del carácter
    48,000, así que un corte de 20,000 desde el inicio entregaba puro ruido."""
    chunks = []
    budget = max_chars // max(1, len(_10K_SECTIONS))
    for label, pattern in _10K_SECTIONS:
        start = _pick_section_start(text, pattern)
        if start is None:
            continue
        chunks.append(f"===== {label} =====\n{text[start:start + budget]}")

    if not chunks:
        # Sin encabezados reconocibles (formato atípico o documento envuelto): se entrega el
        # inicio y se avisa, en vez de devolver silencio.
        return (
            "[No se reconocieron los encabezados Item 1 / Item 7 en este 10-K. "
            "Lo que sigue es el inicio del documento, que puede ser metadata.]\n\n"
            + text[:max_chars]
        )
    return "\n\n".join(chunks)


def get_latest_10k_text(ticker: str, max_chars: int = 20000) -> dict:
    """Extracto del 10-K más reciente: Item 1 (Business) e Item 7 (MD&A).

    Un 10-K puede pasar de 370,000 caracteres, así que max_chars acota lo que llega al LLM
    y se reparte entre las dos secciones que sostienen el análisis: qué hace la empresa y
    cómo explica el management sus resultados.

    Devuelve dict con: filing_date, text y full_chars (tamaño del documento completo, para
    saber qué proporción se está leyendo)."""
    filings = get_recent_filings(ticker, "10-K", days=400)
    if not filings:
        # Caso real (XOM, oct-2026): company_tickers.json mapea el ticker a una holdco
        # sucesora recién registrada que todavía no presentó 10-K; los filings históricos
        # siguen bajo el CIK del predecesor, que ya perdió el ticker. EDGAR no expone el
        # vínculo predecesor→sucesor, así que no se puede resolver automáticamente. Se
        # reporta explícito porque la reorganización misma es material para la tesis.
        try:
            entity = get_entity_info(ticker)
        except Exception:
            entity = {}
        return {
            "filing_date": None,
            "missing": True,
            "entity_name": entity.get("name"),
            "cik": entity.get("cik"),
            "text": (
                f"SIN 10-K DISPONIBLE. En EDGAR el ticker {ticker.upper()} está mapeado a "
                f"{entity.get('name')!r} (CIK {entity.get('cik')}), que no presentó 10-K en los "
                f"últimos 400 días. Esa entidad tiene {entity.get('filing_count')} filings y el "
                f"más antiguo es del {entity.get('earliest_filing')}.\n\n"
                f"Si ese primer filing es reciente, la entidad es nueva: probable reorganización, "
                f"holdco sucesora, fusión o redomicilio. Los estados financieros del data package "
                f"vienen de Yahoo y sí tienen historia, así que no hay contradicción entre ambos — "
                f"pero el cambio de entidad legal es un hecho material.\n\n"
                f"OBLIGATORIO: averiguá qué pasó con la estructura corporativa antes de concluir. "
                f"Es el 'paso previo' del framework: qué negocio es HOY. No asumas continuidad "
                f"entre predecesor y entidad nueva sin verificarla."
            ),
        }

    latest = filings[0]
    try:
        if not latest["primary_doc"]:
            return {"filing_date": latest["filing_date"],
                    "text": "[documento principal del 10-K no disponible en EDGAR]"}
        raw = get_filing_document(latest["cik"], latest["accession"], latest["primary_doc"])
        text = _strip_html(raw) if raw.strip().startswith("<") else raw
        return {
            "filing_date": latest["filing_date"],
            "full_chars": len(text),
            "text": _extract_10k_sections(text, max_chars),
        }
    except Exception as exc:
        return {
            "filing_date": latest["filing_date"],
            "text": f"[error al descargar 10-K: {type(exc).__name__}: {exc}]",
        }
