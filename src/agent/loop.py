"""
Orquestacion del loop diario de Ataraxia.

Flujo (ver PROJECT_PLAN.md Seccion 2 y BUILD_PLAN.md Fase 2):
  1. Revisar posiciones existentes (siempre, todos los dias)
  2. Investigar candidatos nuevos del lote rotativo semanal (config/universe.yaml)
  3. Generar decisiones/resumenes via Claude con tool use
  4. Validar cualquier propuesta de trade contra los guardrails (src/guardrails/validator.py)
  5. Ejecutar lo aprobado, loguear todo (aprobado y rechazado)
  6. Generar el resumen diario

Stub — implementar en Fase 2.
"""


def run_daily_cycle() -> None:
    raise NotImplementedError(
        "Fase 2 — depende de agent/prompt.py, agent/tools.py, y guardrails/validator.py "
        "estando implementados primero."
    )


if __name__ == "__main__":
    run_daily_cycle()
