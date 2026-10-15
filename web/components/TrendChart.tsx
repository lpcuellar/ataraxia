"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const ACCENT = "#2a78d6"; // --series-1
const CONTEXT = "#898781"; // --text-muted
const GRID = "#e1e0d9"; // --gridline

type Variant = "usd" | "index";

// Los formateadores viven aca, no como prop function desde el server component que
// renderiza <TrendChart> — las funciones no pueden cruzar el limite RSC hacia un client
// component (TypeError: "Functions cannot be passed directly to Client Components").
const FORMATTERS: Record<Variant, { value: (v: number) => string; axis: (v: number) => string }> = {
  usd: {
    value: (v) => v.toLocaleString("en-US", { style: "currency", currency: "USD" }),
    axis: (v) => (v >= 1000 ? `$${(v / 1000).toFixed(0)}K` : `$${v}`),
  },
  index: {
    value: (v) => v.toLocaleString("en-US", { maximumFractionDigits: 2 }),
    axis: (v) => v.toLocaleString("en-US", { maximumFractionDigits: 0 }),
  },
};

function CustomTooltip({
  active,
  payload,
  label,
  formatValue,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
  formatValue: (v: number) => string;
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
      <span className="font-semibold tabular-nums" style={{ color: "var(--text-primary)" }}>
        {formatValue(payload[0].value)}
      </span>
    </div>
  );
}

/** Un solo trazo (references/choosing-a-form.md: "trend over time" -> line, 1 hue). Sin
 * leyenda a proposito: un solo color no necesita caja — el titulo de la card ya dice
 * que es. Pensado para small multiples: dos TrendChart lado a lado en vez de forzar dos
 * series de escala distinta (dolares de portafolio vs. puntos de indice) en un mismo eje,
 * que seria el anti-patron de doble eje (references/anti-patterns.md, #1 del catalogo). */
export default function TrendChart({
  data,
  valueLabel,
  variant,
}: {
  data: { asOf: string; value: number | null }[];
  valueLabel: string;
  variant: Variant;
}) {
  const { value: formatValue, axis: formatAxis } = FORMATTERS[variant];
  const points = data.filter((d) => d.value !== null) as { asOf: string; value: number }[];

  if (points.length < 2) {
    return (
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        Hace falta más de un snapshot para graficar una serie.
      </p>
    );
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
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
            tickFormatter={formatAxis}
            width={56}
            domain={["auto", "auto"]}
          />
          <Tooltip content={<CustomTooltip formatValue={formatValue} />} />
          <Line
            type="monotone"
            dataKey="value"
            name={valueLabel}
            stroke={ACCENT}
            strokeWidth={2}
            dot={{ r: 4, fill: ACCENT, stroke: "var(--surface-1)", strokeWidth: 2 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
