import { getRecommendations } from "@/lib/db";
import RecommendationsTable from "@/components/RecommendationsTable";
import Card from "@/components/Card";

export const instant = false;

export default async function RecommendationsPage() {
  const recommendations = await getRecommendations();

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Recomendaciones
        </h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Bitácora completa — qué recomendó Ataraxia y qué hizo LP con cada una.
        </p>
      </header>

      <Card title="Bitácora de recomendaciones">
        <RecommendationsTable recommendations={recommendations} />
      </Card>
    </div>
  );
}
