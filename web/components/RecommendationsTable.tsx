import type { RecommendationRow } from "@/lib/db";

// Convencion de dominio (compra=verde, vender=rojo) sobre los tokens de status fijos de
// references/palette.md — no una paleta categorica nueva por veredicto. mantener/
// esperar_precio quedan neutros porque no son ni una señal de entrada ni de salida.
const VERDICT_STYLE: Record<string, { bg: string; fg: string }> = {
  compra: { bg: "#e3f6e3", fg: "var(--status-good)" },
  agregar_watchlist: { bg: "#e5eefb", fg: "var(--series-1)" },
  mantener: { bg: "#f1f0ec", fg: "var(--text-secondary)" },
  esperar_precio: { bg: "#f1f0ec", fg: "var(--text-secondary)" },
  vender: { bg: "#fce8e4", fg: "var(--status-critical)" },
  recortar: { bg: "#fdf0e0", fg: "var(--status-serious)" },
  descartar: { bg: "#f1f0ec", fg: "var(--text-muted)" },
};

function VerdictBadge({ verdict }: { verdict: string }) {
  const style = VERDICT_STYLE[verdict] ?? { bg: "#f1f0ec", fg: "var(--text-secondary)" };
  return (
    <span
      className="whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-medium"
      style={{ background: style.bg, color: style.fg }}
    >
      {verdict.replace("_", " ")}
    </span>
  );
}

function ActionBadge({ action }: { action: string | null }) {
  if (!action) return null;
  const color =
    action === "ejecutada"
      ? "var(--status-good)"
      : action === "rechazada"
      ? "var(--status-critical)"
      : "var(--text-muted)";
  return (
    <span className="text-xs font-medium" style={{ color }}>
      LP: {action}
    </span>
  );
}

export default function RecommendationsTable({
  recommendations,
}: {
  recommendations: RecommendationRow[];
}) {
  if (recommendations.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Sin recomendaciones todavía.
      </p>
    );
  }

  return (
    <div className="flex flex-col divide-y" style={{ borderColor: "var(--gridline)" }}>
      {recommendations.map((r) => (
        <div key={r.id} className="py-3" style={{ borderColor: "var(--gridline)" }}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
              {r.date}
            </span>
            <span className="font-medium" style={{ color: "var(--text-primary)" }}>
              {r.ticker}
            </span>
            <VerdictBadge verdict={r.verdict} />
            {r.price_at_recommendation && (
              <span className="text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
                ${Number(r.price_at_recommendation).toFixed(2)}
              </span>
            )}
            {r.target_price && (
              <span className="text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
                objetivo ${Number(r.target_price).toFixed(2)}
              </span>
            )}
            <span className="ml-auto">
              <ActionBadge action={r.lp_action} />
            </span>
          </div>
          <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
            {r.rationale}
          </p>
          {r.bear_case && (
            <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
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
