import "server-only";
import postgres from "postgres";

// Conexion de SOLO LECTURA al Supabase de Ataraxia, via el rol ataraxia_dashboard (ver
// supabase/migrations/20261014180000_dashboard_readonly_role.sql). Ese rol no tiene
// INSERT/UPDATE/DELETE sobre nada — ni siquiera lo que tiene ataraxia_brain. Si esta
// credencial se filtrara, lo unico expuesto es lectura de datos ya privados detras del
// password gate, no la integridad de la base.
//
// "server-only" en el import de arriba hace que Next.js reviente el build si este modulo
// se importa accidentalmente desde un componente cliente — la credencial nunca debe llegar
// al bundle del navegador.
const sql = postgres({
  host: process.env.DASHBOARD_DB_HOST,
  port: Number(process.env.DASHBOARD_DB_PORT ?? 5432),
  database: process.env.DASHBOARD_DB_NAME ?? "postgres",
  username: process.env.DASHBOARD_DB_USER,
  password: process.env.DASHBOARD_DB_PASSWORD,
  ssl: "require",
  // Vercel invoca funciones serverless de corta vida; un pool chico evita acumular
  // conexiones ociosas contra el pooler de Supabase entre invocaciones.
  max: 5,
  idle_timeout: 20,
  types: {
    // postgres.js parsea columnas `date` (oid 1082) como objetos Date de JS por defecto.
    // Todas las fechas de este esquema (as_of, open_date, date, lp_action_at) son `date`,
    // no `timestamp`, y el resto del codigo las trata como strings "YYYY-MM-DD" (para
    // ordenar con localeCompare, armar keys, etc.) — igual que el lado Python, que las lee
    // de Supabase sin conversion. Se desactiva el parseo solo para 1082, dejando
    // timestamp/timestamptz (1114/1184) con el comportamiento default por si algun dia se
    // usan.
    plainDate: { to: 1082, from: [1082], serialize: (x: string) => x, parse: (x: string) => x },
  },
});

export type PortfolioSnapshotRow = {
  id: number;
  as_of: string;
  cash: string;
  total_market_value: string;
  total_cost_basis: string;
  sp500_close: string | null;
};

export async function getSnapshotHistory(): Promise<PortfolioSnapshotRow[]> {
  return sql<PortfolioSnapshotRow[]>`
    select id, as_of, cash, total_market_value, total_cost_basis, sp500_close
    from portfolio_snapshots
    order by as_of asc
  `;
}

export type LotRow = {
  snapshot_id: number;
  ticker: string;
  asset_class: string;
  open_date: string;
  quantity: string;
  cost_per_share: string;
  cost_basis: string;
  price_at_snapshot: string | null;
  market_value: string | null;
  holding_period: string | null;
};

/** Lotes de un snapshot puntual. Se pide por id, no "el mas reciente" aca adentro, para que
 * el caller decida cual snapshot usar sin que esta funcion tenga que saberlo. */
export async function getLotsForSnapshot(snapshotId: number): Promise<LotRow[]> {
  return sql<LotRow[]>`
    select snapshot_id, ticker, asset_class, open_date, quantity, cost_per_share,
           cost_basis, price_at_snapshot, market_value, holding_period
    from portfolio_lots
    where snapshot_id = ${snapshotId}
    order by ticker, open_date desc
  `;
}

/** Suma de costo/valor por ticker y clase de activo, para TODOS los snapshots a la vez —
 * una sola consulta en vez de N+1 por snapshot, para construir la serie equities-only de
 * performance (decision de LP 2026-10-11: el alpha se mide solo sobre equities). */
export async function getEquityAggregatesBySnapshot(): Promise<
  { snapshot_id: number; asset_class: string; cost_basis: string; market_value: string }[]
> {
  return sql`
    select snapshot_id, asset_class,
           sum(cost_basis) as cost_basis,
           sum(coalesce(market_value, 0)) as market_value
    from portfolio_lots
    group by snapshot_id, asset_class
  `;
}

export type RecommendationRow = {
  id: number;
  date: string;
  ticker: string;
  verdict: string;
  rationale: string;
  stage1_moat: string | null;
  stage2_checklist: string | null;
  stage3_valuation: string | null;
  price_at_recommendation: string | null;
  target_price: string | null;
  bear_case: string | null;
  bear_case_probability: string | null;
  lp_action: string | null;
  lp_action_at: string | null;
  lp_executed_price: string | null;
  lp_notes: string | null;
};

export async function getRecommendations(limit = 50): Promise<RecommendationRow[]> {
  return sql<RecommendationRow[]>`
    select id, date, ticker, verdict, rationale, stage1_moat, stage2_checklist,
           stage3_valuation, price_at_recommendation, target_price, bear_case,
           bear_case_probability, lp_action, lp_action_at, lp_executed_price, lp_notes
    from recommendations
    order by date desc, id desc
    limit ${limit}
  `;
}

export async function getCashEvents(): Promise<
  { date: string; event_type: string; amount: string; note: string | null }[]
> {
  return sql`
    select date, event_type, amount, note
    from cash_events
    order by date asc
  `;
}
