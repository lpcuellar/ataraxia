import type { PerformancePoint, RiskMetrics } from "@/lib/metrics";

function fmtUsd(n: number): string {
  // Auto-compacto (ver references/marks-and-anatomy.md, anatomia de stat tile):
  // 1,284 / 12.9K / $4.2M, nunca un numero crudo de muchos digitos.
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 10_000) return `$${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtPct(n: number | null): string {
  if (n === null) return "N/D";
  return `${n >= 0 ? "+" : ""}${(n * 100).toFixed(2)}%`;
}

/** Sparkline de 12 puntos como mucho (references/marks-and-anatomy.md): la tendencia en
 * el tono de de-enfasis, salvo el ultimo tramo que lleva el acento. Sin ejes ni grilla —
 * es contexto al lado del numero, no un grafico que se lee por si solo. */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const recent = values.slice(-12);
  const min = Math.min(...recent);
  const max = Math.max(...recent);
  const span = max - min || 1;
  const w = 64;
  const h = 20;
  const step = w / (recent.length - 1);
  const points = recent.map((v, i) => [i * step, h - ((v - min) / span) * h] as const);
  const path = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const lastSegment = points.slice(-2);
  const lastPath = lastSegment
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0" aria-hidden>
      <path d={path} fill="none" stroke="var(--text-muted)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      <path d={lastPath} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Delta({ value, upIsGood = true }: { value: number; upIsGood?: boolean }) {
  const isUp = value >= 0;
  const good = isUp === upIsGood;
  return (
    <span
      className="text-xs font-medium"
      style={{ color: good ? "var(--status-good)" : "var(--status-critical)" }}
    >
      {isUp ? "↑" : "↓"} {fmtPct(Math.abs(value))}
    </span>
  );
}

function Tile({
  label,
  value,
  delta,
  sparkline,
  note,
}: {
  label: string;
  value: string;
  delta?: React.ReactNode;
  sparkline?: number[];
  note?: string;
}) {
  return (
    <div
      className="flex flex-col gap-2 rounded-xl border p-4"
      style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {label}
        </p>
        {sparkline && <Sparkline values={sparkline} />}
      </div>
      <div className="flex items-baseline gap-2">
        <p className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
          {value}
        </p>
        {delta}
      </div>
      {note && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          {note}
        </p>
      )}
    </div>
  );
}

export default function MetricsCards({
  series,
  risk,
}: {
  series: PerformancePoint[];
  risk: RiskMetrics;
}) {
  const latest = series[series.length - 1];
  const previous = series.length >= 2 ? series[series.length - 2] : undefined;

  if (!latest) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Sin snapshots todavía.
      </p>
    );
  }

  const valueDeltaPct = previous && previous.equityMarketValue
    ? (latest.equityMarketValue - previous.equityMarketValue) / previous.equityMarketValue
    : null;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
      <Tile
        label="Valor equities"
        value={fmtUsd(latest.equityMarketValue)}
        delta={valueDeltaPct !== null ? <Delta value={valueDeltaPct} /> : undefined}
        sparkline={series.map((p) => p.equityMarketValue)}
        note={previous ? "vs. snapshot anterior" : undefined}
      />
      <Tile label="Costo equities" value={fmtUsd(latest.equityCostBasis)} />
      <Tile
        label="Retorno equities"
        value={fmtPct(latest.cumulativeReturnPct)}
        note="desde el primer snapshot"
      />
      <Tile
        label="Alpha vs S&P 500"
        value={latest.relativeReturnPct === null ? "N/D" : fmtPct(latest.relativeReturnPct)}
        note="la métrica de la misión"
      />
      <Tile
        label="Drawdown máximo"
        value={risk.maxDrawdownPct === null ? "N/D" : fmtPct(risk.maxDrawdownPct)}
      />
      <Tile
        label="Sharpe"
        value={risk.sharpeRatio === null ? "N/D" : risk.sharpeRatio.toFixed(2)}
        note={
          risk.insufficientHistoryForSharpe
            ? "historial insuficiente — necesita más snapshots"
            : "tasa libre de riesgo 0%"
        }
      />
    </div>
  );
}
