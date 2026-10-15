import type { RecommendationRow } from "@/lib/db";

const VERDICT_STYLE: Record<string, string> = {
  compra: "bg-emerald-950 text-emerald-400",
  agregar_watchlist: "bg-blue-950 text-blue-400",
  mantener: "bg-zinc-800 text-zinc-300",
  esperar_precio: "bg-zinc-800 text-zinc-300",
  vender: "bg-red-950 text-red-400",
  recortar: "bg-amber-950 text-amber-400",
  descartar: "bg-zinc-800 text-zinc-500",
};

function VerdictBadge({ verdict }: { verdict: string }) {
  const cls = VERDICT_STYLE[verdict] ?? "bg-zinc-800 text-zinc-300";
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${cls}`}>
      {verdict.replace("_", " ")}
    </span>
  );
}

function ActionBadge({ action }: { action: string | null }) {
  if (!action) return null;
  const cls =
    action === "ejecutada"
      ? "text-emerald-400"
      : action === "rechazada"
      ? "text-red-400"
      : "text-zinc-500";
  return <span className={`text-xs ${cls}`}>LP: {action}</span>;
}

export default function RecommendationsTable({
  recommendations,
}: {
  recommendations: RecommendationRow[];
}) {
  if (recommendations.length === 0) {
    return <p className="text-sm text-zinc-500">Sin recomendaciones todavía.</p>;
  }

  return (
    <div className="flex flex-col divide-y divide-zinc-800">
      {recommendations.map((r) => (
        <div key={r.id} className="py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-zinc-500">{r.date}</span>
            <span className="font-medium">{r.ticker}</span>
            <VerdictBadge verdict={r.verdict} />
            {r.price_at_recommendation && (
              <span className="text-xs text-zinc-500">
                ${Number(r.price_at_recommendation).toFixed(2)}
              </span>
            )}
            {r.target_price && (
              <span className="text-xs text-zinc-500">
                objetivo ${Number(r.target_price).toFixed(2)}
              </span>
            )}
            <span className="ml-auto">
              <ActionBadge action={r.lp_action} />
            </span>
          </div>
          <p className="mt-1 text-sm text-zinc-400">{r.rationale}</p>
          {r.bear_case && (
            <p className="mt-1 text-xs text-zinc-500">
              Bear case
              {r.bear_case_probability
                ? ` (${(Number(r.bear_case_probability) * 100).toFixed(0)}%)`
                : ""}
              : {r.bear_case}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
