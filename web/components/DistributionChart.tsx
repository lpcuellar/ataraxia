"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PositionRow } from "@/lib/metrics";

// Un ticker no tiene mas "identidad categorica" frente a otro que lo justifique: son
// categorias nominales sin orden natural, asi que un color por barra (uno de 12 del
// catalogo) seria el anti-patron "value-ramp sobre categorias nominales"
// (references/anti-patterns.md) — double-encodea el largo de la barra como color sin
// agregar informacion. Un solo color (slot 1) para todas las barras es lo correcto.
const BAR_COLOR = "#3987e5"; // --series-1 dark
const GRID = "#2c2c2a"; // --gridline dark
const MUTED = "#898781"; // --text-muted (mismo valor en los dos modos)

const ROW_HEIGHT = 32; // px por ticker — suficiente para el logo de 18px + aire
const MIN_HEIGHT = 200;

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: { ticker: string; pct: number } }[];
}) {
  if (!active || !payload?.length) return null;
  const { ticker, pct } = payload[0].payload;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs shadow-sm"
      style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
    >
      <span className="font-semibold tabular-nums" style={{ color: "var(--text-primary)" }}>
        {pct}%
      </span>{" "}
      <span style={{ color: "var(--text-muted)" }}>{ticker}</span>
    </div>
  );
}

/** Tick del eje Y con el logo al lado del ticker — un <img> normal no entra en SVG, asi
 * que va dentro de un foreignObject. El fallback a iniciales esta en TickerLogo.tsx. */
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

export default function DistributionChart({ positions }: { positions: PositionRow[] }) {
  const equities = positions
    .filter((p) => p.assetClass === "equity")
    .map((p) => ({ ticker: p.ticker, pct: Number((p.weightAtCost * 100).toFixed(1)) }));

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
          <Bar dataKey="pct" fill={BAR_COLOR} radius={[0, 4, 4, 0]} maxBarSize={20} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
