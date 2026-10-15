import { getLotsForSnapshot, getSnapshotHistory } from "@/lib/db";
import { buildPositions } from "@/lib/metrics";
import PositionsTable from "@/components/PositionsTable";
import Card from "@/components/Card";

export const instant = false;

export default async function PositionsPage() {
  const snapshots = await getSnapshotHistory();
  const latestSnapshot = [...snapshots].sort((a, b) => b.as_of.localeCompare(a.as_of))[0];
  const lots = latestSnapshot ? await getLotsForSnapshot(latestSnapshot.id) : [];
  const { positions } = buildPositions(lots);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Posiciones
        </h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          {latestSnapshot
            ? `Snapshot al ${latestSnapshot.as_of}`
            : "Sin snapshots cargados todavía"}
        </p>
      </header>

      <Card title="Posiciones">
        <PositionsTable positions={positions} />
      </Card>
    </div>
  );
}
