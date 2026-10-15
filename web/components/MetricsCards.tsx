import type { PerformancePoint, RiskMetrics } from "@/lib/metrics";

function fmtUsd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtPct(n: number | null): string {
  if (n === null) return "N/D";
  return `${n >= 0 ? "+" : ""}${(n * 100).toFixed(2)}%`;
}

function Card({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg" | "neutral";
  note?: string;
}) {
  const toneClass =
    tone === "pos" ? "text-emerald-400" : tone === "neg" ? "text-red-400" : "text-zinc-100";
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${toneClass}`}>{value}</p>
      {note && <p className="mt-1 text-xs text-zinc-500">{note}</p>}
    </div>
  );
}

export default function MetricsCards({
  latest,
  risk,
}: {
  latest: PerformancePoint | undefined;
  risk: RiskMetrics;
}) {
  if (!latest) {
    return <p className="text-zinc-500">Sin snapshots todavía.</p>;
  }

  const alpha = latest.relativeReturnPct;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      <Card label="Valor equities" value={fmtUsd(latest.equityMarketValue)} />
      <Card label="Costo equities" value={fmtUsd(latest.equityCostBasis)} />
      <Card
        label="Retorno equities"
        value={fmtPct(latest.cumulativeReturnPct)}
        tone={latest.cumulativeReturnPct >= 0 ? "pos" : "neg"}
        note="desde el primer snapshot"
      />
      <Card
        label="Alpha vs S&P 500"
        value={alpha === null ? "N/D" : fmtPct(alpha)}
        tone={alpha === null ? "neutral" : alpha >= 0 ? "pos" : "neg"}
        note="la métrica de la misión"
      />
      <Card
        label="Drawdown máximo"
        value={risk.maxDrawdownPct === null ? "N/D" : fmtPct(risk.maxDrawdownPct)}
        tone="neutral"
      />
      <Card
        label="Sharpe"
        value={risk.sharpeRatio === null ? "N/D" : risk.sharpeRatio.toFixed(2)}
        tone="neutral"
        note={
          risk.insufficientHistoryForSharpe
            ? "historial insuficiente — necesita más snapshots"
            : "tasa libre de riesgo 0%"
        }
      />
    </div>
  );
}
