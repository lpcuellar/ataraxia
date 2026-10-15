"use client";

import { useActionState } from "react";
import { login } from "./actions";

export default function LoginForm({ from }: { from: string }) {
  const [state, formAction, pending] = useActionState(
    async (_prev: { error?: string }, formData: FormData) => {
      return (await login(formData)) ?? {};
    },
    {}
  );

  return (
    <form action={formAction} className="flex flex-col gap-4 w-full max-w-sm">
      <input type="hidden" name="from" value={from} />
      <label className="flex flex-col gap-1">
        <span className="text-sm text-zinc-400">Contraseña</span>
        <input
          type="password"
          name="password"
          autoFocus
          required
          className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-zinc-100
                     outline-none focus:border-zinc-400"
        />
      </label>
      {state.error && <p className="text-sm text-red-400">{state.error}</p>}
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900
                   hover:bg-zinc-300 disabled:opacity-50"
      >
        {pending ? "Entrando..." : "Entrar"}
      </button>
    </form>
  );
}
