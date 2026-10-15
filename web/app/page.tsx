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
  const latestPoint = series[series.length - 1];

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-10 px-4 py-10">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Ataraxia</h1>
          <p className="text-sm text-zinc-500">
            {latestSnapshot
              ? `Snapshot al ${latestSnapshot.as_of}`
              : "Sin snapshots cargados todavía"}
          </p>
        </div>
        <form action={logout}>
          <button className="text-sm text-zinc-500 hover:text-zinc-300" type="submit">
            Salir
          </button>
        </form>
      </header>

      <section>
        <MetricsCards latest={latestPoint} risk={risk} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500">
          Retorno de equities vs. S&P 500
        </h2>
        <PerformanceChart series={series} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500">
          Distribución del portafolio (acciones, al costo)
        </h2>
        <DistributionChart positions={positions} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500">
          Posiciones
        </h2>
        <PositionsTable positions={positions} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500">
          Bitácora de recomendaciones
        </h2>
        <RecommendationsTable recommendations={recommendations} />
      </section>
    </main>
  );
}
