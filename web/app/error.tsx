"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main
      className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center"
      style={{ background: "var(--page-plane)" }}
    >
      <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
        No se pudo cargar el dashboard
      </h1>
      <p className="max-w-md text-sm" style={{ color: "var(--text-secondary)" }}>
        Hubo un problema leyendo los datos de Supabase. Si acabás de aplicar la migración del
        rol de solo lectura, puede que todavía no haya propagado — probá de nuevo en un
        momento.
      </p>
      {process.env.NODE_ENV !== "production" && (
        <pre
          className="max-w-lg overflow-x-auto rounded-lg border p-3 text-left text-xs"
          style={{
            borderColor: "var(--border)",
            background: "var(--surface-1)",
            color: "var(--status-critical)",
          }}
        >
          {error.message}
        </pre>
      )}
      <button
        onClick={() => reset()}
        className="rounded-lg px-3 py-2 text-sm font-medium text-white"
        style={{ background: "var(--series-1)" }}
      >
        Reintentar
      </button>
    </main>
  );
}
