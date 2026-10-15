import type { PositionRow } from "@/lib/metrics";

const MAX_POSITION_PCT = 0.25;

function fmtUsd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

export default function PositionsTable({ positions }: { positions: PositionRow[] }) {
  const equities = positions.filter((p) => p.assetClass === "equity");
  const etfs = positions.filter((p) => p.assetClass !== "equity");

  const row = (p: PositionRow, showWeights: boolean) => (
    <tr key={p.ticker} className="border-b last:border-0" style={{ borderColor: "var(--gridline)" }}>
      <td className="py-2.5 pr-3 font-medium" style={{ color: "var(--text-primary)" }}>
        {p.ticker}
      </td>
      <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-primary)" }}>
        {showWeights ? (
          <>
            {fmtPct(p.weightAtCost)}
            {p.weightAtCost > MAX_POSITION_PCT && (
              <span
                className="ml-1"
                style={{ color: "var(--status-warning)" }}
                title={`Excede el tope de ${fmtPct(MAX_POSITION_PCT)} al costo`}
              >
                ⚠
              </span>
            )}
          </>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>n/a</span>
        )}
      </td>
      <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-secondary)" }}>
        {showWeights ? fmtPct(p.weightAtMarket) : <span style={{ color: "var(--text-muted)" }}>n/a</span>}
      </td>
      <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-secondary)" }}>
        {p.quantity.toFixed(4)}
      </td>
      <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-secondary)" }}>
        ${p.avgCost.toFixed(2)}
      </td>
      <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-primary)" }}>
        {p.price !== null ? `$${p.price.toFixed(2)}` : "—"}
      </td>
      <td
        className="py-2.5 pr-3 text-right tabular-nums font-medium"
        style={{ color: p.gainPct >= 0 ? "var(--success-text)" : "var(--status-critical)" }}
      >
        {p.gainPct >= 0 ? "+" : ""}
        {(p.gainPct * 100).toFixed(1)}%
      </td>
      <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-primary)" }}>
        {fmtUsd(p.marketValue)}
      </td>
      <td className="py-2.5">
        {p.needsThesisReview && (
          <span
            className="rounded-md px-1.5 py-0.5 text-xs font-medium"
            style={{ background: "rgba(208, 59, 59, 0.15)", color: "var(--status-critical)" }}
          >
            revisión obligatoria
          </span>
        )}
      </td>
    </tr>
  );

  const head = (
    <thead>
      <tr
        className="border-b text-left text-xs font-medium uppercase tracking-wide"
        style={{ borderColor: "var(--baseline)", color: "var(--text-muted)" }}
      >
        <th className="py-2 pr-3">Ticker</th>
        <th className="py-2 pr-3 text-right">% costo</th>
        <th className="py-2 pr-3 text-right">% mercado</th>
        <th className="py-2 pr-3 text-right">Cantidad</th>
        <th className="py-2 pr-3 text-right">Costo prom.</th>
        <th className="py-2 pr-3 text-right">Precio</th>
        <th className="py-2 pr-3 text-right">P&L</th>
        <th className="py-2 pr-3 text-right">Valor</th>
        <th className="py-2"></th>
      </tr>
    </thead>
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="overflow-x-auto">
        <p className="mb-2 text-xs" style={{ color: "var(--text-muted)" }}>
          Acciones — % costo es el peso sobre el tope de concentración ({fmtPct(MAX_POSITION_PCT)});
          % mercado es informativo, no bloquea nada.
        </p>
        <table className="w-full text-sm">
          {head}
          <tbody>{equities.map((p) => row(p, true))}</tbody>
        </table>
      </div>
      {etfs.length > 0 && (
        <div className="overflow-x-auto">
          <p className="mb-2 text-xs" style={{ color: "var(--text-muted)" }}>
            ETFs — ancla pasiva fuera del mandato, no cuentan para el tope de concentración.
          </p>
          <table className="w-full text-sm">
            {head}
            <tbody>{etfs.map((p) => row(p, false))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
