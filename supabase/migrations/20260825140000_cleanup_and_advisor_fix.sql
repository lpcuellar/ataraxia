-- Ataraxia — Migracion 4: limpieza de las migraciones de prueba del deploy + cierre de un
-- advisory de seguridad detectado al validar el pipeline.
--
-- 1) Las dos migraciones de prueba (20260825120000, 20260825130000) solo agregaron comments
--    a `decisions`/`positions` para confirmar que el deploy automatico de GitHub funciona
--    (estaba roto: el tracker de Supabase nunca habia registrado las migraciones 1-3, que se
--    habian corrido a mano en el SQL Editor — se reparo insertando esos tres version IDs en
--    supabase_migrations.schema_migrations). Los comments ya cumplieron su proposito.
--
-- 2) `get_advisors` marco `public.rls_auto_enable()` (event trigger que Supabase instala por
--    default para auto-habilitar RLS en tablas nuevas — la funcion `ensure_rls`, real y util,
--    no se toca) como SECURITY DEFINER ejecutable por anon/authenticated. En la practica no es
--    explotable: al retornar `event_trigger`, Postgres rechaza cualquier invocacion directa
--    (SELECT rls_auto_enable() o vía /rest/v1/rpc/) fuera del mecanismo de event trigger — pero
--    el GRANT de EXECUTE via PUBLIC quedo ahi por default y conviene cerrarlo de todos modos.

comment on table public.decisions is null;
comment on table public.positions is null;

revoke execute on function public.rls_auto_enable() from public;
