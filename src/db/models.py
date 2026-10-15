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
import os
import time
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.extras

from src.config import PENDING_WRITES_DIR, require_db_config

# El portafolio real empieza aca. Cualquier fila anterior es ruido de desarrollo (quedo un
# snapshot de prueba con as_of 1999-01-01 y source_file 'probe.csv'): ataraxia_brain no tiene
# DELETE por diseño, asi que se filtra en lectura.
#
# Esto NO es cosmetico: un snapshot de 1999 dentro de una serie de performance produce
# retornos y drawdowns sin sentido, y el alpha relativo es el instrumento con el que se juzga
# el proyecto entero. Vive aca, en la capa baja, porque src/db/carlson.py importa de este
# modulo y no al revez — una sola definicion, sin ciclo de imports.
PORTFOLIO_EPOCH = date(2026, 1, 1)


def get_connection():
    """Abre una conexion nueva a Supabase. No se reutiliza una conexion global porque el
    brain corre como un proceso de corta duracion (una sesion programada diaria), no un
    servidor de larga duracion."""
    config = require_db_config()
    config["connect_timeout"] = 10
    if os.getenv("ATARAXIA_DRY_RUN") == "1":
        config["options"] = "-c default_transaction_read_only=on -c statement_timeout=15000"
    conn = psycopg2.connect(**config)
    if os.getenv("ATARAXIA_DRY_RUN") == "1":
        conn.set_session(readonly=True)
    return conn


def _execute(query: str, params: dict) -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
    finally:
        conn.close()


def _dry_run() -> bool:
    """
    Modo dry-run, puesto por scripts/dry_run_check.py via entorno.

    Se consulta ANTES de intentar la escritura, no despues: si solo bloquearamos la
    conexion, el `except` de _write_with_fallback encolaria la escritura rechazada en
    pending_db_writes/ y reapareceria en el proximo ciclo real. El modo de solo lectura
    de Postgres no protege colas de archivos.
    """
    return os.environ.get("ATARAXIA_DRY_RUN") == "1"


def _save_pending_write(kind: str, payload: dict) -> None:
    """Fallback cuando la escritura a Supabase falla: no se pierde el dato, se encola."""
    ts = time.strftime("%Y%m%dT%H%M%S")
    path = PENDING_WRITES_DIR / f"{ts}_{kind}_{id(payload)}.json"
    path.write_text(json.dumps({"kind": kind, "payload": payload}, default=str, indent=2))


def _write_with_fallback(kind: str, query: str, params: dict) -> None:
    if _dry_run():
        # Ruidoso a proposito: en dry-run ningun camino deberia intentar escribir. Si
        # algo llega hasta aca, es un camino que el flag de run_cycle no cubrio y hay
        # que verlo, no silenciarlo.
        raise RuntimeError(
            f"Escritura '{kind}' intentada en dry-run. Bloqueada antes del fallback: "
            "no se encola en pending_db_writes/ para no reaparecer en el proximo ciclo real."
        )
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
            elif kind == "proposal":
                _execute(_INSERT_PROPOSAL, payload)
            elif kind == "fill":
                _execute(_INSERT_FILL, payload)
            elif kind == "cash_event":
                _execute(_INSERT_CASH_EVENT, payload)
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


# ---------------------------------------------------------------------------
# Estado de cuenta derivado (brain-side, solo lectura)
#
# La verdad sobre la cuenta vive en executed_trades + cash_events (escritas solo por el
# executor). El brain arma su vision del portafolio DERIVANDOLA de esas tablas — nunca la
# asevera. Nota: models.py sirve a ambos roles; cual rol se usa depende de SUPABASE_DB_USER
# en el entorno (el brain corre con ataraxia_brain, el executor con ataraxia_executor).
# ---------------------------------------------------------------------------

def get_account_state() -> dict:
    """Deriva el estado real de la cuenta desde executed_trades + cash_events.

    Devuelve: {
        "holdings": {ticker: {"quantity": float, "avg_cost": float}},   # posiciones abiertas
        "cash": float,
        "todays_trades": [{"ticker": str, "action": str}],              # fills de HOY
    }
    El caller le agrega precios actuales (FMP) para construir el PortfolioState del validator.
    avg_cost usa costo promedio simple de los fills de compra (se recalcula al comprar; una
    venta no cambia el avg_cost de lo que queda).
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("select date, ticker, action, quantity, price from executed_trades order by id")
            fills = [dict(r) for r in cur.fetchall()]
            cur.execute("select coalesce(sum(amount), 0) as total from cash_events")
            cash = float(cur.fetchone()["total"])
    finally:
        conn.close()

    holdings: dict[str, dict] = {}
    todays_trades = []
    from datetime import date as _date
    today = _date.today()

    for f in fills:
        qty, price = float(f["quantity"]), float(f["price"])
        t = f["ticker"]
        if f["action"] == "buy":
            cash -= qty * price
            if t not in holdings:
                holdings[t] = {"quantity": 0.0, "avg_cost": 0.0}
            h = holdings[t]
            total_cost = h["quantity"] * h["avg_cost"] + qty * price
            h["quantity"] += qty
            h["avg_cost"] = total_cost / h["quantity"]
        else:  # sell
            cash += qty * price
            if t in holdings:
                holdings[t]["quantity"] -= qty
                if holdings[t]["quantity"] <= 1e-9:
                    del holdings[t]
        if f["date"] == today:
            todays_trades.append({"ticker": t, "action": f["action"]})

    return {"holdings": holdings, "cash": cash, "todays_trades": todays_trades}


def get_cash_events(event_type: str | None = None) -> list[dict]:
    """Todos los cash_events, opcionalmente filtrados por tipo (p.ej. 'deposit'). Usado por
    src/reporting/performance.py para saber cuanto y desde cuando se fondeo la cuenta."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if event_type is not None:
                cur.execute(
                    "select date, event_type, amount, note from cash_events "
                    "where event_type = %(event_type)s order by date",
                    {"event_type": event_type},
                )
            else:
                cur.execute("select date, event_type, amount, note from cash_events order by date")
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_performance_history() -> list[dict]:
    """Historico de snapshots de performance, ordenado cronologicamente — insumo para
    Sharpe ratio y drawdown en src/reporting/performance.py."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "select date, fund_value, sp500_equivalent_value, cumulative_return_pct, "
                "sp500_cumulative_return_pct, current_drawdown_pct, max_drawdown_pct, "
                "sharpe_ratio from performance order by date"
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_flagged_tickers() -> set:
    """Tickers actualmente bajo revision obligatoria de tesis: su ultimo evento de tesis en
    decisions es un 'thesis_flag' sin 'thesis_resolution' posterior."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select distinct on (ticker) ticker, entry_type
                from decisions
                where entry_type in ('thesis_flag', 'thesis_resolution')
                order by ticker, id desc
                """
            )
            return {row[0] for row in cur.fetchall() if row[1] == "thesis_flag"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Handoff brain -> executor
# ---------------------------------------------------------------------------

_INSERT_PROPOSAL = """
insert into decisions (
    date, ticker, entry_type, action, quantity, price, rationale, bear_case,
    bear_case_probability, guardrail_result, guardrail_rejection_reason, execution_status
) values (
    %(date)s, %(ticker)s, 'trade', %(action)s, %(quantity)s, %(price)s,
    %(rationale)s, %(bear_case)s, %(bear_case_probability)s, %(guardrail_result)s,
    %(guardrail_rejection_reason)s, %(execution_status)s
)
"""


def log_trade_proposal(
    date: str,
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    rationale: str,
    guardrail_result: str,
    bear_case: str | None = None,
    bear_case_probability: float | None = None,
    guardrail_rejection_reason: str | None = None,
) -> None:
    """Como log_decision, pero para propuestas ejecutables: si el guardrail del brain la
    aprobo, queda 'pending' para que el executor la recoja (y re-valide por su cuenta).
    Propuestas rechazadas quedan con execution_status='skipped' — registradas para el
    historial, nunca ejecutables."""
    payload = dict(
        date=date, ticker=ticker, action=action, quantity=quantity, price=price,
        rationale=rationale, bear_case=bear_case, bear_case_probability=bear_case_probability,
        guardrail_result=guardrail_result, guardrail_rejection_reason=guardrail_rejection_reason,
        execution_status="pending" if guardrail_result == "approved" else "skipped",
    )
    _write_with_fallback("proposal", _INSERT_PROPOSAL, payload)


def get_pending_proposals() -> list[dict]:
    """Executor-side: propuestas aprobadas por el brain que esperan ejecucion."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "select id, date, ticker, action, quantity, price, rationale, "
                "bear_case, bear_case_probability "
                "from decisions where execution_status = 'pending' order by id"
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def mark_execution_status(decision_id: int, status: str, note: str | None = None) -> None:
    """Executor-side: cierra el ciclo de una propuesta ('executed' | 'failed' | 'skipped')."""
    _execute(
        "update decisions set execution_status = %(status)s, execution_note = %(note)s "
        "where id = %(id)s",
        {"id": decision_id, "status": status, "note": note},
    )


# ---------------------------------------------------------------------------
# Registro de fills y cash (executor-side — el rol ataraxia_brain no tiene INSERT aqui)
# ---------------------------------------------------------------------------

_INSERT_FILL = """
insert into executed_trades (date, ticker, action, quantity, price, decision_id)
values (%(date)s, %(ticker)s, %(action)s, %(quantity)s, %(price)s, %(decision_id)s)
"""


def record_fill(
    date: str, ticker: str, action: str, quantity: float, price: float,
    decision_id: int | None = None,
) -> None:
    payload = dict(
        date=date, ticker=ticker, action=action, quantity=quantity, price=price,
        decision_id=decision_id,
    )
    _write_with_fallback("fill", _INSERT_FILL, payload)


_INSERT_CASH_EVENT = """
insert into cash_events (date, event_type, amount, note)
values (%(date)s, %(event_type)s, %(amount)s, %(note)s)
"""


def record_cash_event(date: str, event_type: str, amount: float, note: str | None = None) -> None:
    payload = dict(date=date, event_type=event_type, amount=amount, note=note)
    _write_with_fallback("cash_event", _INSERT_CASH_EVENT, payload)


# ---------------------------------------------------------------------------
# Snapshots del portafolio real con detalle de lotes
# (migracion 20261011180000_portfolio_lots.sql)
#
# A diferencia de los log_*, estas escrituras NO usan _write_with_fallback: cargar un
# snapshot es una accion deliberada que LP dispara a mano, no un efecto secundario de una
# corrida automatica. Si falla, tiene que fallar a la vista para que se reintente — no
# quedar encolado en data/pending_db_writes/ dando la impresion de que ya se guardo.
# ---------------------------------------------------------------------------

_INSERT_SNAPSHOT = """
insert into portfolio_snapshots
    (as_of, source_file, total_market_value, total_cost_basis, cash,
     equity_count, etf_count, sp500_close)
values
    (%(as_of)s, %(source_file)s, %(total_market_value)s, %(total_cost_basis)s, %(cash)s,
     %(equity_count)s, %(etf_count)s, %(sp500_close)s)
returning id
"""

_INSERT_LOT = """
insert into portfolio_lots
    (snapshot_id, ticker, asset_class, open_date, quantity, cost_per_share, cost_basis,
     price_at_snapshot, market_value, holding_period)
values
    (%(snapshot_id)s, %(ticker)s, %(asset_class)s, %(open_date)s, %(quantity)s,
     %(cost_per_share)s, %(cost_basis)s, %(price_at_snapshot)s, %(market_value)s,
     %(holding_period)s)
"""


def snapshot_exists(as_of: str) -> bool:
    """as_of es unique en portfolio_snapshots — saberlo antes evita que el cargador reviente
    a mitad de camino con un error de constraint."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select 1 from portfolio_snapshots where as_of = %(as_of)s",
                {"as_of": as_of},
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def insert_portfolio_snapshot(
    as_of: str,
    source_file: str,
    total_market_value: float,
    total_cost_basis: float,
    cash: float,
    equity_count: int,
    etf_count: int,
    lots: list[dict],
    sp500_close: float | None = None,
) -> int:
    """Inserta el snapshot y todos sus lotes en UNA transaccion. Devuelve el id.

    Atomico a proposito: un snapshot a medias (cabecera sin lotes, o la mitad de los lotes)
    seria un portafolio que nunca existio, y el brain lo leeria como verdad.
    """
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(_INSERT_SNAPSHOT, dict(
                    as_of=as_of,
                    source_file=source_file,
                    total_market_value=total_market_value,
                    total_cost_basis=total_cost_basis,
                    cash=cash,
                    equity_count=equity_count,
                    etf_count=etf_count,
                    sp500_close=sp500_close,
                ))
                snapshot_id = cur.fetchone()[0]
                for lot in lots:
                    cur.execute(_INSERT_LOT, {**lot, "snapshot_id": snapshot_id})
        return snapshot_id
    finally:
        conn.close()


def update_snapshot_sp500_close(snapshot_id: int, sp500_close: float) -> None:
    """Rellena sp500_close en un snapshot ya existente.

    Unica excepcion deliberada a 'un snapshot es un hecho historico fechado y no se edita'
    (ver snapshot_exists): sp500_close es la referencia del benchmark para ESE as_of, no una
    observacion del portafolio en si — total_market_value, cash y los lotes siguen sin
    tocarse jamas. Pensado para backfill cuando el snapshot se creo sin acceso de red al
    benchmark, o para los snapshots de antes de que esto se poblara automaticamente."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update portfolio_snapshots set sp500_close = %(sp500_close)s "
                    "where id = %(id)s",
                    {"id": snapshot_id, "sp500_close": sp500_close},
                )
    finally:
        conn.close()


def get_latest_snapshot() -> dict | None:
    """Cabecera del snapshot mas reciente, o None si no hay ninguno.

    Filtra por PORTFOLIO_EPOCH igual que get_snapshot_history(): hoy el orden descendente
    por as_of ya dejaria la fila de prueba de 1999 al final, pero el filtro es explicito para
    que la condicion no dependa del ordenamiento de la consulta.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                select id, as_of, source_file, total_market_value, total_cost_basis, cash,
                       equity_count, etf_count, sp500_close, created_at
                from portfolio_snapshots
                where as_of >= %(epoch)s
                order by as_of desc
                limit 1
            """, {"epoch": PORTFOLIO_EPOCH})
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def get_snapshot_lots(snapshot_id: int) -> list[dict]:
    """Lotes de un snapshot, ordenados por ticker y fecha de compra descendente."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                select ticker, asset_class, open_date, quantity, cost_per_share, cost_basis,
                       price_at_snapshot, market_value, holding_period
                from portfolio_lots
                where snapshot_id = %(snapshot_id)s
                order by ticker, open_date desc
            """, {"snapshot_id": snapshot_id})
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
