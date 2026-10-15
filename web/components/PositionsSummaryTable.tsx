import type { PositionRow } from "@/lib/metrics";
import TickerLogo from "@/components/TickerLogo";
import { tickerName } from "@/lib/ticker-names";

function fmtUsd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** Resumen compacto para Overview — acciones y ETFs juntos, logo + nombre + valor +
 * ganancia + peso. El peso aca es sobre el VALOR TOTAL de la cuenta (equities + ETFs),
 * no el peso equity-only del tope de concentracion que usa /positions — son preguntas
 * distintas: "cuanto pesa esto en el tope de 25%" vs. "cuanto es esto de mi plata". */
export default function PositionsSummaryTable({ positions }: { positions: PositionRow[] }) {
  if (positions.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Sin posiciones en el snapshot.
      </p>
    );
  }

  const totalValue = positions.reduce((sum, p) => sum + p.marketValue, 0);
  const sorted = [...positions].sort((a, b) => b.marketValue - a.marketValue);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr
            className="border-b text-left text-xs font-medium uppercase tracking-wide"
            style={{ borderColor: "var(--baseline)", color: "var(--text-muted)" }}
          >
            <th className="py-2 pr-3">Posición</th>
            <th className="py-2 pr-3 text-right">Valor</th>
            <th className="py-2 pr-3 text-right">Ganancia</th>
            <th className="py-2 pr-3 text-right">Peso</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => {
            const name = tickerName(p.ticker);
            const weight = totalValue ? p.marketValue / totalValue : 0;
            return (
              <tr key={p.ticker} className="border-b last:border-0" style={{ borderColor: "var(--gridline)" }}>
                <td className="py-2.5 pr-3">
                  <div className="flex items-center gap-2">
                    <TickerLogo ticker={p.ticker} size={22} />
                    <div className="flex flex-col leading-tight">
                      <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                        {p.ticker}
                      </span>
                      {name && (
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                          {name}
                        </span>
                      )}
                    </div>
                  </div>
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-primary)" }}>
                  {fmtUsd(p.marketValue)}
                </td>
                <td
                  className="py-2.5 pr-3 text-right tabular-nums font-medium"
                  style={{ color: p.gainPct >= 0 ? "var(--success-text)" : "var(--status-critical)" }}
                >
                  {p.gainPct >= 0 ? "+" : ""}
                  {(p.gainPct * 100).toFixed(1)}%
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-secondary)" }}>
                  {(weight * 100).toFixed(1)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
