"""
Colector de datos para análisis profundo de una empresa.

Este módulo resuelve el problema central del ciclo anterior: el LLM no puede investigar y
analizar al mismo tiempo con calidad. El collector hace todo el trabajo de datos ANTES de
que el LLM lo vea. El LLM recibe un paquete estructurado y completo, y su único trabajo es
aplicar el framework de las tres etapas sobre esa información.

Lo que incluye el paquete (collect()):
  profile       — descripción, sector, industria, employees (yfinance)
  financials    — income statement, balance sheet, cashflow anuales (yfinance, 4 años)
  roic_series   — ROIC calculado por código año a año (no scrapeado, no declarado por el LLM)
  quality_flags — alertas de distorsión contable detectadas automáticamente
  multiples     — P/E, P/S, ROIC trailing, márgenes (yfinance + stockanalysis)
  analyst       — estimados y cobertura de analistas
  news          — noticias recientes Yahoo Finance (company-specific, 30 días)
  filings       — earnings releases recientes + 8-K materiales (EDGAR)
  filing_10k    — extracto del 10-K más reciente (EDGAR, hasta 20k chars)

Cálculo de ROIC:
  NOPAT = Operating Income × (1 - effective_tax_rate)
  effective_tax_rate = Tax Provision / Pretax Income cuando ambos son positivos, capeado en [0, 0.5]
  Convención yfinance: Tax Provision POSITIVA = gasto fiscal (normal); NEGATIVA = crédito (inusual).
  Si Tax Provision es negativa, se usa 0% para no inflar NOPAT con beneficios no recurrentes.
  ROIC = NOPAT / Invested Capital

  Invested Capital viene directamente de yfinance balance_sheet — es la suma de
  equity + deuda neta que el management reporta como capital empleado en el negocio.
  No se inventa ni se estima: si el campo no está, se marca como N/D.

Quality flags (alertas automáticas):
  - deferred_tax_spike: Non Current Deferred Taxes Assets creció >$500M en un año.
    Indica que la empresa registró un beneficio por reversión de valuation allowance
    (como Uber en 2024-2025) que infla el net income GAAP pero no es caja real.
  - large_unusual_items: Total Unusual Items > 10% del Operating Income en cualquier año.
    Puede ser ganancia/pérdida por venta de activos, impairments, fees de terminación
    (como el $2.8B de Netflix Q1 2026).
  - negative_effective_tax: Tax Provision negativa (beneficio fiscal) > 20% del pretax.
    Señal de que el net income GAAP está inflado por créditos fiscales no recurrentes.

Estos flags no son errores — son preguntas que el LLM DEBE responder en su análisis.
Si un flag está presente, el análisis debe explicar por qué cambia o no cambia la tesis.
"""

from __future__ import annotations

import warnings
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from src.data import fundamentals, market, yahoo
from src.data.cache import cached_call
from src.data.edgar import get_earnings_releases, get_material_8k, get_latest_10k_text


# ---------------------------------------------------------------------------
# Helpers de cálculo
# ---------------------------------------------------------------------------

def _safe_float(series: pd.Series, row: str) -> Optional[float]:
    """Extrae un float de una fila de un DataFrame, None si no existe o es NaN."""
    if row not in series.index:
        return None
    val = series.loc[row]
    if pd.isna(val):
        return None
    return float(val)


def _calc_roic(income_stmt: pd.DataFrame, balance_sheet: pd.DataFrame) -> list[dict]:
    """Calcula ROIC año a año desde los estados financieros de yfinance.

    Devuelve lista de dicts [{year, roic_pct, nopat, invested_capital, effective_tax_rate}]
    ordenada del más reciente al más antiguo. Campos None si el dato no está disponible."""
    results = []
    for col in income_stmt.columns:
        year = str(col.year)
        inc = income_stmt[col]

        operating_income = _safe_float(inc, "Operating Income")
        tax_provision = _safe_float(inc, "Tax Provision")
        pretax_income = _safe_float(inc, "Pretax Income")

        # Effective tax rate desde la propia empresa ese año, no marginal.
        # Convención yfinance: Tax Provision POSITIVA = gasto fiscal (empresa paga, normal).
        #                      Tax Provision NEGATIVA = crédito/beneficio (inusual, no recurrente).
        effective_tax = None
        if tax_provision is not None and pretax_income and abs(pretax_income) > 1e6:
            if tax_provision >= 0 and pretax_income > 0:
                # Caso normal: empresa paga impuestos → tasa = gasto / pretax
                effective_tax = min(0.50, tax_provision / pretax_income)
            else:
                # Tax Provision negativa (crédito no recurrente) o pretax negativo.
                # Para ROIC conservador usamos 0%: no inflamos NOPAT con créditos puntuales.
                effective_tax = 0.0

        nopat = None
        if operating_income is not None and effective_tax is not None:
            nopat = operating_income * (1 - effective_tax)

        # Invested Capital de balance sheet del mismo año (si está disponible)
        invested_capital = None
        if col in balance_sheet.columns:
            bs = balance_sheet[col]
            invested_capital = _safe_float(bs, "Invested Capital")

        roic_pct = None
        if nopat is not None and invested_capital and abs(invested_capital) > 1e6:
            roic_pct = round(nopat / invested_capital * 100, 2)

        results.append({
            "year": year,
            "roic_pct": roic_pct,
            "nopat_millions": round(nopat / 1e6, 1) if nopat is not None else None,
            "invested_capital_millions": round(invested_capital / 1e6, 1) if invested_capital else None,
            "effective_tax_rate_pct": round(effective_tax * 100, 1) if effective_tax is not None else None,
        })
    return results


def _detect_quality_flags(
    income_stmt: pd.DataFrame,
    balance_sheet: pd.DataFrame,
) -> list[dict]:
    """Detecta señales de distorsión contable que el LLM DEBE abordar en su análisis.

    No son errores ni rechazos — son preguntas obligatorias. Si el flag está, el análisis
    debe decir explícitamente si cambia la tesis y por qué."""
    flags = []

    # --- Flag 1: Spike en Deferred Tax Assets (indica reversión de valuation allowance) ---
    dta_row = "Non Current Deferred Taxes Assets"
    if dta_row in balance_sheet.index:
        dta = balance_sheet.loc[dta_row].dropna()
        if len(dta) >= 2:
            # Comparar año más reciente vs anterior
            cols = list(dta.index)
            delta = float(dta.iloc[0]) - float(dta.iloc[1])
            if delta > 500e6:  # creció más de $500M
                flags.append({
                    "type": "deferred_tax_spike",
                    "severity": "alta",
                    "description": (
                        f"Non-current deferred tax assets creció ${delta/1e9:.1f}B entre "
                        f"{cols[1].year} y {cols[0].year}. Probable reversión de valuation "
                        f"allowance — infla net income GAAP sin representar caja real. "
                        f"El LLM debe verificar si esto afecta el ROIC reportado y ajustarlo."
                    ),
                    "delta_billions": round(delta / 1e9, 2),
                })

    # --- Flag 2: Unusual items materiales ---
    unusual_row = "Total Unusual Items"
    op_income_row = "Operating Income"
    if unusual_row in income_stmt.index and op_income_row in income_stmt.index:
        for col in income_stmt.columns:
            unusual = _safe_float(income_stmt[col], unusual_row)
            op_income = _safe_float(income_stmt[col], op_income_row)
            if unusual is not None and op_income and abs(op_income) > 1e6:
                ratio = abs(unusual) / abs(op_income)
                if ratio > 0.10:  # más del 10% del operating income
                    flags.append({
                        "type": "large_unusual_items",
                        "severity": "media",
                        "description": (
                            f"Total Unusual Items = ${unusual/1e9:.2f}B en {col.year} "
                            f"({ratio*100:.0f}% del Operating Income). "
                            f"Puede incluir ganancias/pérdidas por venta de activos, "
                            f"impairments, fees de terminación, o reestructuraciones. "
                            f"El LLM debe identificar la naturaleza y si es recurrente."
                        ),
                        "year": col.year,
                        "unusual_billions": round(unusual / 1e9, 2),
                        "ratio_to_op_income": round(ratio, 2),
                    })

    # --- Flag 3: Tax Provision negativa (crédito/beneficio fiscal grande) ---
    # Convención yfinance: Tax Provision POSITIVA = gasto fiscal (empresa paga, lo normal).
    # Tax Provision NEGATIVA = crédito/beneficio fiscal (inusual, infla net income sin caja).
    # Solo flagear cuando la provisión es NEGATIVA y el beneficio es > 20% del pretax.
    # Ejemplo real: Uber 2025 Tax Provision = -$4.3B (reversión de valuation allowance DTA).
    tax_row = "Tax Provision"
    pretax_row = "Pretax Income"
    if tax_row in income_stmt.index and pretax_row in income_stmt.index:
        for col in income_stmt.columns:
            tax = _safe_float(income_stmt[col], tax_row)
            pretax = _safe_float(income_stmt[col], pretax_row)
            if tax is not None and pretax and pretax > 1e6:
                # Flagear solo si Tax Provision es NEGATIVA (crédito) y es grande
                if tax < 0 and abs(tax) > abs(pretax) * 0.20:
                    flags.append({
                        "type": "negative_effective_tax",
                        "severity": "alta",
                        "description": (
                            f"Tax Provision negativa (crédito fiscal) = ${abs(tax)/1e9:.2f}B en {col.year} "
                            f"({abs(tax)/abs(pretax)*100:.0f}% del pretax income). "
                            f"Net income GAAP incluye beneficio fiscal no recurrente — no es caja real. "
                            f"Usar operating income para medir rentabilidad real."
                        ),
                        "year": col.year,
                        "tax_benefit_billions": round(abs(tax) / 1e9, 2),
                    })

    return flags


def _financials_to_dict(df: pd.DataFrame, max_rows: list[str]) -> dict[str, dict]:
    """Convierte un DataFrame de yfinance a dict {row_name: {year: value_millions}}.

    Solo incluye las filas de max_rows que existan. Valores en millones (USD)."""
    result = {}
    for row in max_rows:
        if row not in df.index:
            continue
        series = df.loc[row].dropna()
        result[row] = {
            str(col.year): round(float(val) / 1e6, 1)
            for col, val in series.items()
        }
    return result


# Filas del income statement que siempre queremos en el paquete
_INCOME_ROWS = [
    "Total Revenue",
    "Gross Profit",
    "Operating Income",
    "Pretax Income",
    "Tax Provision",
    "Net Income",
    "EBIT",
    "EBITDA",
    "Diluted EPS",
    "Total Unusual Items",
    "Tax Effect Of Unusual Items",
    "Other Income Expense",
]

_BALANCE_ROWS = [
    "Total Assets",
    "Total Debt",
    "Net Debt",
    "Cash And Cash Equivalents",
    "Invested Capital",
    "Common Stock Equity",
    "Non Current Deferred Taxes Assets",
    "Non Current Deferred Taxes Liabilities",
]

_CASHFLOW_ROWS = [
    "Free Cash Flow",
    "Capital Expenditure",
    "Cash Dividends Paid",
    "Repurchase Of Capital Stock",
]


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def collect(ticker: str) -> dict[str, Any]:
    """Ensambla el paquete completo de datos para un ticker.

    Puede tardar 10-30 segundos por ticker (múltiples llamadas de red). Usa cached_call
    internamente — la segunda corrida del mismo día es instantánea.

    El paquete resultante es la única fuente de verdad para el LLM. Si algo no está aquí,
    el LLM no debe asumirlo ni buscarlo por su cuenta."""
    ticker = ticker.upper()

    def _collect():
        t = yf.Ticker(ticker)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            income_stmt = t.income_stmt    # 4 años anuales
            balance_sheet = t.balance_sheet
            cashflow = t.cashflow
            news_raw = t.news or []

        # --- Perfil ---
        profile = yahoo.get_company_profile(ticker)

        # --- Financials estructurados ---
        financials = {
            "income_statement": _financials_to_dict(income_stmt, _INCOME_ROWS),
            "balance_sheet": _financials_to_dict(balance_sheet, _BALANCE_ROWS),
            "cash_flow": _financials_to_dict(cashflow, _CASHFLOW_ROWS),
            "years_available": [str(c.year) for c in income_stmt.columns],
        }

        # --- ROIC calculado por código ---
        roic_series = _calc_roic(income_stmt, balance_sheet)

        # --- Quality flags ---
        quality_flags = _detect_quality_flags(income_stmt, balance_sheet)

        # --- Múltiplos y márgenes ---
        try:
            multiples_primary = fundamentals.get_valuation_metrics(ticker)
        except Exception:
            multiples_primary = None
        multiples_yahoo = yahoo.get_valuation_metrics(ticker)
        # Merge: primary fills first, yahoo fills gaps
        multiples = multiples_yahoo.copy()
        if multiples_primary:
            for k, v in multiples_primary.items():
                if v is not None:
                    multiples[k] = v
                    multiples[f"{k}_source"] = "stockanalysis"

        # Precio actual
        try:
            current_price = market.get_price(ticker)
        except Exception:
            current_price = yahoo.get_price(ticker)

        # --- Estimados de analistas ---
        try:
            analyst = fundamentals.get_analyst_forecast(ticker)
        except Exception:
            analyst = yahoo.get_analyst_forecast(ticker)

        # --- Noticias Yahoo Finance (últimos 30 días, company-specific) ---
        news = []
        for item in news_raw[:15]:  # máximo 15 noticias
            news.append({
                "title": item.get("content", {}).get("title") or item.get("title", ""),
                "published": (item.get("content", {}).get("pubDate") or
                              item.get("providerPublishTime", "")),
                "source": (item.get("content", {}).get("provider", {}).get("displayName") or
                           item.get("publisher", "")),
                "url": (item.get("content", {}).get("canonicalUrl", {}).get("url") or
                        item.get("link", "")),
            })

        # --- Filings EDGAR ---
        try:
            earnings_releases = get_earnings_releases(ticker, count=2)
        except Exception as exc:
            earnings_releases = [{"error": str(exc)}]

        try:
            material_8k = get_material_8k(ticker, days=180)
        except Exception as exc:
            material_8k = [{"error": str(exc)}]

        try:
            filing_10k = get_latest_10k_text(ticker, max_chars=20000)
        except Exception as exc:
            filing_10k = {"error": str(exc)}

        # Un 10-K ausente no es ruido de red: suele significar que el ticker apunta a una
        # entidad legal distinta de la que tiene la historia (reorganización, holdco
        # sucesora, fusión). Entra como flag para que el análisis tenga que responderlo.
        if filing_10k.get("missing"):
            quality_flags.append({
                "type": "missing_10k",
                "severity": "alta",
                "description": (
                    f"No hay 10-K en EDGAR para {ticker}. El ticker está mapeado a "
                    f"{filing_10k.get('entity_name')!r} (CIK {filing_10k.get('cik')}), una entidad "
                    f"sin 10-K reciente. Probable reorganización corporativa o holdco sucesora. "
                    f"El análisis debe identificar qué cambió en la estructura legal y si la "
                    f"continuidad del negocio se sostiene antes de aplicar el framework."
                ),
                "entity_name": filing_10k.get("entity_name"),
                "cik": filing_10k.get("cik"),
            })

        return {
            "ticker": ticker,
            "collected_at": pd.Timestamp.now().isoformat(),
            "current_price": current_price,
            "profile": profile,
            "financials": financials,
            "roic_series": roic_series,
            "quality_flags": quality_flags,
            "multiples": multiples,
            "analyst": analyst,
            "news": news,
            "filings": {
                "earnings_releases": earnings_releases,
                "material_8k": material_8k,
            },
            "filing_10k": filing_10k,
        }

    return cached_call("data_package", {"ticker": ticker}, _collect)
