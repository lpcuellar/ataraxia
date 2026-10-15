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
// Ataraxia es el punto de la historia, S&P 500 es el contexto — acento vs. gris, no dos
// colores categoricos compitiendo por atencion.
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
          {/* Line key, no box (references/interaction.md): un trazo corto, no un swatch. */}
          <span className="inline-block h-0.5 w-3" style={{ background: p.color }} />
          <span className="font-semibold tabular-nums" style={{ color: "var(--text-primary)" }}>
            {p.value >= 0 ? "+" : ""}
            {p.value}%
          </span>
          <span style={{ color: "var(--text-muted)" }}>{p.name}</span>
        </div>
      ))}
    </div>
  );
}

export default function PerformanceChart({ series }: { series: PerformancePoint[] }) {
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
    Ataraxia: Number((p.cumulativeReturnPct * 100).toFixed(2)),
    "S&P 500": p.sp500ReturnPct !== null ? Number((p.sp500ReturnPct * 100).toFixed(2)) : null,
  }));

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          {/* Hairline solida, un paso de la superficie — nunca punteada (anti-patterns.md). */}
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
            tickFormatter={(v) => `${v}%`}
            width={48}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "var(--text-secondary)" }}
            iconType="plainline"
          />
          <Line
            type="monotone"
            dataKey="Ataraxia"
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
