"""
Acceso a datos sobre el schema en supabase/migrations/ (Supabase/Postgres).

Conexion directa via psycopg2 con el rol acotado `ataraxia_brain` (ver
supabase/migrations/ y supabase/README.md) — no el cliente supabase-py, porque ese solo
autentica con las keys anon/service_role, y service_role tiene acceso total (rompe el
principio de scope minimo que queriamos).

Nota: el schema (CREATE TABLE, RLS, GRANT) se despliega via la integracion de GitHub de
Supabase al mergear a main — no desde aqui. La creacion del rol ataraxia_brain en si es un
paso manual de una sola vez (ver supabase/README.md) porque require una password que no
debe quedar committeada. El rol ataraxia_brain no tiene permiso para crear tablas ni roles,
solo para leer/escribir segun los GRANT de la migracion.

Resiliencia de red: si un log_* falla (Supabase caido, sin internet, etc.), la escritura no
se pierde en silencio — se guarda en data/pending_db_writes/ como JSON y queda para
reintentar con flush_pending_writes(), que conviene llamar al inicio de cada corrida diaria.
"""

import json
import time
from pathlib import Path

import psycopg2
import psycopg2.extras

from src.config import PENDING_WRITES_DIR, require_db_config


def get_connection():
    """Abre una conexion nueva a Supabase. No se reutiliza una conexion global porque el
    brain corre como un proceso de corta duracion (una sesion programada diaria), no un
    servidor de larga duracion."""
    return psycopg2.connect(**require_db_config())


def _execute(query: str, params: dict) -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
    finally:
        conn.close()


def _save_pending_write(kind: str, payload: dict) -> None:
    """Fallback cuando la escritura a Supabase falla: no se pierde el dato, se encola."""
    ts = time.strftime("%Y%m%dT%H%M%S")
    path = PENDING_WRITES_DIR / f"{ts}_{kind}_{id(payload)}.json"
    path.write_text(json.dumps({"kind": kind, "payload": payload}, default=str, indent=2))


def _write_with_fallback(kind: str, query: str, params: dict) -> None:
    try:
        _execute(query, params)
    except Exception as e:
        _save_pending_write(kind, params)
        print(
            f"AVISO: fallo al escribir '{kind}' en Supabase ({e}). "
            f"Guardado en {PENDING_WRITES_DIR} para reintentar con flush_pending_writes()."
        )


def flush_pending_writes() -> int:
    """Reintenta todas las escrituras encoladas por fallos de red anteriores. Devuelve
    cuantas se lograron reenviar. Llamar al inicio de cada corrida diaria del brain."""
    pending = sorted(PENDING_WRITES_DIR.glob("*.json"))
    flushed = 0
    for path in pending:
        record = json.loads(path.read_text())
        kind, payload = record["kind"], record["payload"]
        try:
            if kind == "decision":
                _insert_decision(payload)
            elif kind == "position":
                _upsert_position(payload)
            elif kind == "performance":
                _upsert_performance(payload)
            elif kind == "universe_state":
                _update_universe_state(payload)
            else:
                continue
            path.unlink()
            flushed += 1
        except Exception:
            continue  # sigue en pending_db_writes/, se reintenta la proxima vez
    return flushed


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------

_INSERT_DECISION = """
insert into decisions (
    date, ticker, entry_type, action, quantity, price, rationale, bear_case,
    bear_case_probability, guardrail_result, guardrail_rejection_reason
) values (
    %(date)s, %(ticker)s, %(entry_type)s, %(action)s, %(quantity)s, %(price)s,
    %(rationale)s, %(bear_case)s, %(bear_case_probability)s, %(guardrail_result)s,
    %(guardrail_rejection_reason)s
)
"""


def _insert_decision(payload: dict) -> None:
    _execute(_INSERT_DECISION, payload)


def log_decision(
    date: str,
    ticker: str,
    entry_type: str,
    rationale: str,
    guardrail_result: str,
    action: str | None = None,
    quantity: float | None = None,
    price: float | None = None,
    bear_case: str | None = None,
    bear_case_probability: float | None = None,
    guardrail_rejection_reason: str | None = None,
) -> None:
    payload = dict(
        date=date, ticker=ticker, entry_type=entry_type, action=action, quantity=quantity,
        price=price, rationale=rationale, bear_case=bear_case,
        bear_case_probability=bear_case_probability, guardrail_result=guardrail_result,
        guardrail_rejection_reason=guardrail_rejection_reason,
    )
    _write_with_fallback("decision", _INSERT_DECISION, payload)


# ---------------------------------------------------------------------------
# positions
# ---------------------------------------------------------------------------

_UPSERT_POSITION = """
insert into positions (date, ticker, quantity, avg_cost, current_value, pct_of_portfolio)
values (%(date)s, %(ticker)s, %(quantity)s, %(avg_cost)s, %(current_value)s, %(pct_of_portfolio)s)
on conflict (date, ticker) do update set
    quantity = excluded.quantity,
    avg_cost = excluded.avg_cost,
    current_value = excluded.current_value,
    pct_of_portfolio = excluded.pct_of_portfolio
"""


def _upsert_position(payload: dict) -> None:
    _execute(_UPSERT_POSITION, payload)


def log_position_snapshot(
    date: str, ticker: str, quantity: float, avg_cost: float, current_value: float,
    pct_of_portfolio: float,
) -> None:
    payload = dict(
        date=date, ticker=ticker, quantity=quantity, avg_cost=avg_cost,
        current_value=current_value, pct_of_portfolio=pct_of_portfolio,
    )
    _write_with_fallback("position", _UPSERT_POSITION, payload)


# ---------------------------------------------------------------------------
# performance
# ---------------------------------------------------------------------------

_UPSERT_PERFORMANCE = """
insert into performance (
    date, fund_value, sp500_equivalent_value, cumulative_return_pct,
    sp500_cumulative_return_pct, current_drawdown_pct, max_drawdown_pct, sharpe_ratio
) values (
    %(date)s, %(fund_value)s, %(sp500_equivalent_value)s, %(cumulative_return_pct)s,
    %(sp500_cumulative_return_pct)s, %(current_drawdown_pct)s, %(max_drawdown_pct)s,
    %(sharpe_ratio)s
)
on conflict (date) do update set
    fund_value = excluded.fund_value,
    sp500_equivalent_value = excluded.sp500_equivalent_value,
    cumulative_return_pct = excluded.cumulative_return_pct,
    sp500_cumulative_return_pct = excluded.sp500_cumulative_return_pct,
    current_drawdown_pct = excluded.current_drawdown_pct,
    max_drawdown_pct = excluded.max_drawdown_pct,
    sharpe_ratio = excluded.sharpe_ratio
"""


def _upsert_performance(payload: dict) -> None:
    _execute(_UPSERT_PERFORMANCE, payload)


def log_performance_snapshot(
    date: str, fund_value: float, sp500_equivalent_value: float, cumulative_return_pct: float,
    sp500_cumulative_return_pct: float, current_drawdown_pct: float, max_drawdown_pct: float,
    sharpe_ratio: float | None = None,
) -> None:
    payload = dict(
        date=date, fund_value=fund_value, sp500_equivalent_value=sp500_equivalent_value,
        cumulative_return_pct=cumulative_return_pct,
        sp500_cumulative_return_pct=sp500_cumulative_return_pct,
        current_drawdown_pct=current_drawdown_pct, max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
    )
    _write_with_fallback("performance", _UPSERT_PERFORMANCE, payload)


# ---------------------------------------------------------------------------
# universe_state — fila singleton (id=1), leida/escrita por src/data/universe.py
# ---------------------------------------------------------------------------

_UPDATE_UNIVERSE_STATE = """
update universe_state set
    pool = %(pool)s,
    next_index = %(next_index)s,
    pool_last_refreshed = %(pool_last_refreshed)s,
    reviewed_ever = %(reviewed_ever)s,
    updated_at = now()
where id = 1
"""


def _update_universe_state(payload: dict) -> None:
    # payload puede venir con pool/reviewed_ever ya como listas (desde save_universe_state)
    # o ya serializadas (si viene de un JSON reencolado por flush_pending_writes) — normalizar.
    params = dict(payload)
    if not isinstance(params["pool"], str):
        params["pool"] = json.dumps(params["pool"])
    if not isinstance(params["reviewed_ever"], str):
        params["reviewed_ever"] = json.dumps(params["reviewed_ever"])
    _execute(_UPDATE_UNIVERSE_STATE, params)


def get_universe_state() -> dict | None:
    """Devuelve la fila singleton de universe_state, o None si Supabase no esta accesible
    (el llamador — RotationState.load() — decide como resolver ese caso)."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "select pool, next_index, pool_last_refreshed, reviewed_ever "
                "from universe_state where id = 1"
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def save_universe_state(
    pool: list[str], next_index: int, pool_last_refreshed: str | None, reviewed_ever: list[str],
) -> None:
    payload = dict(
        pool=pool, next_index=next_index, pool_last_refreshed=pool_last_refreshed,
        reviewed_ever=reviewed_ever,
    )
    try:
        _update_universe_state(payload)
    except Exception as e:
        _save_pending_write("universe_state", payload)
        print(
            f"AVISO: fallo al escribir 'universe_state' en Supabase ({e}). "
            f"Guardado en {PENDING_WRITES_DIR} para reintentar con flush_pending_writes()."
        )
