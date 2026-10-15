import { getWatchlist } from "@/lib/db";
import WatchlistTable from "@/components/WatchlistTable";
import Card from "@/components/Card";

export const instant = false;

export default async function WatchlistPage() {
  // Solo 'esperando' (default de getWatchlist): candidatas que pasaron Etapa 1 pero
  // todavia no tocaron precio de entrada. Las compradas ya estan en Posiciones; las
  // descartadas no son parte de nada activo.
  const entries = await getWatchlist();

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Watchlist
        </h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Candidatas que ya pasaron el negocio (Etapa 1) — esperando que el precio tenga
          sentido.
        </p>
      </header>

      <Card title={`Esperando precio (${entries.length})`}>
        <WatchlistTable entries={entries} />
      </Card>
    </div>
  );
}
