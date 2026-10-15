"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PositionRow } from "@/lib/metrics";

const COLORS = [
  "#34d399",
  "#60a5fa",
  "#f59e0b",
  "#f472b6",
  "#a78bfa",
  "#fb7185",
  "#22d3ee",
  "#a3e635",
  "#fbbf24",
  "#818cf8",
  "#4ade80",
  "#e879f9",
];

export default function DistributionChart({ positions }: { positions: PositionRow[] }) {
  const equities = positions
    .filter((p) => p.assetClass === "equity")
    .map((p) => ({ ticker: p.ticker, pct: Number((p.weightAtCost * 100).toFixed(1)) }));

  if (equities.length === 0) {
    return <p className="text-sm text-zinc-500">Sin acciones en el snapshot.</p>;
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={equities} layout="vertical" margin={{ left: 8, right: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
          <XAxis
            type="number"
            stroke="#71717a"
            fontSize={12}
            tickFormatter={(v) => `${v}%`}
          />
          <YAxis
            type="category"
            dataKey="ticker"
            stroke="#71717a"
            fontSize={12}
            width={56}
          />
          <Tooltip
            contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
            labelStyle={{ color: "#e4e4e7" }}
            formatter={(value) => `${value}%`}
          />
          <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
            {equities.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
