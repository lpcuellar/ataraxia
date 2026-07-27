"""
Capa de validacion de guardrails — codigo determinista, sin LLM involucrado.

Principio de diseño (BUILD_PLAN.md): el LLM propone, el codigo decide. Ninguna orden llega
a IBKR sin pasar por aqui. Si una propuesta viola un guardrail, se rechaza automaticamente
y se loguea la razon — Ataraxia (el agente) no tiene autoridad para saltarse esto.

Funciones puras: no hacen I/O (sin llamadas a DB, red, ni broker). El caller (el brain, y
mas adelante el executor de forma independiente) arma PortfolioState/TradeProposal con datos
ya obtenidos y le pasa el resultado a estas funciones. Esto es intencional: la misma
validacion debe poder correr dos veces — una vez en el brain (Cowork) y otra vez en el
executor, sin depender de que compartan conexion a DB ni estado mutable.

Guardrails implementados aqui (fuente de verdad: PROJECT_PLAN.md Seccion 1):
  - Maximo 15% de posicion individual al costo               -> validate_trade_proposal (hard)
  - Sin operaciones intradia (mismo ticker, compra y venta)   -> validate_trade_proposal (hard)
  - Cartera objetivo de 8-12 posiciones                       -> validate_trade_proposal (max
    es hard — no se abre una posicion #13; el minimo de 8 es un warning, no bloquea ventas
    forzadas por invalidacion de tesis, ver nota de diseño abajo)
  - Universo restringido a acciones (sin crypto, sin prediction markets) -> validate_trade_proposal (hard)
  - Suficiencia de cash (implicito, no listado explicitamente en PROJECT_PLAN.md pero
    obviamente necesario) -> validate_trade_proposal (hard)
  - Trigger de revision obligatoria a -20% desde costo        -> check_thesis_review_triggers
    (NO bloquea la propuesta en si — flaguea la posicion. Una vez flaggeada, no se le puede
    agregar mas hasta resolver la revision — eso si lo bloquea validate_trade_proposal)
  - Kill-switch de drawdown: desactivado durante paper trading -> check_drawdown_kill_switch
    (DRAWDOWN_KILL_SWITCH_PCT = None mientras estemos en paper; se activa en Fase 6)

Nota de diseño — por que el minimo de 8 posiciones NO es un bloqueo duro:
PROJECT_PLAN.md es explicito en que el control de riesgo real esta atado a la tesis, "no a
un porcentaje ciego de calendario" (mismo argumento usado para rechazar un kill-switch de
drawdown ciego). Bloquear una venta legitima por invalidacion de tesis solo para mantener un
conteo minimo de posiciones seria exactamente ese tipo de regla ciega — obligaria a sostener
una mala posicion. El minimo de 8 es una señal de diversificacion a vigilar, no una excusa
para no vender cuando la tesis se rompe.
"""

from dataclasses import dataclass, field


MAX_POSITION_PCT = 0.15
THESIS_REVIEW_TRIGGER_PCT = -0.20
TARGET_MIN_POSITIONS = 8
TARGET_MAX_POSITIONS = 12
DRAWDOWN_KILL_SWITCH_PCT = None  # None = desactivado (fase paper). Fase real: -0.25 a -0.30
ALLOWED_ASSET_CLASSES = {"stock"}


@dataclass
class Position:
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float

    @property
    def current_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_return_pct(self) -> float:
        if self.avg_cost == 0:
            return 0.0
        return (self.current_price - self.avg_cost) / self.avg_cost


@dataclass
class PortfolioState:
    positions: list[Position] = field(default_factory=list)
    cash: float = 0.0
    # Trades ya ejecutados HOY, para detectar same-day round-trips.
    # Cada uno: {"ticker": str, "action": "buy" | "sell"}
    todays_trades: list[dict] = field(default_factory=list)
    # Tickers actualmente pendientes de revision de tesis obligatoria (trigger de -20%),
    # todavia no resuelta. No se les puede agregar mas hasta que se resuelva la revision.
    flagged_for_review: set = field(default_factory=set)

    @property
    def total_value(self) -> float:
        return self.cash + sum(p.current_value for p in self.positions)

    def get_position(self, ticker: str) -> Position | None:
        for p in self.positions:
            if p.ticker == ticker:
                return p
        return None


@dataclass
class TradeProposal:
    ticker: str
    action: str  # "buy" | "sell"
    quantity: float
    price: float
    asset_class: str = "stock"

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass
class GuardrailResult:
    approved: bool
    reason: str
    warnings: list[str] = field(default_factory=list)


def validate_trade_proposal(proposal: TradeProposal, portfolio: PortfolioState) -> GuardrailResult:
    """Valida una propuesta de trade contra todos los guardrails aplicables.
    Debe correr ANTES de cualquier llamada a src/broker/ibkr_client.py, y se vuelve a correr
    de forma independiente en el executor — nunca confiar en un resultado ya aprobado que
    venga del brain.
    """
    if proposal.action not in ("buy", "sell"):
        return GuardrailResult(False, f"accion invalida: '{proposal.action}' (debe ser 'buy' o 'sell')")

    if proposal.quantity <= 0:
        return GuardrailResult(False, "la cantidad debe ser mayor a cero")

    if proposal.price <= 0:
        return GuardrailResult(False, "el precio debe ser mayor a cero")

    if proposal.asset_class not in ALLOWED_ASSET_CLASSES:
        return GuardrailResult(
            False,
            f"clase de activo no permitida: '{proposal.asset_class}' "
            f"(universo restringido a {sorted(ALLOWED_ASSET_CLASSES)})",
        )

    for trade in portfolio.todays_trades:
        if trade["ticker"] == proposal.ticker and trade["action"] != proposal.action:
            return GuardrailResult(
                False,
                f"operacion intradia no permitida: ya hubo un '{trade['action']}' de "
                f"{proposal.ticker} hoy, no se permite '{proposal.action}' el mismo dia",
            )

    existing = portfolio.get_position(proposal.ticker)

    if proposal.action == "sell":
        held_qty = existing.quantity if existing else 0
        if existing is None:
            return GuardrailResult(False, f"no se puede vender {proposal.ticker}: no hay posicion abierta")
        if proposal.quantity > held_qty:
            return GuardrailResult(
                False,
                f"no se puede vender {proposal.quantity} de {proposal.ticker}: solo se tienen {held_qty}",
            )
        return GuardrailResult(True, "aprobado")

    # proposal.action == "buy" a partir de aqui
    if proposal.ticker in portfolio.flagged_for_review:
        return GuardrailResult(
            False,
            f"{proposal.ticker} esta marcado para revision obligatoria de tesis "
            f"(cayo {THESIS_REVIEW_TRIGGER_PCT:.0%} o mas desde costo) — no se puede agregar "
            f"hasta resolver la revision",
        )

    if proposal.notional > portfolio.cash:
        return GuardrailResult(
            False,
            f"cash insuficiente: se necesitan ${proposal.notional:,.2f}, hay ${portfolio.cash:,.2f}",
        )

    is_new_position = existing is None
    if is_new_position and len(portfolio.positions) >= TARGET_MAX_POSITIONS:
        return GuardrailResult(
            False,
            f"no se puede abrir una posicion nueva en {proposal.ticker}: la cartera ya tiene "
            f"{len(portfolio.positions)} posiciones (maximo objetivo: {TARGET_MAX_POSITIONS})",
        )

    existing_value = existing.current_value if existing else 0.0
    resulting_position_value = existing_value + proposal.notional
    total_value = portfolio.total_value
    resulting_pct = resulting_position_value / total_value if total_value > 0 else float("inf")
    if resulting_pct > MAX_POSITION_PCT:
        return GuardrailResult(
            False,
            f"la compra dejaria a {proposal.ticker} en {resulting_pct:.1%} de la cartera "
            f"(maximo permitido: {MAX_POSITION_PCT:.0%})",
        )

    warnings = []
    resulting_count = len(portfolio.positions) + (1 if is_new_position else 0)
    if resulting_count < TARGET_MIN_POSITIONS:
        warnings.append(
            f"la cartera queda con {resulting_count} posiciones, debajo del objetivo "
            f"minimo de {TARGET_MIN_POSITIONS} — no bloquea la operacion, solo aviso"
        )

    return GuardrailResult(True, "aprobado", warnings=warnings)


def check_thesis_review_triggers(portfolio: PortfolioState) -> list[str]:
    """Chequeo diario, no bloqueante: que posiciones cayeron THESIS_REVIEW_TRIGGER_PCT (-20%)
    o mas desde costo y necesitan una revision obligatoria de tesis. No vende nada
    automaticamente — solo flaguea. El brain debe reportar estas revisiones explicitamente."""
    return [
        p.ticker for p in portfolio.positions
        if p.unrealized_return_pct <= THESIS_REVIEW_TRIGGER_PCT
    ]


def check_drawdown_kill_switch(current_drawdown_pct: float) -> GuardrailResult:
    """Chequeo a nivel fondo, no por-trade. Durante paper trading DRAWDOWN_KILL_SWITCH_PCT es
    None, asi que esto siempre aprueba (el drawdown solo se monitorea, ver PROJECT_PLAN.md
    Seccion 1). Se activa unicamente en Fase 6 con capital real.

    current_drawdown_pct se espera negativo o cero (p.ej. -0.12 para un drawdown del 12%).
    """
    if DRAWDOWN_KILL_SWITCH_PCT is None:
        return GuardrailResult(True, "kill-switch de drawdown desactivado (fase paper trading)")

    if current_drawdown_pct <= DRAWDOWN_KILL_SWITCH_PCT:
        return GuardrailResult(
            False,
            f"kill-switch de drawdown activado: drawdown actual {current_drawdown_pct:.1%} "
            f"alcanzo el umbral {DRAWDOWN_KILL_SWITCH_PCT:.0%} — no se permiten nuevas compras",
        )

    return GuardrailResult(True, "drawdown dentro de limites")
