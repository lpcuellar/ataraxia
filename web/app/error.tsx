"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-zinc-950 px-4 text-center">
      <h1 className="text-lg font-semibold text-zinc-100">No se pudo cargar el dashboard</h1>
      <p className="max-w-md text-sm text-zinc-400">
        Hubo un problema leyendo los datos de Supabase. Si acabás de aplicar la migración del
        rol de solo lectura, puede que todavía no haya propagado — probá de nuevo en un
        momento.
      </p>
      {process.env.NODE_ENV !== "production" && (
        <pre className="max-w-lg overflow-x-auto rounded bg-zinc-900 p-3 text-left text-xs text-red-400">
          {error.message}
        </pre>
      )}
      <button
        onClick={() => reset()}
        className="rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-300"
      >
        Reintentar
      </button>
    </main>
  );
}
