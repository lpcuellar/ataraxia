-- Ataraxia — Migracion 5: correccion de la migracion anterior.
--
-- `revoke execute on function public.rls_auto_enable() from public;` (migracion 4) no cerro
-- el advisory: anon/authenticated tenian el GRANT de EXECUTE directo (no heredado via PUBLIC),
-- como se ve en pg_proc.proacl (`anon=X/postgres`, `authenticated=X/postgres`). Revocar desde
-- PUBLIC no toca un grant directo a un rol especifico. Se revoca explicitamente de los dos
-- roles que importan aqui; se deja intacto para `service_role` (uso interno de Supabase) y
-- `postgres` (dueño de la funcion).

revoke execute on function public.rls_auto_enable() from anon, authenticated;
