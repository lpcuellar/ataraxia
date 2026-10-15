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
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="flex flex-col gap-6 items-center">
        <h1 className="text-xl font-semibold text-zinc-100">Ataraxia</h1>
        <LoginForm from={from ?? "/"} />
      </div>
    </main>
  );
}
