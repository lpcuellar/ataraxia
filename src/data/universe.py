"""
Embudo de dos etapas para el universo de candidatos de Ataraxia (ver BUILD_PLAN.md).

Etapa 1 — filtro cuantitativo objetivo (sin juicio humano): interseccion entre los
constituyentes del S&P 500 y el resultado del screener por market cap minimo. Nadie elige a
mano cuales tickers quedan dentro.

Etapa 2 — lote rotativo: cada semana se toma un lote nuevo del pool filtrado para research
profundo, sin repetir hasta haber cubierto todo el pool una vez.

Nota de diseño: la "cobertura minima de analistas" (config/universe.yaml) NO se aplica en la
Etapa 1 para todo el pool de una — eso costaria una llamada de analyst-estimates por cada una
de las ~500 acciones del S&P 500 solo para armar el pool, lo cual desperdicia cuota del free
tier de FMP sin necesidad. En cambio, se aplica de forma perezosa: se verifica solo cuando un
ticker es seleccionado para el lote rotativo de esa semana (Etapa 2). Si no cumple, se
descarta y se toma el siguiente del pool — el costo de la verificacion se paga solo para los
~15-20 tickers que realmente se van a investigar esa semana, no para los ~150 del pool.

Las funciones de logica pura (sin I/O) estan separadas de la clase que persiste estado, para
poder probarlas con datos sinteticos sin necesitar una API key real (ver
scripts/test_universe_logic.py).

Fase 1.
"""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from src.config import DATA_DIR
from src.data import fundamentals
from src.db import models as db

# rotation_state.json ya no es la fuente de verdad (eso es la tabla universe_state en
# Supabase) — se mantiene como espejo local de solo-lectura de emergencia, para que un
# fallo de red no deje al brain sin saber en que punto de la rotacion iba.
ROTATION_STATE_FILE = DATA_DIR / "rotation_state.json"


# ---------------------------------------------------------------------------
# Logica pura — testable sin red ni API key
# ---------------------------------------------------------------------------

def build_quantitative_pool(
    sp500_constituents: list[dict],
    screener_results: list[dict],
) -> list[str]:
    """Etapa 1: interseccion de constituyentes del S&P 500 con el resultado del screener
    (ya filtrado por market cap minimo). Devuelve una lista ordenada alfabeticamente para
    que el orden sea determinista y auditable, no dependiente del orden de respuesta de la
    API."""
    sp500_tickers = {row["symbol"] for row in sp500_constituents if "symbol" in row}
    screener_tickers = {row["symbol"] for row in screener_results if "symbol" in row}
    pool = sorted(sp500_tickers & screener_tickers)
    return pool


def select_next_batch(
    pool: list[str],
    next_index: int,
    batch_size: int,
) -> tuple[list[str], int]:
    """Etapa 2: selecciona el siguiente lote del pool, avanzando circularmente (cuando se
    llega al final, se vuelve al principio) para eventualmente cubrir todo el pool a lo largo
    de suficientes semanas. Devuelve (lote, nuevo_next_index)."""
    if not pool:
        return [], 0

    batch = []
    idx = next_index % len(pool)
    for _ in range(min(batch_size, len(pool))):
        batch.append(pool[idx])
        idx = (idx + 1) % len(pool)

    return batch, idx


# ---------------------------------------------------------------------------
# Estado persistido + orquestacion con I/O real
# ---------------------------------------------------------------------------

@dataclass
class RotationState:
    pool: list[str] = field(default_factory=list)
    next_index: int = 0
    pool_last_refreshed: str | None = None
    reviewed_ever: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "RotationState":
        """Fuente de verdad: universe_state en Supabase. Si Supabase no esta accesible
        (sin red, proyecto pausado, etc.), cae al espejo local en disco para no bloquear
        al brain — pero eso puede estar un dia desactualizado, así que se avisa."""
        try:
            row = db.get_universe_state()
            if row is not None:
                state = cls(
                    pool=row["pool"],
                    next_index=row["next_index"],
                    pool_last_refreshed=(
                        row["pool_last_refreshed"].isoformat()
                        if row["pool_last_refreshed"] else None
                    ),
                    reviewed_ever=row["reviewed_ever"],
                )
                state._mirror_to_disk()
                return state
        except Exception as e:
            print(
                f"AVISO: no se pudo leer universe_state de Supabase ({e}). "
                f"Usando el espejo local en {ROTATION_STATE_FILE} si existe."
            )

        if ROTATION_STATE_FILE.exists():
            data = json.loads(ROTATION_STATE_FILE.read_text())
            return cls(**data)
        return cls()

    def save(self) -> None:
        """Escribe primero a Supabase (fuente de verdad); log_decision-style resiliencia ya
        vive dentro de db.save_universe_state (encola en pending_db_writes/ si falla). El
        espejo local se actualiza siempre, para que load() tenga algo razonable si Supabase
        no responde en la proxima corrida."""
        db.save_universe_state(
            pool=self.pool,
            next_index=self.next_index,
            pool_last_refreshed=self.pool_last_refreshed,
            reviewed_ever=self.reviewed_ever,
        )
        self._mirror_to_disk()

    def _mirror_to_disk(self) -> None:
        ROTATION_STATE_FILE.write_text(json.dumps(self.__dict__, indent=2))


def _load_universe_config() -> dict:
    import yaml
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "universe.yaml"
    return yaml.safe_load(config_path.read_text())


def refresh_pool_if_stale(state: RotationState, refresh_interval_days: int = 30) -> RotationState:
    """Los constituyentes del S&P 500 cambian pocas veces al año — no hace falta re-consultar
    la API cada dia. Solo refresca si el pool esta vacio o ya pasaron refresh_interval_days."""
    needs_refresh = state.pool_last_refreshed is None
    if not needs_refresh:
        last = date.fromisoformat(state.pool_last_refreshed)
        needs_refresh = (date.today() - last) > timedelta(days=refresh_interval_days)

    if needs_refresh:
        config = _load_universe_config()
        min_cap = config["filtros_cuantitativos"]["market_cap_minimo_usd"]
        constituents = fundamentals.get_sp500_constituents()
        screener_results = fundamentals.screen_by_market_cap(min_cap)

        # Anclar la rotacion al ticker donde ibamos ANTES de pisar el pool viejo — refrescar
        # el pool (verificacion periodica, no un evento raro) no deberia por si solo perder
        # semanas de progreso de cobertura reiniciando a 0 cada vez.
        anchor_ticker = (
            state.pool[state.next_index]
            if state.pool and 0 <= state.next_index < len(state.pool)
            else None
        )

        state.pool = build_quantitative_pool(constituents, screener_results)
        state.pool_last_refreshed = date.today().isoformat()

        if anchor_ticker and anchor_ticker in state.pool:
            state.next_index = state.pool.index(anchor_ticker)
        else:
            # El ancla ya no esta en el pool nuevo (dejo de calificar, fue adquirida, etc.)
            # — no hay una posicion "correcta" a la que volver, asi que se reinicia. Esto es
            # la excepcion (el pool cambio bajo los pies), no lo que pasa en cada refresh.
            state.next_index = 0

        state.save()

    return state


def get_weekly_batch() -> list[str]:
    """Punto de entrada principal para el brain: devuelve el lote de tickers a investigar
    esta semana, aplicando el filtro de cobertura de analistas de forma perezosa (ver nota de
    diseño arriba)."""
    config = _load_universe_config()
    batch_size = config["lote_rotativo"]["tickers_nuevos_por_semana"]
    min_analyst_coverage = config["filtros_cuantitativos"]["cobertura_analistas_minima"]

    state = RotationState.load()
    state = refresh_pool_if_stale(state)

    if not state.pool:
        raise RuntimeError(
            "El pool de candidatos esta vacio despues de refrescar — revisa que el "
            "screener y sp500-constituent de FMP esten devolviendo datos."
        )

    # Se camina el pool circularmente UN ticker a la vez, e idx solo avanza por los que de
    # verdad se inspeccionan (aceptados o rechazados por cobertura) — nunca por candidatos
    # "reservados" y despues descartados sin mirar. Antes esto pedia batch_size*2 candidatos
    # de una via select_next_batch() pero solo investigaba batch_size, y el indice avanzaba
    # igual por los que ni se llegaban a inspeccionar: la mitad del pool se saltaba cada
    # semana sin que nadie lo revisara. max_inspections acota esto a una vuelta completa al
    # pool por corrida, para no hacer loop infinito si casi nada cumple cobertura minima.
    accepted = []
    idx = state.next_index % len(state.pool)
    inspected = 0
    max_inspections = len(state.pool)

    while len(accepted) < batch_size and inspected < max_inspections:
        ticker = state.pool[idx]
        idx = (idx + 1) % len(state.pool)
        inspected += 1

        estimates = fundamentals.get_analyst_estimates(ticker, limit=1)
        analyst_count = 0
        if estimates:
            analyst_count = estimates[0].get("numAnalystsRevenue", 0) or 0
        if analyst_count >= min_analyst_coverage:
            accepted.append(ticker)

    state.next_index = idx
    state.reviewed_ever = list(set(state.reviewed_ever) | set(accepted))
    state.save()

    return accepted
