# Ataraxia — Dashboard

App Next.js (Fase 4, `docs/BUILD_PLAN.md`) que muestra el portafolio real de LP: retorno de
equities vs. S&P 500, posiciones, distribución, métricas de riesgo y la bitácora de
recomendaciones. Lee Supabase en modo solo lectura y no escribe nada.

## Arquitectura

- **Datos**: conexión de solo lectura a Supabase vía el rol `ataraxia_dashboard`
  (`supabase/migrations/20261014180000_dashboard_readonly_role.sql`). Ese rol no tiene
  INSERT/UPDATE/DELETE sobre nada — ni siquiera lo que tiene `ataraxia_brain`. Las consultas
  viven en `lib/db.ts` y corren siempre en el servidor (`import "server-only"` evita que la
  credencial llegue al bundle del navegador).
- **Métricas**: `lib/metrics.ts` replica en TypeScript la lógica ya validada en Python
  (`src/guardrails/validator.py`, `src/data/portfolio_csv.py`, `src/reporting/performance.py`):
  el alpha se mide SOLO sobre equities (decisión de LP 2026-10-11), el tope de concentración
  es 25% sobre el costo de las acciones (decisión de LP 2026-10-14), y el Sharpe no se
  muestra con menos de 5 snapshots en vez de dar un número que sería ruido.
- **Acceso**: password gate simple (`middleware.ts` + `lib/auth.ts`), pensado para un solo
  visitante. Sin usuarios, sin tabla de sesiones — una cookie firmada con HMAC alcanza.

## Correr en local

```bash
npm install
cp .env.local.example .env.local   # completar los tres valores, ver abajo
npm run dev
```

### Variables de entorno

Ver `.env.local.example`. Las tres que hay que completar:

- `DASHBOARD_DB_PASSWORD` — la contraseña del rol `ataraxia_dashboard` (la generó Kai al
  escribir la migración; pedírsela si se perdió, o rotarla con `ALTER ROLE ... PASSWORD`).
- `DASHBOARD_PASSWORD` — la contraseña que vos vas a escribir en el navegador. Elegila.
- `SESSION_SECRET` — generar con `openssl rand -base64 32`.

**Ojo con `DASHBOARD_DB_USER`**: tiene que llevar el project ref de Supabase pegado
(`ataraxia_dashboard.<ref>`), no solo el nombre del rol — el pooler de Supabase (Supavisor)
identifica el proyecto por ahí, porque el host (`aws-0-us-east-2.pooler.supabase.com`) es
compartido entre todos los proyectos de la región. El ref está en `SUPABASE_DB_USER` del
`.env` de la raíz del repo (mismo ref para todos los roles del proyecto).

## Desplegar en Vercel

1. Conectar este repo a Vercel, con **Root Directory = `web`** (el repo tiene el proyecto
   Python en la raíz; Vercel tiene que construir solo esta subcarpeta).
2. Configurar las mismas tres variables de entorno de arriba en Vercel → Settings →
   Environment Variables. `DASHBOARD_DB_HOST`/`PORT`/`NAME`/`USER` también, si no se quiere
   depender de los defaults hardcodeados en `lib/db.ts`.
3. Deploy. No hace falta build command custom — Next.js lo detecta solo.

## Qué NO hace a propósito

- No escribe nada en Supabase. Ni un INSERT.
- No muestra `cash_events` ni tablas fuera de las cuatro que el rol puede leer
  (`portfolio_snapshots`, `portfolio_lots`, `recommendations`) — si se necesita algo más,
  hay que agregar el GRANT en una migración nueva primero.
