# Ataraxia

Analista de inversiones de largo plazo que evalúa empresas con la filosofía de
**Joseph Carlson** y recomienda qué comprar, a qué precio y en qué momento.

Trabaja sobre el portafolio real de LP (export de Schwab), no sobre paper money.

## El marco de evaluación

Tres etapas, en orden fijo. Carlson es explícito: el foso se establece **antes** de mirar
valuación — una empresa barata sin foso no es una oportunidad, es una trampa.

**Paso previo, no negociable.** Verificar qué negocio es la empresa *hoy*, contra filings
recientes. Un ticker no cambia cuando la empresa sí. (Ver `src/agent/prompt.py` para el
caso que motivó esta regla.)

**Etapa 1 — Riesgo y foso durable. Eliminatoria.**
No es un checklist marcado: exige investigación con evidencia.
- Anatomía del foso: nombrarlo y mostrar el número que lo prueba
- Durabilidad como derivada: ROIC y margen bruto a 5-10 años, ¿se ensancha o se erosiona?
- **ROIC > WACC** — si el foso no se convierte en retorno, no es foso
- El caso del atacante: argumento adversarial con competidores reales. Eliminatorio.
- Verificación desagregada por segmento

**Etapa 2 — Checklist Carlson.** Basics (calidad, liderazgo, oportunidad, tipo de
crecimiento, moat) y balance (ingresos, utilidad neta, caja, deuda, deuda neta, acciones
en circulación).

**Etapa 3 — Valuación.** P/S relativo contra pares + TAM. De aquí salen precio objetivo
y momento de compra.

Las etapas son **filtros, no secciones de un informe**: lo que falla la Etapa 1 se reporta
en dos líneas y no avanza. La tesis completa se reserva para lo que pasa.

## La watchlist es el mecanismo central

> *"La mayoría de las empresas no cumplirán todas estas características, y las que sí rara
> vez cotizan con descuento. Recomiendo construir una lista de empresas que cumplan la
> mayoría y comprarlas cuando se presente una oportunidad decente."* — Carlson

La distinción es por dónde falló la empresa:
- **Falla el negocio** (Etapa 1 o 2) → se descarta
- **Falla solo el precio** (Etapa 3) → entra a la watchlist con precio objetivo

Crece despacio y por acumulación. Pero la paciencia es un medio, no el objetivo: si una
empresa pasa las tres etapas y hoy cotiza a un precio que lo vale, la recomendación es
compra hoy.

## Los dos flujos

```bash
venv/bin/python scripts/run_cycle.py barrido    # diario — rápido, encola
venv/bin/python scripts/run_cycle.py reporte    # lun/mié — analiza 2-3 a fondo
```

Separados a propósito: el ciclo anterior hacía todo junto y tardaba 10-60 minutos, con
timeouts. El barrido revisa estado y encola; el reporte consume la cola.

## Principio central

**El LLM propone, el código decide.** Los guardrails se validan en `src/guardrails/`
contra el portafolio real:

- Cartera objetivo: **8-15 acciones** (los ETFs no cuentan — ya son canastas)
- Máximo 15% de una acción individual al costo
- Revisión obligatoria de tesis si una posición cae -20%
- Sin operaciones intradía · solo acciones

## El portafolio

La fuente de verdad es el CSV que LP exporta de Schwab a `data/portfolio-YYYY-MM-DD.csv`.
El más reciente manda. Si tiene más de 14 días, los scripts lo marcan como viejo: una
tesis sobre un portafolio desactualizado es peor que ninguna.

LP ejecuta a mano; Ataraxia nunca opera en el mercado.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # llenar con credenciales reales
```

Base de datos: ver `supabase/README.md`. Las migraciones se despliegan solas al mergear
a `main` vía la integración de GitHub.

```bash
venv/bin/python scripts/verify_db_connection.py   # confirma conexión y permisos
```

## Estructura

```
ataraxia/
├── config/universe.yaml        # pool de candidatos
├── supabase/migrations/        # schema versionado
├── src/
│   ├── agent/prompt.py         # el framework — la fuente de verdad del criterio
│   ├── guardrails/             # validación determinista, no negociable
│   ├── data/                   # fundamentales, mercado, universo, portfolio_csv
│   ├── db/
│   │   ├── models.py           # esquema del fondo simulado (track record)
│   │   └── carlson.py          # watchlist, cola, bitácora, snapshots
│   └── reporting/
├── dashboard/
└── scripts/
    ├── run_cycle.py            # orquestador: barrido | reporte
    ├── brain_portfolio.py      # estado del portafolio real
    ├── brain_watchlist.py      # ver, agregar, revisar y cerrar entradas
    ├── brain_candidates.py     # alimenta la cola de candidatos
    ├── brain_fundamentals.py   # datos de un ticker
    ├── brain_decide.py         # propuestas validadas por guardrails
    ├── log_recommendation.py   # bitácora: recomendación + acción de LP
    └── compute_performance.py  # serie de snapshots vs S&P 500
```

## Datos

`brain_fundamentals.py` usa stockanalysis.com como fuente primaria y Yahoo Finance como
respaldo por campo (los valores de respaldo salen marcados `[yahoo]`). FMP quedó fuera:
sus endpoints devuelven 402.

Cuando dos fuentes discrepan, **no promediar** — reportar la discrepancia y verificar por
fuera. Ya pasó dos veces y ambas destapó un bug real.
