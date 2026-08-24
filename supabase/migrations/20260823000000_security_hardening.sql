-- Ataraxia — Migracion 3: cierre de brecha de seguridad (RLS/anon) + fix de grants para
-- snapshots del brain + refuerzo a nivel de DB del requisito de bear case.
--
-- Tres problemas encontrados en el review de arquitectura, ninguno relacionado al diseño de
-- los roles ataraxia_brain/ataraxia_executor en si (ese diseño esta bien):
--
-- 1) Ninguna de las dos migraciones anteriores revoca los privilegios por default que
--    Supabase otorga a los roles `anon` y `authenticated` sobre tablas nuevas en `public`.
--    Combinado con policies RLS "using (true)" (documentadas como defensa en profundidad,
--    no el mecanismo principal de scoping — ver migracion inicial), cualquiera con la
--    anon key publica del proyecto podria leer `decisions` e insertar filas fabricadas en
--    `executed_trades`/`cash_events`. Se cierra revocando explicitamente. Es seguro correr
--    este REVOKE aunque anon/authenticated nunca hayan tenido el privilegio — no falla.
--
-- 2) ataraxia_brain nunca recibio UPDATE en `positions`/`performance`, pero
--    src/db/models.py usa `insert ... on conflict (...) do update` en ambas — Postgres
--    exige el privilegio de UPDATE para preparar esa sentencia aunque el conflicto nunca
--    ocurra en un caso particular. Sin el grant, cada log_position_snapshot()/
--    log_performance_snapshot() fallaba en silencio y quedaba encolado para siempre en
--    data/pending_db_writes/. positions y performance nunca fueron parte de la garantia
--    "el brain no puede fabricar fills" (esa garantia es solo sobre
--    executed_trades/cash_events, y ahi el brain sigue sin nada mas que SELECT) asi que
--    otorgar UPDATE aqui no la debilita.
--
-- 3) bear_case/bear_case_probability eran nullable a nivel de DB — nada impedia que una
--    propuesta de trade se guardara sin ninguno de los dos, aunque PROJECT_PLAN.md y
--    src/guardrails/validator.py (ver migracion de codigo en el mismo commit) lo exigen.
--    Se agrega como CHECK "not valid" para no fallar si ya existen filas viejas sin estos
--    datos (proyecto en fase temprana, pero mejor no asumir) — sigue aplicando de lleno a
--    toda fila nueva desde ahora; validar las filas viejas es un paso manual aparte si hace
--    falta (`alter table decisions validate constraint ...`).

-- ============================================================================
-- 1) Cerrar el acceso publico via anon/authenticated
-- ============================================================================
revoke all on decisions, positions, performance, universe_state,
    executed_trades, cash_events
    from anon, authenticated;

alter default privileges in schema public revoke all on tables from anon, authenticated;

-- ============================================================================
-- 2) UPDATE en positions/performance para ataraxia_brain (soporta ON CONFLICT DO UPDATE)
-- ============================================================================
grant update on positions to ataraxia_brain;
grant update on performance to ataraxia_brain;

create policy "actualizar positions" on positions for update using (true) with check (true);
create policy "actualizar performance" on performance for update using (true) with check (true);

-- ============================================================================
-- 3) Bear case + probabilidad obligatorios en toda propuesta de trade
-- ============================================================================
alter table decisions add constraint decisions_trade_requires_bear_case
    check (
        entry_type <> 'trade'
        or (bear_case is not null and bear_case_probability is not null)
    ) not valid;
