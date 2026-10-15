import type { WatchlistRow } from "@/lib/db";

const MOAT_LABEL: Record<string, string> = {
  marca: "marca",
  efecto_red: "efecto red",
  costos_cambio: "costos de cambio",
  ventaja_costo: "ventaja de costo",
  escala: "escala",
};

const DIRECTION_STYLE: Record<string, { bg: string; fg: string }> = {
  ensanchando: { bg: "rgba(12, 163, 12, 0.15)", fg: "var(--status-good)" },
  estable: { bg: "var(--surface-raised)", fg: "var(--text-secondary)" },
  erosionando: { bg: "rgba(208, 59, 59, 0.15)", fg: "var(--status-critical)" },
};

function fmtUsd(n: string | null): string | null {
  if (n === null) return null;
  return Number(n).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export default function WatchlistTable({ entries }: { entries: WatchlistRow[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Sin candidatas en espera de precio.
      </p>
    );
  }

  return (
    <div className="flex flex-col divide-y" style={{ borderColor: "var(--gridline)" }}>
      {entries.map((e) => {
        const direction = e.moat_direction ? DIRECTION_STYLE[e.moat_direction] : null;
        return (
          <div key={e.id} className="py-4" style={{ borderColor: "var(--gridline)" }}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                {e.ticker}
              </span>
              {e.company_name && (
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {e.company_name}
                </span>
              )}
              {e.moat_type && (
                <span
                  className="rounded-md px-1.5 py-0.5 text-xs font-medium"
                  style={{ background: "var(--surface-raised)", color: "var(--text-secondary)" }}
                >
                  {MOAT_LABEL[e.moat_type] ?? e.moat_type}
                </span>
              )}
              {direction && (
                <span
                  className="rounded-md px-1.5 py-0.5 text-xs font-medium"
                  style={{ background: direction.bg, color: direction.fg }}
                >
                  foso {e.moat_direction}
                </span>
              )}
              <span className="ml-auto flex items-baseline gap-3 text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
                {e.price_at_entry && <span>entró a {fmtUsd(e.price_at_entry)}</span>}
                {e.target_price && (
                  <span className="font-semibold" style={{ color: "var(--series-1)" }}>
                    objetivo {fmtUsd(e.target_price)}
                  </span>
                )}
              </span>
            </div>

            <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
              {e.thesis_summary}
            </p>

            <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
              <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
                Gatilla la compra:
              </span>{" "}
              {e.what_needs_to_happen}
            </p>

            {e.moat_evidence && (
              <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
                <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
                  Evidencia del foso:
                </span>{" "}
                {e.moat_evidence}
              </p>
            )}

            {e.attacker_case && (
              <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
                <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
                  Caso del atacante
                  {e.attacker_probability ? ` (${(Number(e.attacker_probability) * 100).toFixed(0)}%)` : ""}:
                </span>{" "}
                {e.attacker_case}
              </p>
            )}

            <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
              Entró {e.added_at}
              {e.last_reviewed_at && e.last_reviewed_at !== e.added_at
                ? ` · última revisión ${e.last_reviewed_at}`
                : ""}
            </p>
          </div>
        );
      })}
    </div>
  );
}
