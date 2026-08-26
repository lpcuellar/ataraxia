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
- **Datos, guardrails y DB implementados:** cliente FMP, precios/benchmark, embudo de
  candidatos de dos etapas, caché en disco; `src/guardrails/validator.py` (validación
  determinista, incluyendo el tope de 15% al costo y el trigger de revisión de tesis a -20%,
  ambos ya cableados en `validate_trade_proposal`); schema en `supabase/migrations/`,
  `src/db/models.py` conectado vía `psycopg2`.
- **Ejecución manual (arquitectura "mimetizar a The Claude Portfolio de cerca"):** el humano
  ejecuta todo en IBKR directamente; `scripts/log_manual_trade.py` registra la verdad de la
  cuenta. `src/executor/`, `src/broker/ibkr_client.py` y `docker/` implementan un executor
  automatizado que ya no es parte de la arquitectura objetivo — quedan en el repo sin usarse,
  pendientes de limpieza.
- **Pendiente:** programar la sesión de Cowork/Routine que sigue `src/agent/prompt.py` a
  diario — el código que esa sesión invoca por bash (`scripts/brain_*.py`) ya existe y está
  probado, falta el paso de configurar la tarea programada en el dashboard.

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
│   ├── agent/                # prompt — la orquestación la hace la sesión de Cowork/Routine
│   ├── guardrails/            # validación determinista, no negociable
│   ├── data/                   # fundamentales, mercado, embudo de candidatos
│   ├── reporting/                # métricas de performance + reconstrucción del portfolio
│   ├── broker/                     # wrapper sobre IBKR Client Portal API — sin usar (ver Estado actual)
│   ├── executor/                    # executor automatizado — sin usar (ver Estado actual)
│   └── db/                           # acceso a Supabase/Postgres (psycopg2)
├── dashboard/
└── scripts/
    ├── brain_portfolio.py      # estado del portafolio — el brain lo invoca por bash
    ├── brain_candidates.py     # lote rotativo de candidatos — el brain lo invoca por bash
    ├── brain_fundamentals.py   # datos fundamentales de un ticker — el brain lo invoca por bash
    ├── brain_decide.py         # registra propuestas/revisiones — el brain lo invoca por bash
    ├── log_manual_trade.py     # el humano registra fills/cash reales ejecutados en IBKR
    └── run_daily.py            # reporte de solo lectura para el humano
```
