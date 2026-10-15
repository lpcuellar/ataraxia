"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import type { PerformancePoint } from "@/lib/metrics";

// Referencia de LP (2026-10-14): app de trading con tema oscuro, numero grande arriba,
// dos lineas de color real (no acento-vs-gris) con el valor final pegado como pastilla
// en la punta de cada linea, y un selector de temporalidad (1D/5D/1M/6M/YTD/1Y/5Y/ALL).
// Paleta categorica de references/palette.md: azul (slot 1, portafolio) y naranja
// (slot 2, S&P 500) — no gris, porque en la referencia las dos series son protagonistas.
//
// Hex explicito (no var(--...)) porque son props de SVG de recharts, no estilos de DOM —
// coinciden a proposito con los tokens globales de globals.css ahora que todo el
// dashboard es oscuro (LP 2026-10-14). Si el tema cambia, actualizar ambos lugares.
const BLUE = "#3987e5"; // --series-1
const ORANGE = "#d95926"; // --series-2
const DARK_SURFACE = "#1a1a19"; // --surface-1
const DARK_GRID = "#2c2c2a"; // --gridline
const DARK_TEXT_MUTED = "#898781"; // --text-muted

const RANGES = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "ALL"] as const;
type Range = (typeof RANGES)[number];

/** Fecha de corte para un rango, relativa a HOY (no al ultimo snapshot): "1M" siempre
 * significa "el ultimo mes real", aunque el snapshot mas reciente tenga unos dias. */
function cutoffFor(range: Range): Date | null {
  const now = new Date();
  switch (range) {
    case "1D":
      return new Date(now.getTime() - 1 * 86400_000);
    case "5D":
      return new Date(now.getTime() - 5 * 86400_000);
    case "1M": {
      const d = new Date(now);
      d.setMonth(d.getMonth() - 1);
      return d;
    }
    case "6M": {
      const d = new Date(now);
      d.setMonth(d.getMonth() - 6);
      return d;
    }
    case "YTD":
      return new Date(now.getFullYear(), 0, 1);
    case "1Y": {
      const d = new Date(now);
      d.setFullYear(d.getFullYear() - 1);
      return d;
    }
    case "5Y": {
      const d = new Date(now);
      d.setFullYear(d.getFullYear() - 5);
      return d;
    }
    case "ALL":
      return null;
  }
}

/** Recalcula el retorno % de un sub-rango desde SU propio primer punto, no desde el
 * primer snapshot de toda la serie — si no, elegir "1M" seguiria mostrando el retorno
 * desde el inicio de los tiempos con una ventana de fechas mas chica, que es enganoso. */
function rebase(points: PerformancePoint[]): PerformancePoint[] {
  if (points.length === 0) return points;
  const base = points[0];
  const baseEquity = base.equityMarketValue;
  const baseSp500 = base.sp500Close;
  return points.map((p) => {
    const cumulativeReturnPct = baseEquity ? (p.equityMarketValue - baseEquity) / baseEquity : 0;
    const sp500ReturnPct =
      baseSp500 && p.sp500Close !== null ? (p.sp500Close - baseSp500) / baseSp500 : null;
    return {
      ...p,
      cumulativeReturnPct,
      sp500ReturnPct,
      relativeReturnPct: sp500ReturnPct !== null ? cumulativeReturnPct - sp500ReturnPct : null,
    };
  });
}

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

/** Portafolio y S&P 500, retorno % acumulado, con selector de temporalidad — estilo app
 * de trading (referencia de LP, 2026-10-14). Un solo eje de % (no dolares vs. puntos de
 * indice) evita el anti-patron de doble eje (references/anti-patterns.md). */
export default function PerformanceChart({ series }: { series: PerformancePoint[] }) {
  const [range, setRange] = useState<Range>("ALL");

  const filtered = useMemo(() => {
    const cutoff = cutoffFor(range);
    const inRange = cutoff ? series.filter((p) => new Date(p.asOf) >= cutoff) : series;
    return rebase(inRange);
  }, [series, range]);

  const rangeSelector = (
    <div className="mb-4 flex flex-wrap gap-1">
      {RANGES.map((r) => (
        <button
          key={r}
          onClick={() => setRange(r)}
          className="rounded-full px-2.5 py-1 text-xs font-medium transition-colors"
          style={{
            background: range === r ? BLUE : "rgba(255,255,255,0.08)",
            color: range === r ? "#ffffff" : DARK_TEXT_MUTED,
          }}
        >
          {r}
        </button>
      ))}
    </div>
  );

  if (series.length < 2) {
    return (
      <section
        className="rounded-xl border p-5"
        style={{ borderColor: "rgba(255,255,255,0.1)", background: DARK_SURFACE }}
      >
        <h2 className="mb-4 text-sm font-semibold" style={{ color: "#ffffff" }}>
          Portafolio vs. S&P 500
        </h2>
        <p className="text-sm" style={{ color: DARK_TEXT_MUTED }}>
          Hace falta más de un snapshot para graficar una serie. Con{" "}
          {series.length === 1 ? "1 punto" : "ningún punto"} todavía no hay nada que trazar.
        </p>
      </section>
    );
  }

  const data = filtered.map((p) => ({
    asOf: p.asOf,
    Portafolio: Number((p.cumulativeReturnPct * 100).toFixed(2)),
    "S&P 500": p.sp500ReturnPct !== null ? Number((p.sp500ReturnPct * 100).toFixed(2)) : null,
  }));

  const first = filtered[0];
  const latest = filtered[filtered.length - 1];
  const hasEnoughData = filtered.length >= 2;
  const deltaUsd = hasEnoughData ? latest.equityMarketValue - first.equityMarketValue : 0;
  const deltaPct = hasEnoughData ? latest.cumulativeReturnPct : 0;

  return (
    <section
      className="rounded-xl border p-5"
      style={{ borderColor: "rgba(255,255,255,0.1)", background: DARK_SURFACE }}
    >
      <h2 className="mb-4 text-sm font-semibold" style={{ color: "#ffffff" }}>
        Portafolio vs. S&P 500
      </h2>
      {/* Pastillas de identidad: estaticas, no selectores de activo — no hay otro activo
          ni otro corte de holdings para elegir todavia, asi que no se finge un control
          que no hace nada. El selector de rango SI es funcional (filtra y rebasea). */}
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
      {hasEnoughData ? (
        <p className="mt-1 text-sm">
          <span style={{ color: deltaPct >= 0 ? "#34d399" : "#f87171" }}>
            {deltaPct >= 0 ? "+" : ""}
            {fmtUsd(deltaUsd)} ({deltaPct >= 0 ? "+" : ""}
            {(deltaPct * 100).toFixed(2)}%)
          </span>{" "}
          <span style={{ color: DARK_TEXT_MUTED }}>Desde {first.asOf}</span>
        </p>
      ) : (
        <p className="mt-1 text-sm" style={{ color: DARK_TEXT_MUTED }}>
          Solo hay un snapshot en este rango — no hay con qué comparar todavía.
        </p>
      )}

      <div className="mt-6">{rangeSelector}</div>

      {hasEnoughData ? (
        <div className="h-64 w-full">
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
                label={(props) => <EndLabel {...props} total={data.length} color={ORANGE} />}
              />
              <Line
                type="monotone"
                dataKey="Portafolio"
                stroke={BLUE}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 5 }}
                label={(props) => <EndLabel {...props} total={data.length} color={BLUE} />}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="text-sm" style={{ color: DARK_TEXT_MUTED }}>
          No hay suficientes snapshots en este rango todavía — probá con uno más amplio.
        </p>
      )}
    </section>
  );
}
