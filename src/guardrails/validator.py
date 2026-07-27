"""
Capa de validacion de guardrails — codigo determinista, sin LLM involucrado.

Principio de diseño (BUILD_PLAN.md): el LLM propone, el codigo decide. Ninguna orden llega
a IBKR sin pasar por aqui. Si una propuesta viola un guardrail, se rechaza automaticamente
y se loguea la razon — Ataraxia (el agente) no tiene autoridad para saltarse esto.

Guardrails implementados aqui (fuente de verdad: PROJECT_PLAN.md Seccion 1):
  - Maximo 15% de posicion individual al costo
  - Trigger de revision obligatoria (no venta automatica) a -20% desde costo
  - Sin operaciones intradia (mismo ticker, mismo dia, compra y venta)
  - Cartera objetivo de 8-12 posiciones
  - Universo restringido a acciones (sin crypto, sin prediction markets)
  - Kill-switch de drawdown: DESACTIVADO durante paper trading (solo monitoreo).
    Se activa (25-30%) unicamente en fase de capital real — ver PROJECT_PLAN.md Seccion 8.

Stub — implementar en Fase 2, junto con agent/tools.py.
"""

from dataclasses import dataclass


MAX_POSITION_PCT = 0.15
THESIS_REVIEW_TRIGGER_PCT = -0.20
TARGET_MIN_POSITIONS = 8
TARGET_MAX_POSITIONS = 12
DRAWDOWN_KILL_SWITCH_PCT = None  # None = desactivado (fase paper). Fase real: -0.25 a -0.30


@dataclass
class GuardrailResult:
    approved: bool
    reason: str


def validate_trade_proposal(proposal: dict, current_portfolio: dict) -> GuardrailResult:
    """Valida una propuesta de trade contra todos los guardrails aplicables.
    Debe correr ANTES de cualquier llamada a src/broker/ibkr_client.py.
    """
    raise NotImplementedError("Fase 2 — implementar cada chequeo listado arriba")
