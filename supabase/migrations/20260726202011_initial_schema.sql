-- Ataraxia — schema inicial de Supabase (Postgres).
-- Aplicado automaticamente por la integracion de GitHub cuando esto se mergea a main
-- (una vez que "Deploy to production" este activado en Project Settings > Integrations).
--
-- IMPORTANTE: la creacion del rol `ataraxia_brain` y su password NO estan en este archivo
-- a proposito — un CREATE ROLE con password committeado a git quedaria en el historial para
-- siempre, aunque despues se "corrija". Ese paso se hace una sola vez, a mano, desde el SQL
-- Editor de Supabase (ver supabase/README.md en esta misma carpeta).

-- ============================================================================
-- decisions: cada propuesta del brain — trade o revision sin accion.
-- Es el registro de auditoria central: rationale, bear case, y si paso el guardrail.
-- Nunca se actualiza ni se borra una fila despues de creada — es historial, no estado.
-- ============================================================================
create table if not exists decisions (
    id bigint generated always as identity primary key,
    date date not null,
    ticker text not null,
    entry_type text not null check (entry_type in ('trade', 'review')),
    action text check (action in ('buy', 'sell')),
    quantity numeric,
    price numeric,
    rationale text not null,
    bear_case text,
    bear_case_probability numeric check (bear_case_probability between 0 and 1),
    guardrail_result text not null check (guardrail_result in ('approved', 'rejected', 'n/a')),
    guardrail_rejection_reason text,
    created_at timestamptz not null default now()
);

create index if not exists idx_decisions_date on decisions (date);
create index if not exists idx_decisions_ticker on decisions (ticker);

-- ============================================================================
-- positions: snapshot diario de la cartera — una fila por ticker por dia.
-- ============================================================================
create table if not exists positions (
    id bigint generated always as identity primary key,
    date date not null,
    ticker text not null,
    quantity numeric not null,
    avg_cost numeric not null,
    current_value numeric not null,
    pct_of_portfolio numeric not null,
    created_at timestamptz not null default now(),
    unique (date, ticker)
);

create index if not exists idx_positions_date on positions (date);

-- ============================================================================
-- performance: snapshot diario del fondo completo vs. el benchmark S&P 500.
-- Alimenta la metrica de alpha relativo (PROJECT_PLAN.md Seccion 1) y el gate de
-- performance del criterio de graduacion (Seccion 8).
-- ============================================================================
create table if not exists performance (
    id bigint generated always as identity primary key,
    date date not null unique,
    fund_value numeric not null,
    sp500_equivalent_value numeric not null,
    cumulative_return_pct numeric not null,
    sp500_cumulative_return_pct numeric not null,
    current_drawdown_pct numeric not null,
    max_drawdown_pct numeric not null,
    sharpe_ratio numeric,
    created_at timestamptz not null default now()
);

-- ============================================================================
-- universe_state: memoria operacional del embudo de candidatos (src/data/universe.py).
-- Tabla singleton (una sola fila, id fijo en 1 via CHECK) — solo existe un universo.
--   pool                 -> resultado del filtro cuantitativo de Etapa 1 (lista de tickers)
--   next_index           -> puntero de rotacion de Etapa 2, donde quedo la ultima semana
--   pool_last_refreshed  -> para no re-consultar sp500-constituent + screener todos los dias
--   reviewed_ever        -> historico de que tickers ya se investigaron al menos una vez
-- ============================================================================
create table if not exists universe_state (
    id int primary key default 1 check (id = 1),
    pool jsonb not null default '[]'::jsonb,
    next_index int not null default 0,
    pool_last_refreshed date,
    reviewed_ever jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now()
);

insert into universe_state (id) values (1) on conflict (id) do nothing;

-- ============================================================================
-- Row Level Security — defensa en profundidad, no el mecanismo principal de scoping
-- ============================================================================
-- Si el brain se conecta con la "service_role" key de Supabase, RLS se IGNORA por completo
-- — esa key siempre tiene acceso total, por diseno de Supabase. El scoping real se logra con
-- el rol dedicado `ataraxia_brain` (creado a mano, ver supabase/README.md), no con RLS solo.

alter table decisions enable row level security;
alter table positions enable row level security;
alter table performance enable row level security;
alter table universe_state enable row level security;

create policy "insertar decisions" on decisions for insert with check (true);
create policy "leer decisions" on decisions for select using (true);

create policy "insertar positions" on positions for insert with check (true);
create policy "leer positions" on positions for select using (true);

create policy "insertar performance" on performance for insert with check (true);
create policy "leer performance" on performance for select using (true);

create policy "leer universe_state" on universe_state for select using (true);
create policy "actualizar universe_state" on universe_state
    for update using (true) with check (id = 1);

-- ============================================================================
-- Permisos del rol ataraxia_brain (el rol en si se crea a mano — ver supabase/README.md)
-- ============================================================================
-- Este GRANT si puede vivir en la migracion: no revela ningun secreto, y si el rol todavia
-- no existe cuando esto corre por primera vez, falla ruidosamente en vez de fallar en
-- silencio — lo cual es preferible (avisa que falta el paso manual documentado abajo).

grant usage on schema public to ataraxia_brain;

grant select, insert on decisions to ataraxia_brain;
grant select, insert on positions to ataraxia_brain;
grant select, insert on performance to ataraxia_brain;
grant select, update on universe_state to ataraxia_brain;

grant usage, select on all sequences in schema public to ataraxia_brain;
