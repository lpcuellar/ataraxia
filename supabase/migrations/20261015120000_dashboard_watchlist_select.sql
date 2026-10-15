-- Ataraxia — Migracion: el dashboard puede leer watchlist.
--
-- Contexto (LP, 2026-10-15): nueva pagina en el dashboard web con las candidatas en
-- espera de precio — el watchlist de Carlson (brain_watchlist.py). El rol
-- ataraxia_dashboard (migracion 20261014180000_dashboard_readonly_role.sql) solo tenia
-- SELECT sobre portfolio_snapshots, portfolio_lots, cash_events y recommendations; falta
-- watchlist. Mismo principio de minimo privilegio de siempre: solo SELECT, nunca
-- INSERT/UPDATE/DELETE.
--
-- Aplicar desde el SQL Editor de Supabase con credenciales de admin.

grant select on watchlist to ataraxia_dashboard;
