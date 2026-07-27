-- Ataraxia — Migracion 2: soporte para el executor automatizado (paper trading).
--
-- Diseño (ver BUILD_PLAN.md "Fase 3.5"): el brain (Cowork) escribe propuestas aprobadas en
-- `decisions`; el executor (script separado en Docker, junto al IBKR Gateway) las lee,
-- RE-VALIDA los guardrails de forma independiente, ejecuta contra la cuenta paper, y
-- registra el fill real. La verdad sobre "que hay en la cuenta" se deriva SOLO de
-- executed_trades + cash_events, que unicamente el executor puede escribir.
--
-- Igual que en la migracion inicial: el rol `ataraxia_executor` se crea A MANO en el SQL
-- Editor (password fuera de Git):
--   create role ataraxia_executor login password 'PASSWORD_FUERTE_Y_UNICA';
-- Este archivo solo hace los GRANT — falla ruidosamente si el rol no existe todavia.

-- ============================================================================
-- executed_trades: fills reales en la cuenta de IBKR. UNICA fuente de verdad de posiciones.
-- Solo el executor escribe aqui. El brain la lee para armar su PortfolioState diario.
-- ============================================================================
create table if not exists executed_trades (
    id bigint generated always as identity primary key,
    date date not null,
    ticker text not null,
    action text not null check (action in ('buy', 'sell')),
    quantity numeric not null check (quantity > 0),
    price numeric not null check (price > 0),
    decision_id bigint references decisions (id),  -- propuesta que origino el fill (nullable)
    created_at timestamptz not null default now()
);

create index if not exists idx_executed_trades_date on executed_trades (date);
create index if not exists idx_executed_trades_ticker on executed_trades (ticker);

-- ============================================================================
-- cash_events: movimientos de cash que no son trades (deposito inicial, dividendos, fees).
-- Cash actual = sum(cash_events.amount) - compras + ventas (derivado, no almacenado).
-- ============================================================================
create table if not exists cash_events (
    id bigint generated always as identity primary key,
    date date not null,
    event_type text not null check (event_type in ('deposit', 'withdrawal', 'dividend', 'fee', 'interest')),
    amount numeric not null,  -- positivo = entra cash; negativo = sale (withdrawal/fee)
    note text,
    created_at timestamptz not null default now()
);

-- ============================================================================
-- decisions: extensiones para el handoff brain -> executor
-- ============================================================================
-- 1) entry_type ahora incluye eventos de revision de tesis (en vez de una tabla aparte):
--    'thesis_flag' (posicion cayo -20%, revision obligatoria pendiente) y
--    'thesis_resolution' (revision hecha; rationale explica la conclusion).
--    "Actualmente flaggeado" = tickers cuyo ultimo evento de tesis es flag sin resolution.
alter table decisions drop constraint if exists decisions_entry_type_check;
alter table decisions add constraint decisions_entry_type_check
    check (entry_type in ('trade', 'review', 'thesis_flag', 'thesis_resolution'));

-- 2) execution_status: ciclo de vida de una propuesta de trade aprobada.
--    NULL para entradas que no son propuestas ejecutables (reviews, flags).
--    'pending' -> el executor la ve -> 'executed' | 'failed' | 'skipped'
alter table decisions add column if not exists execution_status text
    check (execution_status in ('pending', 'executed', 'failed', 'skipped'));
alter table decisions add column if not exists execution_note text;

create index if not exists idx_decisions_execution_status on decisions (execution_status)
    where execution_status = 'pending';

-- ============================================================================
-- RLS
-- ============================================================================
alter table executed_trades enable row level security;
alter table cash_events enable row level security;

create policy "insertar executed_trades" on executed_trades for insert with check (true);
create policy "leer executed_trades" on executed_trades for select using (true);

create policy "insertar cash_events" on cash_events for insert with check (true);
create policy "leer cash_events" on cash_events for select using (true);

-- decisions ya tiene RLS activo con policies de insert/select solamente — sin una policy de
-- UPDATE, el executor no podria actualizar execution_status aunque tenga el GRANT de columna.
-- (El GRANT de columna sigue siendo lo que limita QUE puede tocar; esta policy solo permite
-- que el update ocurra.)
create policy "actualizar estado de ejecucion" on decisions for update using (true) with check (true);

-- ============================================================================
-- Permisos — la separacion brain/executor aplicada a nivel de base de datos
-- ============================================================================
-- brain: lee las tablas del executor, jamas las escribe (no puede "inventar" un fill)
grant select on executed_trades to ataraxia_brain;
grant select on cash_events to ataraxia_brain;

-- executor: escribe fills y cash; lee propuestas; SOLO puede actualizar las columnas de
-- estado de ejecucion en decisions (grant a nivel de columna), no el contenido de la
-- propuesta (rationale, bear case, etc. quedan intactos — son del brain)
grant usage on schema public to ataraxia_executor;
grant select, insert on executed_trades to ataraxia_executor;
grant select, insert on cash_events to ataraxia_executor;
grant select on decisions to ataraxia_executor;
grant update (execution_status, execution_note) on decisions to ataraxia_executor;
grant select on positions to ataraxia_executor;
grant select on performance to ataraxia_executor;
grant usage, select on all sequences in schema public to ataraxia_executor;
