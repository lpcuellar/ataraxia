"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PerformancePoint } from "@/lib/metrics";

// Tokens de references/palette.md. Forma "emphasis" (references/choosing-a-form.md):
// Portafolio es el punto de la historia, S&P 500 es el contexto — acento vs. gris.
const ACCENT = "#2a78d6"; // --series-1
const CONTEXT = "#898781"; // --text-muted
const GRID = "#e1e0d9"; // --gridline

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs shadow-sm"
      style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
    >
      <p className="mb-1 font-medium" style={{ color: "var(--text-secondary)" }}>
        {label}
      </p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="inline-block h-0.5 w-3" style={{ background: p.color }} />
          <span className="font-semibold tabular-nums" style={{ color: "var(--text-primary)" }}>
            {p.value.toFixed(1)}
          </span>
          <span style={{ color: "var(--text-muted)" }}>{p.name}</span>
        </div>
      ))}
    </div>
  );
}

/** Portafolio y S&P 500 en UNA sola linea de tiempo, indexados a 100 en el primer
 * snapshot (decision de LP 2026-10-14: prefiere esto a dos graficos separados, aun
 * sabiendo que dos ejes de escala real -dolares vs. puntos de indice- hubiera sido el
 * anti-patron de doble eje). Indexar a una base comun es la forma correcta de poner dos
 * series de distinta unidad en un solo eje (references/anti-patterns.md, alternativa #1
 * al dual-axis) — ambas arrancan en 100 y se leen como "cuanto creció cada una desde
 * ahi", sin inventar una correlacion por la alineacion arbitraria de dos ejes. */
export default function IndexedPerformanceChart({ series }: { series: PerformancePoint[] }) {
  if (series.length < 2) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Hace falta más de un snapshot para graficar una serie. Con{" "}
        {series.length === 1 ? "1 punto" : "ningún punto"} todavía no hay nada que trazar.
      </p>
    );
  }

  const data = series.map((p) => ({
    asOf: p.asOf,
    Portafolio: Number((100 * (1 + p.cumulativeReturnPct)).toFixed(2)),
    "S&P 500": p.sp500ReturnPct !== null ? Number((100 * (1 + p.sp500ReturnPct)).toFixed(2)) : null,
  }));

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="0" stroke={GRID} vertical={false} />
          <XAxis
            dataKey="asOf"
            stroke={CONTEXT}
            tick={{ fill: CONTEXT, fontSize: 12 }}
            axisLine={{ stroke: GRID }}
            tickLine={false}
          />
          <YAxis
            stroke={CONTEXT}
            tick={{ fill: CONTEXT, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            domain={["auto", "auto"]}
            width={48}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "var(--text-secondary)" }}
            iconType="plainline"
          />
          <Line
            type="monotone"
            dataKey="Portafolio"
            stroke={ACCENT}
            strokeWidth={2}
            dot={{ r: 4, fill: ACCENT, stroke: "var(--surface-1)", strokeWidth: 2 }}
            activeDot={{ r: 5 }}
          />
          <Line
            type="monotone"
            dataKey="S&P 500"
            stroke={CONTEXT}
            strokeWidth={2}
            dot={{ r: 4, fill: CONTEXT, stroke: "var(--surface-1)", strokeWidth: 2 }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
