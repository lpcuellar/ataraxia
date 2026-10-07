-- Ataraxia — Migracion: tablas del rediseño sobre el framework de Joseph Carlson.
--
-- Contexto: el fondo simulado se descarta y Ataraxia pasa a trabajar sobre el portafolio
-- real de LP. El framework de seis preguntas se reemplaza por tres etapas (riesgo y foso /
-- checklist / valuacion), y la watchlist deja de ser accesoria: es el mecanismo central.
--
-- Carlson lo dice directo: "La mayoria de las empresas no cumpliran todas estas
-- caracteristicas, y las que si rara vez cotizan con descuento. Recomiendo construir una
-- lista de empresas que cumplan la mayoria y comprarlas cuando se presente una oportunidad
-- decente."
--
-- Las tablas existentes (decisions, positions, performance, universe_state) NO se tocan:
-- decisions queda como track record historico.
--
-- Aplicar desde el SQL Editor de Supabase con credenciales de admin — ni ataraxia_brain ni
-- ataraxia_executor pueden hacer DDL, por diseño.

-- ============================================================================
-- watchlist: empresas que pasaron el filtro de NEGOCIO (Etapas 1 y 2) pero cuyo
-- precio todavia no justifica la compra.
--
-- La distincion es por donde fallo la empresa:
--   - falla el negocio  -> se descarta, no entra aqui
--   - falla solo el precio -> entra aqui, con precio objetivo, y se sigue
--
-- Crece despacio y por acumulacion. Muchas entradas por ciclo es señal de que se bajo
-- el estandar de las Etapas 1 y 2.
-- ============================================================================
create table if not exists watchlist (
    id bigint generated always as identity primary key,
    ticker text not null unique,
    company_name text,

    -- Veredicto de la Etapa 1 (riesgo y foso durable)
    moat_type text,                     -- marca | efecto_red | costos_cambio | ventaja_costo | escala
    moat_evidence text,                 -- el numero que lo prueba, no la narrativa
    moat_direction text check (moat_direction in ('ensanchando', 'estable', 'erosionando')),
    attacker_case text,                 -- el argumento adversarial, con nombre propio
    attacker_probability numeric check (attacker_probability between 0 and 1),

    -- Etapa 3 (valuacion): por que todavia no se compra
    thesis_summary text not null,
    target_price numeric,
    what_needs_to_happen text not null, -- que gatilla la compra
    price_at_entry numeric,             -- precio cuando entro a la lista, para medir espera

    status text not null default 'esperando'
        check (status in ('esperando', 'comprada', 'descartada')),
    removed_reason text,                -- por que salio: comprada, o el foso se erosiono

    added_at date not null default current_date,
    last_reviewed_at date,
    updated_at timestamptz not null default now()
);

create index if not exists idx_watchlist_status on watchlist (status);
create index if not exists idx_watchlist_reviewed on watchlist (last_reviewed_at);

-- ============================================================================
-- candidate_queue: cola entre el barrido diario de noticias y el reporte de lun/mie.
--
-- El barrido diario filtra agresivo y acumula aqui; el reporte consume la cola y
-- analiza 2-3 empresas a fondo. Separar las dos corridas evita que un solo ciclo
-- tenga que hacer todo (lo que ya causo timeouts de 60+ minutos).
-- ============================================================================
create table if not exists candidate_queue (
    id bigint generated always as identity primary key,
    ticker text not null,
    source text not null,               -- noticia | rotacion_universo | portafolio | watchlist
    reason text not null,               -- por que merece analisis profundo
    url text,
    priority int not null default 0,    -- mayor = antes
    status text not null default 'pendiente'
        check (status in ('pendiente', 'analizado', 'descartado')),
    queued_at timestamptz not null default now(),
    consumed_at timestamptz,
    unique (ticker, status)             -- un ticker no se encola dos veces pendiente
);

create index if not exists idx_queue_status on candidate_queue (status, priority desc);

-- ============================================================================
-- recommendations: la bitacora. Que recomendo Ataraxia y que acciono LP.
--
-- Separa explicitamente las dos cosas: la recomendacion es de Ataraxia, la ejecucion
-- es de LP y puede no ocurrir. Medir la brecha entre ambas es informacion util.
-- ============================================================================
create table if not exists recommendations (
    id bigint generated always as identity primary key,
    date date not null default current_date,
    ticker text not null,

    verdict text not null check (verdict in (
        'compra', 'agregar_watchlist', 'esperar_precio', 'descartar',
        'recortar', 'vender', 'mantener'
    )),

    -- El recorrido por las tres etapas
    stage1_moat text,
    stage1_verdict text check (stage1_verdict in ('pasa', 'falla')),
    stage2_checklist text,
    stage2_verdict text check (stage2_verdict in ('pasa', 'falla')),
    stage3_valuation text,

    price_at_recommendation numeric,
    target_price numeric,
    proposed_size_pct numeric,          -- % de cartera propuesto
    bear_case text,
    bear_case_probability numeric check (bear_case_probability between 0 and 1),
    rationale text not null,

    -- Que hizo LP. Null = todavia no decidio.
    lp_action text check (lp_action in ('ejecutada', 'rechazada', 'parcial', 'pendiente')),
    lp_action_at date,
    lp_executed_price numeric,
    lp_notes text,

    created_at timestamptz not null default now()
);

create index if not exists idx_recommendations_date on recommendations (date desc);
create index if not exists idx_recommendations_ticker on recommendations (ticker);
create index if not exists idx_recommendations_pending on recommendations (lp_action)
    where lp_action is null or lp_action = 'pendiente';

-- ============================================================================
-- portfolio_snapshots: serie historica del portafolio real de LP.
--
-- Una fila por CSV que LP sube. Alimenta la curva de performance del dashboard y la
-- comparacion contra el S&P 500. Sin esto, el dashboard no tiene de donde sacar la serie.
--
-- Guarda agregados, no el detalle por posicion: las posiciones del dia vivo salen del
-- CSV mas reciente, no de aqui.
-- ============================================================================
create table if not exists portfolio_snapshots (
    id bigint generated always as identity primary key,
    as_of date not null unique,
    source_file text not null,

    total_market_value numeric not null,
    total_cost_basis numeric not null,
    cash numeric not null default 0,

    equity_count int not null default 0,
    etf_count int not null default 0,

    sp500_close numeric,                -- para la comparacion relativa
    created_at timestamptz not null default now()
);

create index if not exists idx_snapshots_as_of on portfolio_snapshots (as_of desc);

-- ============================================================================
-- Permisos: mismo criterio que la migracion de security hardening.
--
-- anon/authenticated no tocan nada (el dashboard lee via endpoint propio, no directo).
-- ataraxia_brain puede insertar y leer; ademas update donde el flujo lo exige:
-- la watchlist se revisa en cada ciclo, la cola se marca consumida, y la bitacora
-- se completa cuando LP acciona.
--
-- Nota: a diferencia de decisions (inmutable por diseño), estas tablas si admiten
-- update — son estado vivo, no historial de auditoria.
-- ============================================================================
revoke all on watchlist, candidate_queue, recommendations, portfolio_snapshots
    from anon, authenticated;

grant select, insert, update on watchlist to ataraxia_brain;
grant select, insert, update on candidate_queue to ataraxia_brain;
grant select, insert, update on recommendations to ataraxia_brain;
grant select, insert on portfolio_snapshots to ataraxia_brain;

alter table watchlist enable row level security;
alter table candidate_queue enable row level security;
alter table recommendations enable row level security;
alter table portfolio_snapshots enable row level security;

create policy "brain lee watchlist" on watchlist for select using (true);
create policy "brain escribe watchlist" on watchlist for insert with check (true);
create policy "brain actualiza watchlist" on watchlist for update using (true) with check (true);

create policy "brain lee cola" on candidate_queue for select using (true);
create policy "brain escribe cola" on candidate_queue for insert with check (true);
create policy "brain actualiza cola" on candidate_queue for update using (true) with check (true);

create policy "brain lee recomendaciones" on recommendations for select using (true);
create policy "brain escribe recomendaciones" on recommendations for insert with check (true);
create policy "brain actualiza recomendaciones" on recommendations for update using (true) with check (true);

create policy "brain lee snapshots" on portfolio_snapshots for select using (true);
create policy "brain escribe snapshots" on portfolio_snapshots for insert with check (true);
