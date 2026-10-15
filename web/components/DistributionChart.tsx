import type { PositionRow } from "@/lib/metrics";
import TickerLogo from "@/components/TickerLogo";
import { tickerName } from "@/lib/ticker-names";

// Color por compañia, extraido del logo de cada una (LP, 2026-10-15) — ver
// lib/logo-colors.ts para como se calcula y por que. Esto se aparta a proposito de la
// regla general del catalogo de la skill dataviz ("un ticker no tiene identidad
// categorica frente a otro, un solo color para todas las barras"): la regla existe para
// evitar el anti-patron de inventar una paleta sin orden ni validacion CVD sobre
// categorias nominales. Aca no se inventa nada — es el color de marca real de cada
// empresa — y la mitigacion de accesibilidad sigue intacta porque cada fila YA lleva el
// logo y el ticker como etiqueta directa (references/marks-and-anatomy.md): ningun
// lector depende de distinguir el color para saber que compañia es cada fila.
const DEFAULT_COLOR = "#3987e5"; // --series-1 dark — mismo fallback que lib/logo-colors.ts

/** Filas con barra de progreso horizontal (referencia de LP, 2026-10-15: un panel de
 * "top merchants" con logo + nombre + barra llena al % correspondiente) en vez de un
 * grafico de ejes. Es HTML/CSS plano, sin recharts — mas simple de construir para este
 * formato especifico, y de paso se puede verificar con curl sin depender de que un
 * navegador real hidrate un SVG (limitacion que arrastraba el BarChart anterior). */
export default function DistributionChart({
  positions,
  colors = {},
}: {
  positions: PositionRow[];
  /** ticker -> color hex, del color de marca extraido del logo (lib/logo-colors.ts).
   * Se calcula en el servidor (el CDN de logos no manda CORS, asi que no se puede leer
   * pixeles desde el navegador) y se pasa ya resuelto — un ticker sin entrada cae al
   * color por defecto, no a un error. */
  colors?: Record<string, string>;
}) {
  const equities = positions
    .filter((p) => p.assetClass === "equity")
    .map((p) => ({
      ticker: p.ticker,
      pct: Number((p.weightAtCost * 100).toFixed(1)),
      color: colors[p.ticker.toUpperCase()] ?? DEFAULT_COLOR,
    }))
    .sort((a, b) => b.pct - a.pct);

  if (equities.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Sin acciones en el snapshot.
      </p>
    );
  }

  const maxPct = Math.max(...equities.map((e) => e.pct));

  return (
    <div className="flex flex-col gap-4">
      {equities.map((e) => {
        const name = tickerName(e.ticker);
        // La barra crece relativa a la posicion mas grande, no al 100% del eje — asi la
        // de mayor peso siempre llena el ancho completo y las diferencias entre el resto
        // se notan, en vez de que todas queden chiquitas si la mayor es, digamos, 20%.
        const widthPct = maxPct ? (e.pct / maxPct) * 100 : 0;
        return (
          <div key={e.ticker} className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <TickerLogo ticker={e.ticker} size={28} />
              <div className="flex min-w-0 flex-col leading-tight">
                <span className="font-medium" style={{ color: "var(--text-primary)" }}>
                  {e.ticker}
                </span>
                {name && (
                  <span className="truncate text-xs" style={{ color: "var(--text-muted)" }}>
                    {name}
                  </span>
                )}
              </div>
              <span
                className="ml-auto text-sm font-semibold tabular-nums"
                style={{ color: "var(--text-primary)" }}
              >
                {e.pct}%
              </span>
            </div>
            <div
              className="h-2 w-full overflow-hidden rounded-full"
              style={{ background: "var(--surface-raised)" }}
            >
              <div
                className="h-full rounded-full"
                style={{ width: `${widthPct}%`, background: e.color }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
