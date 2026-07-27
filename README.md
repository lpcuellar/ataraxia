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

## Setup rápido

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # y llenar con tus API keys reales
```

Base de datos (Supabase/Postgres) — ver `supabase/README.md` para el setup paso a paso
(crear el rol `ataraxia_brain`, conectar el repo, activar el despliegue de migraciones).

Después:
1. Verificar que la cuenta de paper trading de IBKR esté abierta
2. Correr el Client Portal Gateway localmente (ver docs de IBeam/ibind) — solo necesario
   desde Fase 5 (ejecución automatizada); durante paper trading la ejecución es manual
3. Confirmar el pipeline de datos: `python scripts/smoke_test_fmp.py`

## Estado actual
- **Fase 1 (datos) completa:** cliente FMP, precios/benchmark, embudo de candidatos de dos
  etapas, caché en disco.
- **Fase 3 (DB) implementada:** schema en `supabase/migrations/`, `src/db/models.py`
  conectado vía `psycopg2`, `RotationState` migrado a la tabla `universe_state`.
- **Pendiente:** `src/guardrails/validator.py` (validación determinista de guardrails).

## Estructura
```
ataraxia/
├── config/
│   └── universe.yaml       # pool de candidatos (filtro cuantitativo + rotación)
├── supabase/
│   ├── config.toml
│   ├── README.md            # setup de la base de datos
│   └── migrations/          # schema versionado, desplegado vía integración de GitHub
├── src/
│   ├── agent/                # prompt — la orquestación la hace esta sesión de Cowork
│   ├── guardrails/            # validación determinista, no negociable
│   ├── data/                   # fundamentales, mercado, embudo de candidatos
│   ├── broker/                  # wrapper sobre IBKR Client Portal API (Fase 5+)
│   └── db/                       # acceso a Supabase/Postgres (psycopg2)
├── dashboard/
└── scripts/
    └── run_daily.py            # helpers que el brain invoca por bash
```
