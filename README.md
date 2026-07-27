# Ataraxia

Agente de IA que gestiona un fondo de inversión pequeño de largo plazo, replicando el método
de The Claude Portfolio (@theaiportfolios) con la voz y disciplina de Joseph Carlson.

Ver la documentación completa en la carpeta del proyecto (fuera de este repo de código):
- `PROJECT_PLAN.md` — estrategia, métricas, guardrails, criterio de graduación
- `BUILD_PLAN.md` — roadmap técnico, fases, decisiones de arquitectura

## Principio central
El LLM propone, el código decide. Todos los guardrails se validan en `src/guardrails/`
antes de que cualquier orden llegue al broker. Ver `BUILD_PLAN.md` para el razonamiento
completo.

## Setup rápido (Fase 0)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # y llenar con tus API keys reales
```

Después:
1. Verificar que la cuenta de paper trading de IBKR esté abierta
2. Correr el Client Portal Gateway localmente (ver docs de IBeam/ibind)
3. Confirmar conexión: `python scripts/run_daily.py --dry-run`

## Estado actual
Scaffold inicial — Fase 0/1 del `BUILD_PLAN.md`. Sin lógica de negocio implementada todavía;
los módulos en `src/` tienen stubs con la responsabilidad de cada uno documentada.

## Estructura
```
ataraxia/
├── config/
│   └── universe.yaml      # pool de candidatos (filtro cuantitativo + rotación)
├── src/
│   ├── agent/              # prompt, tools, loop de orquestación
│   ├── guardrails/          # validación determinista, no negociable
│   ├── data/                 # fundamentales + mercado
│   ├── broker/                # wrapper sobre IBKR Client Portal API
│   └── db/                     # schema y modelos (SQLite)
├── dashboard/
└── scripts/
    └── run_daily.py         # entry point del scheduler
```
