import {
  getEquityAggregatesBySnapshot,
  getLotsForSnapshot,
  getRecommendations,
  getSnapshotHistory,
} from "@/lib/db";
import { buildPerformanceSeries, buildPositions, computeRiskMetrics } from "@/lib/metrics";
import MetricsCards from "@/components/MetricsCards";
import PerformanceChart from "@/components/PerformanceChart";
import PositionsTable from "@/components/PositionsTable";
import DistributionChart from "@/components/DistributionChart";
import RecommendationsTable from "@/components/RecommendationsTable";
import { logout } from "./login/actions";

// Con Cache Components (Next 16) una ruta con datos sin cachear tiene que optar
// explicitamente por renderizarse en el servidor en cada visita en vez de intentar un
// prerender estatico. Es exactamente lo que se quiere aca: un dashboard de portafolio
// siempre fresco, no un blog estatico.
export const instant = false;

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section
      className="rounded-xl border p-5"
      style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
    >
      <div className="mb-4">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          {title}
        </h2>
        {subtitle && (
          <p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>
            {subtitle}
          </p>
        )}
      </div>
      {children}
    </section>
  );
}

export default async function DashboardPage() {
  const [snapshots, equityAggregates, recommendations] = await Promise.all([
    getSnapshotHistory(),
    getEquityAggregatesBySnapshot(),
    getRecommendations(),
  ]);

  const latestSnapshot = [...snapshots].sort((a, b) => b.as_of.localeCompare(a.as_of))[0];
  const lots = latestSnapshot ? await getLotsForSnapshot(latestSnapshot.id) : [];

  const series = buildPerformanceSeries(snapshots, equityAggregates);
  const { positions } = buildPositions(lots);
  const risk = computeRiskMetrics(series);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-10">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            Ataraxia
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {latestSnapshot
              ? `Snapshot al ${latestSnapshot.as_of}`
              : "Sin snapshots cargados todavía"}
          </p>
        </div>
        <form action={logout}>
          <button
            className="rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors"
            style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
            type="submit"
          >
            Salir
          </button>
        </form>
      </header>

      <MetricsCards series={series} risk={risk} />

      <Card title="Retorno de equities vs. S&P 500">
        <PerformanceChart series={series} />
      </Card>

      <Card title="Distribución del portafolio" subtitle="Acciones, al costo">
        <DistributionChart positions={positions} />
      </Card>

      <Card title="Posiciones">
        <PositionsTable positions={positions} />
      </Card>

      <Card title="Bitácora de recomendaciones">
        <RecommendationsTable recommendations={recommendations} />
      </Card>
    </main>
  );
}
