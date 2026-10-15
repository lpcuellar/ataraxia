import "server-only";
import type { LotRow, PortfolioSnapshotRow } from "./db";

type EquityAggregateRow = {
  snapshot_id: number;
  asset_class: string;
  cost_basis: string;
  market_value: string;
};

// Minimo de puntos para que un Sharpe signifique algo. Mismo umbral y misma razon que
// src/reporting/performance.py (MIN_POINTS_FOR_SHARPE): con pocos snapshots el desvio
// estandar de retornos es ruido, no senal, y un numero asi es peor que no mostrar nada.
const MIN_POINTS_FOR_SHARPE = 5;

export type PerformancePoint = {
  asOf: string;
  equityMarketValue: number;
  equityCostBasis: number;
  cumulativeReturnPct: number; // retorno acumulado de las equities desde el primer snapshot
  sp500ReturnPct: number | null; // retorno acumulado del S&P 500 en la misma ventana
  relativeReturnPct: number | null; // alpha: equities - S&P 500
};

/** Agregados de costo/valor de equities (sin ETFs) por snapshot, a partir de las filas ya
 * sumadas por SQL (ver db.getEquityAggregatesBySnapshot — una sola consulta agregada en vez
 * de traer cada lote individual, que crece sin limite semana a semana). */
function equityAggregatesBySnapshot(
  rows: EquityAggregateRow[]
): Map<number, { cost: number; value: number }> {
  const out = new Map<number, { cost: number; value: number }>();
  for (const row of rows) {
    if (row.asset_class !== "equity") continue;
    out.set(row.snapshot_id, { cost: Number(row.cost_basis), value: Number(row.market_value) });
  }
  return out;
}

/** Serie de performance equities-only vs S&P 500. Decision de LP (2026-10-11): el alpha de
 * Ataraxia se mide SOLO sobre equities, nunca sobre el total de la cuenta — los ETFs
 * (VOO/SCHD/VXUS) son ancla pasiva fuera del mandato y VOO *es* el benchmark, asi que
 * mezclarlos arrastraria la medicion hacia el indice y esconderia el aporte real. */
export function buildPerformanceSeries(
  snapshots: PortfolioSnapshotRow[],
  equityAggregateRows: EquityAggregateRow[]
): PerformancePoint[] {
  const aggregates = equityAggregatesBySnapshot(equityAggregateRows);
  const ordered = [...snapshots].sort((a, b) => a.as_of.localeCompare(b.as_of));

  const base = ordered[0];
  const baseAgg = base ? aggregates.get(base.id) : undefined;
  const baseValue = baseAgg?.value ?? 0;
  const baseSp500 = base?.sp500_close ? Number(base.sp500_close) : null;

  return ordered.map((snap) => {
    const agg = aggregates.get(snap.id) ?? { cost: 0, value: 0 };
    const cumulativeReturnPct = baseValue ? (agg.value - baseValue) / baseValue : 0;

    let sp500ReturnPct: number | null = null;
    if (baseSp500 && snap.sp500_close) {
      sp500ReturnPct = (Number(snap.sp500_close) - baseSp500) / baseSp500;
    }

    return {
      asOf: snap.as_of,
      equityMarketValue: agg.value,
      equityCostBasis: agg.cost,
      cumulativeReturnPct,
      sp500ReturnPct,
      relativeReturnPct:
        sp500ReturnPct !== null ? cumulativeReturnPct - sp500ReturnPct : null,
    };
  });
}

export type PositionRow = {
  ticker: string;
  assetClass: string;
  quantity: number;
  avgCost: number;
  price: number | null;
  costBasis: number;
  marketValue: number;
  gainPct: number;
  weightAtCost: number; // sobre equity_cost_basis (sin ETFs ni cash) — 0 para ETFs
  weightAtMarket: number; // sobre equity_market_value — 0 para ETFs, informativo (LP 2026-10-14)
  needsThesisReview: boolean; // -20% o peor, mismo trigger que src/guardrails/validator.py
};

const MAX_POSITION_PCT = 0.25; // src/guardrails/validator.py MAX_POSITION_PCT — mismo numero,
// duplicado aca porque el dashboard es TypeScript y el validator es Python; si uno cambia,
// cambiar el otro.

/** Posiciones de un snapshot, agregadas por ticker (un ticker puede tener varios lotes de
 * distintas fechas de compra). El peso al costo/mercado usa SOLO equities en el denominador
 * (ver buildPerformanceSeries) — igual que src.guardrails.validator.PortfolioState.equity_cost_basis
 * y src.data.portfolio_csv.PortfolioSnapshot.weight_at_market. */
export function buildPositions(lots: LotRow[]): {
  positions: PositionRow[];
  equityCostBasis: number;
  equityMarketValue: number;
} {
  const byTicker = new Map<
    string,
    { assetClass: string; quantity: number; costBasis: number; marketValue: number }
  >();

  for (const l of lots) {
    const existing = byTicker.get(l.ticker) ?? {
      assetClass: l.asset_class,
      quantity: 0,
      costBasis: 0,
      marketValue: 0,
    };
    existing.quantity += Number(l.quantity);
    existing.costBasis += Number(l.cost_basis);
    existing.marketValue += Number(l.market_value ?? 0);
    byTicker.set(l.ticker, existing);
  }

  let equityCostBasis = 0;
  let equityMarketValue = 0;
  for (const p of byTicker.values()) {
    if (p.assetClass !== "equity") continue;
    equityCostBasis += p.costBasis;
    equityMarketValue += p.marketValue;
  }

  const positions: PositionRow[] = [...byTicker.entries()].map(([ticker, p]) => {
    const isEquity = p.assetClass === "equity";
    const avgCost = p.quantity ? p.costBasis / p.quantity : 0;
    const price = p.quantity ? p.marketValue / p.quantity : null;
    const gainPct = p.costBasis ? (p.marketValue - p.costBasis) / p.costBasis : 0;
    return {
      ticker,
      assetClass: p.assetClass,
      quantity: p.quantity,
      avgCost,
      price,
      costBasis: p.costBasis,
      marketValue: p.marketValue,
      gainPct,
      weightAtCost: isEquity && equityCostBasis ? p.costBasis / equityCostBasis : 0,
      weightAtMarket: isEquity && equityMarketValue ? p.marketValue / equityMarketValue : 0,
      needsThesisReview: gainPct <= -0.2,
    };
  });

  positions.sort((a, b) => b.costBasis - a.costBasis);
  return { positions, equityCostBasis, equityMarketValue };
}

export type RiskMetrics = {
  maxDrawdownPct: number | null;
  sharpeRatio: number | null;
  insufficientHistoryForSharpe: boolean;
};

/** Drawdown maximo y Sharpe sobre la serie de valor de mercado de equities. Sharpe asume
 * tasa libre de riesgo 0% — igual simplificacion que src/reporting/performance.py, aceptable
 * mientras el historico sea corto pero NO para juzgar la estrategia contra bonos a largo
 * plazo. Revisar cuando haya suficiente historico para que la comparacion importe. */
export function computeRiskMetrics(series: PerformancePoint[]): RiskMetrics {
  if (series.length < 2) {
    return { maxDrawdownPct: null, sharpeRatio: null, insufficientHistoryForSharpe: true };
  }

  let peak = series[0].equityMarketValue;
  let maxDrawdown = 0;
  for (const point of series) {
    if (point.equityMarketValue > peak) peak = point.equityMarketValue;
    const drawdown = peak ? (point.equityMarketValue - peak) / peak : 0;
    if (drawdown < maxDrawdown) maxDrawdown = drawdown;
  }

  if (series.length < MIN_POINTS_FOR_SHARPE) {
    return { maxDrawdownPct: maxDrawdown, sharpeRatio: null, insufficientHistoryForSharpe: true };
  }

  const returns: number[] = [];
  for (let i = 1; i < series.length; i++) {
    const prev = series[i - 1].equityMarketValue;
    if (!prev) continue;
    returns.push((series[i].equityMarketValue - prev) / prev);
  }
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance =
    returns.reduce((a, r) => a + (r - mean) ** 2, 0) / Math.max(1, returns.length - 1);
  const stdDev = Math.sqrt(variance);
  const sharpe = stdDev ? mean / stdDev : null;

  return { maxDrawdownPct: maxDrawdown, sharpeRatio: sharpe, insufficientHistoryForSharpe: false };
}
