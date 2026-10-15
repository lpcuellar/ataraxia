import type { WatchlistRow } from "@/lib/db";
import TickerLogo from "@/components/TickerLogo";

function fmtUsd(n: string | null): string {
  if (n === null) return "—";
  return Number(n).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** Version compacta para Overview — solo lo que pidio LP (ticker, nombre, precio de
 * entrada). El detalle completo de tesis/foso/atacante sigue viviendo en /watchlist. */
export default function WatchlistSummaryTable({ entries }: { entries: WatchlistRow[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Sin candidatas en espera de precio.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr
            className="border-b text-left text-xs font-medium uppercase tracking-wide"
            style={{ borderColor: "var(--baseline)", color: "var(--text-muted)" }}
          >
            <th className="py-2 pr-3">Ticker</th>
            <th className="py-2 pr-3">Empresa</th>
            <th className="py-2 pr-3 text-right">Precio de entrada</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id} className="border-b last:border-0" style={{ borderColor: "var(--gridline)" }}>
              <td className="py-2.5 pr-3">
                <div className="flex items-center gap-2">
                  <TickerLogo ticker={e.ticker} size={22} />
                  <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                    {e.ticker}
                  </span>
                </div>
              </td>
              <td className="py-2.5 pr-3" style={{ color: "var(--text-secondary)" }}>
                {e.company_name ?? "—"}
              </td>
              <td className="py-2.5 pr-3 text-right tabular-nums" style={{ color: "var(--text-primary)" }}>
                {fmtUsd(e.price_at_entry)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
