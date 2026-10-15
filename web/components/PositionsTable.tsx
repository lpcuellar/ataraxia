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
    <tr key={p.ticker} className="border-b border-zinc-800 last:border-0">
      <td className="py-2 pr-3 font-medium">{p.ticker}</td>
      <td className="py-2 pr-3 text-right">
        {showWeights ? fmtPct(p.weightAtCost) : <span className="text-zinc-600">n/a</span>}
        {showWeights && p.weightAtCost > MAX_POSITION_PCT && (
          <span className="ml-1 text-amber-400" title={`Excede el tope de ${fmtPct(MAX_POSITION_PCT)} al costo`}>
            ⚠
          </span>
        )}
      </td>
      <td className="py-2 pr-3 text-right">
        {showWeights ? fmtPct(p.weightAtMarket) : <span className="text-zinc-600">n/a</span>}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums">{p.quantity.toFixed(4)}</td>
      <td className="py-2 pr-3 text-right tabular-nums">${p.avgCost.toFixed(2)}</td>
      <td className="py-2 pr-3 text-right tabular-nums">
        {p.price !== null ? `$${p.price.toFixed(2)}` : "—"}
      </td>
      <td
        className={`py-2 pr-3 text-right tabular-nums ${
          p.gainPct >= 0 ? "text-emerald-400" : "text-red-400"
        }`}
      >
        {p.gainPct >= 0 ? "+" : ""}
        {(p.gainPct * 100).toFixed(1)}%
      </td>
      <td className="py-2 pr-3 text-right tabular-nums">{fmtUsd(p.marketValue)}</td>
      <td className="py-2">
        {p.needsThesisReview && (
          <span className="rounded bg-red-950 px-1.5 py-0.5 text-xs text-red-400">
            revisión obligatoria
          </span>
        )}
      </td>
    </tr>
  );

  const head = (
    <thead>
      <tr className="border-b border-zinc-700 text-left text-xs uppercase text-zinc-500">
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
        <p className="mb-2 text-xs text-zinc-500">
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
          <p className="mb-2 text-xs text-zinc-500">
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
