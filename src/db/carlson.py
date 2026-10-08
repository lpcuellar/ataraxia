"""
Acceso a las tablas del rediseño Carlson: watchlist, candidate_queue, recommendations
y portfolio_snapshots.

Sigue las mismas convenciones que src/db/models.py — conexion de corta duracion y
fallback a data/pending_db_writes/ cuando la escritura falla, para no perder datos por
un corte de red a mitad de ciclo.

Separado de models.py a proposito: models.py es el esquema del fondo simulado (decisions,
positions, performance) que se conserva como track record. Este modulo es el flujo nuevo.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg2.extras

from src.db.models import _write_with_fallback, get_connection


def _query(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    """SELECT que devuelve dicts. Lectura directa: si falla, que falle ruidoso."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or {})
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# watchlist — empresas que pasaron el filtro de negocio pero estan caras
# ---------------------------------------------------------------------------

_INSERT_WATCHLIST = """
insert into watchlist (
    ticker, company_name, moat_type, moat_evidence, moat_direction,
    attacker_case, attacker_probability, thesis_summary, target_price,
    what_needs_to_happen, price_at_entry, last_reviewed_at
) values (
    %(ticker)s, %(company_name)s, %(moat_type)s, %(moat_evidence)s, %(moat_direction)s,
    %(attacker_case)s, %(attacker_probability)s, %(thesis_summary)s, %(target_price)s,
    %(what_needs_to_happen)s, %(price_at_entry)s, current_date
)
on conflict (ticker) do update set
    moat_evidence = excluded.moat_evidence,
    moat_direction = excluded.moat_direction,
    attacker_case = excluded.attacker_case,
    attacker_probability = excluded.attacker_probability,
    thesis_summary = excluded.thesis_summary,
    target_price = excluded.target_price,
    what_needs_to_happen = excluded.what_needs_to_happen,
    last_reviewed_at = current_date,
    updated_at = now()
"""


def add_to_watchlist(
    ticker: str,
    thesis_summary: str,
    what_needs_to_happen: str,
    *,
    company_name: str | None = None,
    moat_type: str | None = None,
    moat_evidence: str | None = None,
    moat_direction: str | None = None,
    attacker_case: str | None = None,
    attacker_probability: float | None = None,
    target_price: float | None = None,
    price_at_entry: float | None = None,
) -> None:
    """
    Agrega (o actualiza) una empresa en la watchlist.

    Solo entran empresas que pasaron Etapas 1 y 2 y fallaron unicamente en precio.
    Si fallo el negocio, se descarta — no va aqui.
    """
    _write_with_fallback(
        "watchlist",
        _INSERT_WATCHLIST,
        {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "moat_type": moat_type,
            "moat_evidence": moat_evidence,
            "moat_direction": moat_direction,
            "attacker_case": attacker_case,
            "attacker_probability": attacker_probability,
            "thesis_summary": thesis_summary,
            "target_price": target_price,
            "what_needs_to_happen": what_needs_to_happen,
            "price_at_entry": price_at_entry,
        },
    )


def get_watchlist(status: str = "esperando") -> list[dict[str, Any]]:
    """La watchlist viva. status=None trae todo, incluidas compradas y descartadas."""
    if status is None:
        return _query("select * from watchlist order by ticker")
    return _query(
        "select * from watchlist where status = %(status)s order by ticker",
        {"status": status},
    )


def mark_watchlist_reviewed(ticker: str) -> None:
    """Marca que se reviso en este ciclo, sin cambiar la tesis."""
    _write_with_fallback(
        "watchlist_review",
        "update watchlist set last_reviewed_at = current_date, updated_at = now() "
        "where ticker = %(ticker)s",
        {"ticker": ticker.upper()},
    )


def close_watchlist_entry(ticker: str, status: str, reason: str) -> None:
    """
    Saca una empresa de la lista viva.

    status='comprada'   -> llego a precio y se recomendo la compra
    status='descartada' -> el foso se erosiono; una empresa que dejo de ser buena no
                           espera para siempre en la lista
    """
    _write_with_fallback(
        "watchlist_close",
        "update watchlist set status = %(status)s, removed_reason = %(reason)s, "
        "updated_at = now() where ticker = %(ticker)s",
        {"ticker": ticker.upper(), "status": status, "reason": reason},
    )


# ---------------------------------------------------------------------------
# candidate_queue — cola entre el barrido diario y el reporte de lun/mie
# ---------------------------------------------------------------------------

_INSERT_CANDIDATE = """
insert into candidate_queue (ticker, source, reason, url, priority)
values (%(ticker)s, %(source)s, %(reason)s, %(url)s, %(priority)s)
on conflict (ticker, status) do update set
    reason = excluded.reason,
    priority = greatest(candidate_queue.priority, excluded.priority),
    queued_at = now()
"""


def enqueue_candidate(
    ticker: str,
    source: str,
    reason: str,
    *,
    url: str | None = None,
    priority: int = 0,
) -> None:
    """
    Encola un candidato para analisis profundo.

    source: noticia | rotacion_universo | portafolio | watchlist
    El unique (ticker, status) evita duplicados pendientes del mismo ticker.
    """
    _write_with_fallback(
        "candidate",
        _INSERT_CANDIDATE,
        {
            "ticker": ticker.upper(),
            "source": source,
            "reason": reason,
            "url": url,
            "priority": priority,
        },
    )


def get_queue(limit: int = 10) -> list[dict[str, Any]]:
    """Los candidatos pendientes, por prioridad y antigüedad."""
    return _query(
        "select * from candidate_queue where status = 'pendiente' "
        "order by priority desc, queued_at asc limit %(limit)s",
        {"limit": limit},
    )


def mark_candidate(ticker: str, status: str) -> None:
    """status: 'analizado' o 'descartado'. Lo saca de la cola pendiente."""
    _write_with_fallback(
        "candidate_status",
        "update candidate_queue set status = %(status)s, consumed_at = now() "
        "where ticker = %(ticker)s and status = 'pendiente'",
        {"ticker": ticker.upper(), "status": status},
    )


# ---------------------------------------------------------------------------
# recommendations — la bitacora: que recomendo Ataraxia, que acciono LP
# ---------------------------------------------------------------------------

_INSERT_RECOMMENDATION = """
insert into recommendations (
    date, ticker, verdict, stage1_moat, stage1_verdict, stage2_checklist,
    stage2_verdict, stage3_valuation, price_at_recommendation, target_price,
    proposed_size_pct, bear_case, bear_case_probability, rationale, lp_action
) values (
    %(date)s, %(ticker)s, %(verdict)s, %(stage1_moat)s, %(stage1_verdict)s,
    %(stage2_checklist)s, %(stage2_verdict)s, %(stage3_valuation)s,
    %(price_at_recommendation)s, %(target_price)s, %(proposed_size_pct)s,
    %(bear_case)s, %(bear_case_probability)s, %(rationale)s, %(lp_action)s
)
"""


def log_recommendation(
    ticker: str,
    verdict: str,
    rationale: str,
    *,
    stage1_moat: str | None = None,
    stage1_verdict: str | None = None,
    stage2_checklist: str | None = None,
    stage2_verdict: str | None = None,
    stage3_valuation: str | None = None,
    price_at_recommendation: float | None = None,
    target_price: float | None = None,
    proposed_size_pct: float | None = None,
    bear_case: str | None = None,
    bear_case_probability: float | None = None,
    on_date: date | None = None,
) -> None:
    """
    Registra una recomendacion. lp_action queda 'pendiente' hasta que LP decida.

    verdict: compra | agregar_watchlist | esperar_precio | descartar |
             recortar | vender | mantener
    """
    _write_with_fallback(
        "recommendation",
        _INSERT_RECOMMENDATION,
        {
            "date": on_date or date.today(),
            "ticker": ticker.upper(),
            "verdict": verdict,
            "stage1_moat": stage1_moat,
            "stage1_verdict": stage1_verdict,
            "stage2_checklist": stage2_checklist,
            "stage2_verdict": stage2_verdict,
            "stage3_valuation": stage3_valuation,
            "price_at_recommendation": price_at_recommendation,
            "target_price": target_price,
            "proposed_size_pct": proposed_size_pct,
            "bear_case": bear_case,
            "bear_case_probability": bear_case_probability,
            "rationale": rationale,
            "lp_action": "pendiente" if verdict in ("compra", "recortar", "vender") else None,
        },
    )


def record_lp_action(
    recommendation_id: int,
    action: str,
    *,
    executed_price: float | None = None,
    notes: str | None = None,
) -> None:
    """
    Cierra el ciclo: que hizo LP con la recomendacion.

    action: ejecutada | rechazada | parcial | pendiente

    La brecha entre lo recomendado y lo ejecutado es informacion util — si LP rechaza
    sistematicamente cierto tipo de recomendacion, eso dice algo del criterio.
    """
    _write_with_fallback(
        "lp_action",
        "update recommendations set lp_action = %(action)s, lp_action_at = current_date, "
        "lp_executed_price = %(price)s, lp_notes = %(notes)s where id = %(id)s",
        {
            "id": recommendation_id,
            "action": action,
            "price": executed_price,
            "notes": notes,
        },
    )


def get_recommendations(limit: int = 20, pending_only: bool = False) -> list[dict[str, Any]]:
    """Historial de recomendaciones, mas recientes primero."""
    if pending_only:
        return _query(
            "select * from recommendations where lp_action = 'pendiente' "
            "order by date desc, id desc limit %(limit)s",
            {"limit": limit},
        )
    return _query(
        "select * from recommendations order by date desc, id desc limit %(limit)s",
        {"limit": limit},
    )


# ---------------------------------------------------------------------------
# portfolio_snapshots — serie historica del portafolio real
# ---------------------------------------------------------------------------

_INSERT_SNAPSHOT = """
insert into portfolio_snapshots (
    as_of, source_file, total_market_value, total_cost_basis, cash,
    equity_count, etf_count, sp500_close
) values (
    %(as_of)s, %(source_file)s, %(total_market_value)s, %(total_cost_basis)s,
    %(cash)s, %(equity_count)s, %(etf_count)s, %(sp500_close)s
)
on conflict (as_of) do nothing
"""


def log_portfolio_snapshot(
    as_of: date,
    source_file: str,
    total_market_value: float,
    total_cost_basis: float,
    *,
    cash: float = 0.0,
    equity_count: int = 0,
    etf_count: int = 0,
    sp500_close: float | None = None,
) -> None:
    """
    Registra un snapshot del portafolio real. Idempotente por fecha: subir el mismo CSV
    dos veces no duplica la serie.
    """
    _write_with_fallback(
        "portfolio_snapshot",
        _INSERT_SNAPSHOT,
        {
            "as_of": as_of,
            "source_file": source_file,
            "total_market_value": total_market_value,
            "total_cost_basis": total_cost_basis,
            "cash": cash,
            "equity_count": equity_count,
            "etf_count": etf_count,
            "sp500_close": sp500_close,
        },
    )


# El portafolio real empieza acá. Cualquier fila anterior es ruido de desarrollo:
# ataraxia_brain no tiene DELETE por diseño, asi que se filtran en lectura.
PORTFOLIO_EPOCH = date(2026, 1, 1)


def get_snapshot_history(limit: int = 365, since: date | None = None) -> list[dict[str, Any]]:
    """La serie historica, mas antigua primero — lista para graficar."""
    rows = _query(
        "select * from portfolio_snapshots where as_of >= %(since)s "
        "order by as_of desc limit %(limit)s",
        {"limit": limit, "since": since or PORTFOLIO_EPOCH},
    )
    return list(reversed(rows))
