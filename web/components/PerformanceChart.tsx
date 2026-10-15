"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import type { PerformancePoint } from "@/lib/metrics";

// Referencia de LP (2026-10-14): app de trading con tema oscuro, numero grande arriba,
// dos lineas de color real (no acento-vs-gris) con el valor final pegado como pastilla
// en la punta de cada linea. Paleta categorica de references/palette.md: azul (slot 1,
// portafolio) y naranja (slot 2, S&P 500) — no gris, porque en la referencia las dos
// series son protagonistas, no una y su contexto.
const BLUE = "#3987e5"; // --series-1 dark
const ORANGE = "#d95926"; // --series-2 dark
const DARK_SURFACE = "#1a1a19";
const DARK_GRID = "#2c2c2a";
const DARK_TEXT_MUTED = "#898781";

function EndLabel({
  x,
  y,
  index,
  total,
  value,
  color,
}: {
  x?: string | number;
  y?: string | number;
  index?: number;
  total: number;
  // recharts tipa 'value' como RenderableText (incluye bool/ReactNode) porque label() se
  // reusa para cualquier mark — aca siempre es el numero de la serie, se coerciona.
  value?: unknown;
  color: string;
}) {
  const numX = typeof x === "number" ? x : Number(x);
  const numY = typeof y === "number" ? y : Number(y);
  const numValue = typeof value === "number" ? value : Number(value);
  if (
    index !== total - 1 ||
    !Number.isFinite(numX) ||
    !Number.isFinite(numY) ||
    !Number.isFinite(numValue)
  ) {
    return null;
  }
  const text = `${numValue >= 0 ? "+" : ""}${numValue.toFixed(2)}%`;
  const width = text.length * 6.5 + 16;
  return (
    <g>
      <rect x={numX + 10} y={numY - 11} width={width} height={22} rx={11} fill={color} />
      <text
        x={numX + 10 + width / 2}
        y={numY + 4}
        textAnchor="middle"
        fontSize={12}
        fontWeight={600}
        fill="#0b0b0b"
      >
        {text}
      </text>
    </g>
  );
}

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
      style={{ borderColor: "rgba(255,255,255,0.1)", background: DARK_SURFACE }}
    >
      <p className="mb-1 font-medium" style={{ color: DARK_TEXT_MUTED }}>
        {label}
      </p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <span className="inline-block h-0.5 w-3" style={{ background: p.color }} />
          <span className="font-semibold tabular-nums" style={{ color: "#ffffff" }}>
            {p.value >= 0 ? "+" : ""}
            {p.value.toFixed(2)}%
          </span>
          <span style={{ color: DARK_TEXT_MUTED }}>{p.name}</span>
        </div>
      ))}
    </div>
  );
}

function fmtUsd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** Portafolio y S&P 500, retorno % acumulado desde el primer snapshot, en una sola
 * linea de tiempo — estilo app de trading (referencia de LP, 2026-10-14): numero grande
 * de portafolio arriba, dos colores reales (no emphasis gris), valor final como pastilla
 * en la punta de cada linea en vez de leyenda aparte. Un solo eje de % en vez de dolares
 * vs. puntos de indice evita el anti-patron de doble eje (references/anti-patterns.md). */
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
    Portafolio: Number((p.cumulativeReturnPct * 100).toFixed(2)),
    "S&P 500": p.sp500ReturnPct !== null ? Number((p.sp500ReturnPct * 100).toFixed(2)) : null,
  }));

  const first = series[0];
  const latest = series[series.length - 1];
  const deltaUsd = latest.equityMarketValue - first.equityMarketValue;
  const deltaPct = latest.cumulativeReturnPct;

  return (
    <section
      className="rounded-xl border p-5"
      style={{ borderColor: "rgba(255,255,255,0.1)", background: DARK_SURFACE }}
    >
      <h2 className="mb-4 text-sm font-semibold" style={{ color: "#ffffff" }}>
        Portafolio vs. S&P 500
      </h2>
      {/* Pastillas de identidad: estaticas, no selectores — no hay otro activo ni otro
          corte de holdings para elegir todavia, asi que no se finge un control que no
          hace nada. */}
      <div className="mb-4 flex gap-2">
        <span
          className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
          style={{ background: "rgba(255,255,255,0.08)", color: "#ffffff" }}
        >
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: ORANGE }} />
          S&P 500
        </span>
        <span
          className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
          style={{ background: "rgba(255,255,255,0.08)", color: "#ffffff" }}
        >
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: BLUE }} />
          Portafolio
        </span>
      </div>

      <p className="text-3xl font-semibold" style={{ color: "#ffffff" }}>
        {fmtUsd(latest.equityMarketValue)}
      </p>
      <p className="mt-1 text-sm">
        <span style={{ color: deltaPct >= 0 ? "#34d399" : "#f87171" }}>
          {deltaPct >= 0 ? "+" : ""}
          {fmtUsd(deltaUsd)} ({deltaPct >= 0 ? "+" : ""}
          {(deltaPct * 100).toFixed(2)}%)
        </span>{" "}
        <span style={{ color: DARK_TEXT_MUTED }}>Desde {first.asOf}</span>
      </p>

      <div className="mt-6 h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 72, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="0" stroke={DARK_GRID} vertical={false} horizontal={false} />
            <XAxis
              dataKey="asOf"
              stroke={DARK_TEXT_MUTED}
              tick={{ fill: DARK_TEXT_MUTED, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="S&P 500"
              stroke={ORANGE}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5 }}
              connectNulls
              label={(props) => (
                <EndLabel {...props} total={data.length} color={ORANGE} />
              )}
            />
            <Line
              type="monotone"
              dataKey="Portafolio"
              stroke={BLUE}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5 }}
              label={(props) => (
                <EndLabel {...props} total={data.length} color={BLUE} />
              )}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
