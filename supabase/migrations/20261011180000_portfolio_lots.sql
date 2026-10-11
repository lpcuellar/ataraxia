-- Ataraxia — Migracion: lotes del portafolio real, versionados.
--
-- Contexto (decision de LP, 2026-10-11): el portafolio deja de vivir solo como archivo CSV
-- en disco y pasa a Supabase, para tener historico versionado en vez de un archivo que se
-- sobreescribe. portfolio_snapshots (migracion 20261007200000_carlson_redesign) ya guarda los
-- agregados por fecha de corte; lo que faltaba es el detalle.
--
-- Por que a nivel de LOTE y no de posicion: el export "Lot Details" de Schwab trae la fecha
-- de compra y el costo de cada compra por separado. Esa informacion es la que permite
--   (a) distinguir short term de long term para decisiones fiscales,
--   (b) medir cuanto tiempo lleva sostenida una tesis,
--   (c) reconstruir el costo promedio sin confiar en un numero ya agregado por el broker.
-- El export "Positions" no la trae, y una vez agregada no se puede recuperar.
--
-- Las posiciones por ticker NO se guardan como tabla aparte: se derivan de los lotes con la
-- vista portfolio_positions. Una sola fuente de verdad, sin riesgo de que agregado y detalle
-- se contradigan.
--
-- Aplicar desde el SQL Editor de Supabase con credenciales de admin — ni ataraxia_brain ni
-- ataraxia_executor pueden hacer DDL, por diseño.

-- ============================================================================
-- portfolio_lots: un renglon por lote (compra individual) de un snapshot.
-- ============================================================================
create table if not exists portfolio_lots (
    id bigint generated always as identity primary key,
    snapshot_id bigint not null references portfolio_snapshots (id) on delete cascade,

    ticker text not null,

    -- Separar equities de ETFs es un requisito de la evaluacion, no cosmetico: LP decidio
    -- (2026-10-11) que el alpha de Ataraxia se mide SOLO sobre equities. Los ETFs amplios
    -- (VOO/SCHD/VXUS) son un ancla pasiva fuera del mandato del agente — incluirlos en la
    -- medicion diluiria justamente lo que se quiere medir, porque VOO *es* el benchmark.
    asset_class text not null check (asset_class in ('equity', 'etf', 'cash')),

    open_date date not null,              -- fecha de compra del lote, del export de Schwab
    quantity numeric not null check (quantity > 0),
    cost_per_share numeric not null,
    cost_basis numeric not null,

    -- Precio y valor al momento del snapshot. Se guardan para poder reconstruir el estado
    -- tal como se vio ese dia; para decisiones se usa el precio en vivo, no este.
    price_at_snapshot numeric,
    market_value numeric,

    holding_period text check (holding_period in ('Short Term', 'Long Term')),

    created_at timestamptz not null default now()
);

create index if not exists idx_lots_snapshot on portfolio_lots (snapshot_id);
create index if not exists idx_lots_ticker on portfolio_lots (ticker);
create index if not exists idx_lots_snapshot_ticker on portfolio_lots (snapshot_id, ticker);

-- Un mismo ticker puede tener dos lotes con la MISMA fecha de apertura (verificado en el
-- export del 2026-10-08: META tiene dos lotes del 03/26/2026 con cantidades distintas), asi
-- que (snapshot, ticker, open_date) NO es unico. No se declara unique constraint a proposito.

-- ============================================================================
-- portfolio_positions: posiciones agregadas, derivadas de los lotes.
-- ============================================================================
create or replace view portfolio_positions as
select
    l.snapshot_id,
    s.as_of,
    l.ticker,
    l.asset_class,
    sum(l.quantity)                                        as quantity,
    sum(l.cost_basis)                                      as cost_basis,
    sum(l.cost_basis) / nullif(sum(l.quantity), 0)         as avg_cost_per_share,
    max(l.price_at_snapshot)                               as price_at_snapshot,
    sum(l.market_value)                                    as market_value,
    sum(l.market_value) - sum(l.cost_basis)                as gain_loss,
    count(*)                                               as lot_count,
    min(l.open_date)                                       as first_open_date
from portfolio_lots l
join portfolio_snapshots s on s.id = l.snapshot_id
group by l.snapshot_id, s.as_of, l.ticker, l.asset_class;

-- ============================================================================
-- Permisos: mismo criterio que las migraciones anteriores.
--
-- ataraxia_brain necesita insert (el cargador de snapshots corre con ese rol) y select.
-- Sin update ni delete: un snapshot es un hecho historico fechado, no estado mutable — si un
-- export sale mal, se carga otro snapshot con otra fecha, no se edita el anterior.
-- ============================================================================
revoke all on portfolio_lots from anon, authenticated;
revoke all on portfolio_positions from anon, authenticated;

grant select, insert on portfolio_lots to ataraxia_brain;
grant select on portfolio_positions to ataraxia_brain;

alter table portfolio_lots enable row level security;

create policy "brain lee lotes" on portfolio_lots for select using (true);
create policy "brain escribe lotes" on portfolio_lots for insert with check (true);
