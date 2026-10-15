"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PositionRow } from "@/lib/metrics";

// Color por compañia, extraido del logo de cada una (LP, 2026-10-15) — ver
// lib/logo-colors.ts para como se calcula y por que. Esto se aparta a proposito de la
// regla general del catalogo de la skill dataviz ("un ticker no tiene identidad
// categorica frente a otro, un solo color para todas las barras"): la regla existe para
// evitar el anti-patron de inventar una paleta sin orden ni validacion CVD sobre
// categorias nominales. Ac aca no se inventa nada — es el color de marca real de cada
// empresa — y la mitigacion de accesibilidad sigue intacta porque cada barra YA lleva el
// logo y el ticker como etiqueta directa (references/marks-and-anatomy.md): ningun
// lector depende de distinguir el color para saber que compañia es cada barra.
const DEFAULT_COLOR = "#3987e5"; // --series-1 dark — mismo fallback que lib/logo-colors.ts
const GRID = "#2c2c2a"; // --gridline dark
const MUTED = "#898781"; // --text-muted (mismo valor en los dos modos)

const ROW_HEIGHT = 32; // px por ticker — suficiente para el logo de 18px + aire
const MIN_HEIGHT = 200;

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: { ticker: string; pct: number; color: string } }[];
}) {
  if (!active || !payload?.length) return null;
  const { ticker, pct, color } = payload[0].payload;
  return (
    <div
      className="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs shadow-sm"
      style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
    >
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      <span className="font-semibold tabular-nums" style={{ color: "var(--text-primary)" }}>
        {pct}%
      </span>
      <span style={{ color: "var(--text-muted)" }}>{ticker}</span>
    </div>
  );
}

/** Tick del eje Y con el logo al lado del ticker — un <img> normal no entra en SVG, asi
 * que va dentro de un foreignObject. Si el logo no carga, el texto del ticker solo sigue
 * siendo suficiente identidad (no hay fallback a iniciales aca; seria redundante con el
 * texto que ya esta al lado). */
function TickerTick({ x = 0, y = 0, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const ticker = payload?.value ?? "";
  return (
    <foreignObject x={x - 56} y={y - 10} width={52} height={20}>
      <div className="flex items-center justify-end gap-1.5" style={{ width: 52 }}>
        <img
          src={`https://logos.stockanalysis.com/${ticker.toLowerCase()}.svg`}
          alt=""
          width={16}
          height={16}
          className="shrink-0 rounded-full"
          style={{ width: 16, height: 16, objectFit: "contain" }}
          onError={(e) => {
            (e.target as HTMLImageElement).style.visibility = "hidden";
          }}
        />
        <span className="truncate text-xs" style={{ color: MUTED }}>
          {ticker}
        </span>
      </div>
    </foreignObject>
  );
}

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
    }));

  if (equities.length === 0) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Sin acciones en el snapshot.
      </p>
    );
  }

  // La altura crece con la cantidad de tickers — con una altura fija, 12+ posiciones se
  // amontonaban y las etiquetas de abajo quedaban ilegibles/solapadas (lo que LP vio como
  // "no aparecen todos"). Con alto variable, cada fila tiene el mismo aire sin importar
  // cuantas posiciones haya.
  const height = Math.max(MIN_HEIGHT, equities.length * ROW_HEIGHT);

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={equities} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={4}>
          <CartesianGrid strokeDasharray="0" stroke={GRID} horizontal={false} />
          <XAxis
            type="number"
            stroke={MUTED}
            tick={{ fill: MUTED, fontSize: 12 }}
            axisLine={{ stroke: GRID }}
            tickLine={false}
            tickFormatter={(v) => `${v}%`}
          />
          <YAxis
            type="category"
            dataKey="ticker"
            stroke={MUTED}
            tick={<TickerTick />}
            axisLine={false}
            tickLine={false}
            width={72}
            interval={0}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "var(--page-plane)" }} />
          {/* <=24px de grosor y extremo redondeado de datos (references/marks-and-anatomy.md) */}
          <Bar dataKey="pct" radius={[0, 4, 4, 0]} maxBarSize={20}>
            {equities.map((e) => (
              <Cell key={e.ticker} fill={e.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
