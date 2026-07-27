"""
Wrapper sobre el Client Portal (Web) API de IBKR, via IBeam o ibind.

Decisiones ya tomadas (PROJECT_PLAN.md Seccion 3):
  - Client Portal API, NO TWS API (TWS no puede correr headless)
  - 2FA diaria aceptada como costo operacional fijo — requiere aprobacion push del usuario
    aproximadamente una vez al dia
  - Cuenta de paper trading primero, siempre, antes de cualquier capital real

Stub — implementar en Fase 0 (conexion) y Fase 3 (ejecucion de ordenes).
"""


class IBKRClient:
    def __init__(self, paper_trading: bool = True):
        self.paper_trading = paper_trading
        raise NotImplementedError(
            "Fase 0 — instalar y configurar IBeam o ibind primero, ver BUILD_PLAN.md"
        )

    def get_positions(self) -> list[dict]:
        raise NotImplementedError("Fase 3")

    def place_order(self, ticker: str, action: str, qty: float) -> dict:
        """Solo se llama despues de que la propuesta paso por
        src/guardrails/validator.py — nunca directamente desde el agente."""
        raise NotImplementedError("Fase 3")

    def keepalive(self) -> None:
        """Llamada periodica a /tickle para mantener la sesion viva entre la aprobacion
        2FA diaria."""
        raise NotImplementedError("Fase 0")
