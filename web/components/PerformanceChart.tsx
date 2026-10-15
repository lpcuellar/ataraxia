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

export default function PerformanceChart({ series }: { series: PerformancePoint[] }) {
  if (series.length < 2) {
    return (
      <p className="text-sm text-zinc-500">
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
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="asOf" stroke="#71717a" fontSize={12} />
          <YAxis
            stroke="#71717a"
            fontSize={12}
            tickFormatter={(v) => `${v}%`}
            width={48}
          />
          <Tooltip
            contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
            labelStyle={{ color: "#e4e4e7" }}
            formatter={(value) => `${Number(value) >= 0 ? "+" : ""}${value}%`}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="Ataraxia"
            stroke="#34d399"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
          <Line
            type="monotone"
            dataKey="S&P 500"
            stroke="#a1a1aa"
            strokeWidth={2}
            strokeDasharray="4 4"
            dot={{ r: 3 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
