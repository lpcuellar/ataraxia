import { getEquityAggregatesBySnapshot, getLotsForSnapshot, getSnapshotHistory } from "@/lib/db";
import { buildPerformanceSeries, buildPositions, computeRiskMetrics } from "@/lib/metrics";
import MetricsCards from "@/components/MetricsCards";
import PerformanceChart from "@/components/PerformanceChart";
import DistributionChart from "@/components/DistributionChart";
import Card from "@/components/Card";

// Con Cache Components (Next 16) una ruta con datos sin cachear tiene que optar
// explicitamente por renderizarse en el servidor en cada visita en vez de intentar un
// prerender estatico. Es exactamente lo que se quiere aca: un dashboard de portafolio
// siempre fresco, no un blog estatico.
export const instant = false;

export default async function OverviewPage() {
  const [snapshots, equityAggregates] = await Promise.all([
    getSnapshotHistory(),
    getEquityAggregatesBySnapshot(),
  ]);

  const latestSnapshot = [...snapshots].sort((a, b) => b.as_of.localeCompare(a.as_of))[0];
  const lots = latestSnapshot ? await getLotsForSnapshot(latestSnapshot.id) : [];

  const series = buildPerformanceSeries(snapshots, equityAggregates);
  const { positions } = buildPositions(lots);
  const risk = computeRiskMetrics(series);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Overview
        </h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {latestSnapshot
            ? `Snapshot al ${latestSnapshot.as_of}`
            : "Sin snapshots cargados todavía"}
        </p>
      </header>

      <MetricsCards series={series} risk={risk} />

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
        <Card title="Portafolio vs. S&P 500" subtitle="Retorno acumulado desde el primer snapshot">
          <PerformanceChart series={series} />
        </Card>
        <Card title="Distribución" subtitle="Acciones, al costo">
          <DistributionChart positions={positions} />
        </Card>
      </div>
    </div>
  );
}
