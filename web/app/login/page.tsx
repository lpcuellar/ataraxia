import LoginForm from "./LoginForm";

// searchParams (de donde viene el redirect) es dato de request, no estatico. Misma razon
// que en la pagina principal: esta ruta se renderiza en el servidor en cada visita.
export const instant = false;

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string }>;
}) {
  const { from } = await searchParams;

  return (
    <main
      className="flex min-h-screen items-center justify-center px-4"
      style={{ background: "var(--page-plane)" }}
    >
      <div
        className="flex w-full max-w-sm flex-col items-center gap-6 rounded-xl border p-8"
        style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
      >
        <h1 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
          Ataraxia
        </h1>
        <LoginForm from={from ?? "/"} />
      </div>
    </main>
  );
}
