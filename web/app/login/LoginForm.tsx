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
    <form action={formAction} className="flex w-full max-w-sm flex-col gap-4">
      <input type="hidden" name="from" value={from} />
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          Contraseña
        </span>
        <input
          type="password"
          name="password"
          autoFocus
          required
          className="rounded-lg border px-3 py-2.5 text-sm outline-none transition-colors focus:ring-2"
          style={{
            borderColor: "var(--border)",
            background: "var(--surface-1)",
            color: "var(--text-primary)",
          }}
        />
      </label>
      {state.error && (
        <p className="text-sm" style={{ color: "var(--status-critical)" }}>
          {state.error}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="rounded-lg px-3 py-2.5 text-sm font-medium text-white transition-opacity disabled:opacity-50"
        style={{ background: "var(--series-1)" }}
      >
        {pending ? "Entrando..." : "Entrar"}
      </button>
    </form>
  );
}
