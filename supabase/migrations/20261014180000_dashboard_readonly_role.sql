-- Ataraxia — Migracion: rol de solo lectura para el dashboard web (Fase 4, docs/BUILD_PLAN.md).
--
-- Contexto (decision de LP, 2026-10-14): el dashboard es una app Next.js publica en Vercel,
-- con password gate, que lee el portafolio real. Mismo principio de minimo privilegio que
-- ataraxia_brain (sin DELETE/UPDATE/DDL) y ataraxia_executor (solo su alcance): esta app
-- JAMAS debe poder escribir nada, ni siquiera lo que brain puede. Es un visor, no un actor.
--
-- Por que un rol nuevo y no reusar ataraxia_brain: ataraxia_brain tiene INSERT en varias
-- tablas (recommendations, cash_events, portfolio_snapshots). Si la credencial de ese rol
-- se filtrara desde una variable de entorno de Vercel (configuracion mal hecha, log, etc.),
-- alguien podria escribir filas falsas. ataraxia_dashboard no puede escribir nada bajo
-- ninguna circunstancia: la unica exposicion de un leak es lectura de datos ya privados
-- detras del password gate, no integridad de la DB.
--
-- Conexion: mismo host/puerto que ataraxia_brain (pooler de Supabase, ya verificado en
-- produccion) — ver SUPABASE_DB_HOST en .env. Sin acceso de red distinto, solo un usuario
-- Postgres distinto con permisos mas chicos.
--
-- Aplicar desde el SQL Editor de Supabase con credenciales de admin.

create role ataraxia_dashboard with login password 'glDI6KyDAIPVwua5sWikPXdxn0Y4l0';

grant usage on schema public to ataraxia_dashboard;
grant select on portfolio_snapshots to ataraxia_dashboard;
grant select on portfolio_lots to ataraxia_dashboard;
grant select on cash_events to ataraxia_dashboard;
grant select on recommendations to ataraxia_dashboard;

-- Nada mas. Sin INSERT/UPDATE/DELETE, sin acceso a otras tablas (watchlist,
-- candidate_queue, executed_trades, decisions, etc.) — el dashboard no los necesita y
-- otorgarlos seria superficie de exposicion sin beneficio.
