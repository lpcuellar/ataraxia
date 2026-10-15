"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { logout } from "@/app/login/actions";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/positions", label: "Posiciones" },
  { href: "/recommendations", label: "Recomendaciones" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="flex h-screen w-56 shrink-0 flex-col justify-between border-r px-4 py-6"
      style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
    >
      <div className="flex flex-col gap-8">
        <p className="px-2 text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          Ataraxia
        </p>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-lg px-2.5 py-2 text-sm font-medium transition-colors"
                style={{
                  color: active ? "var(--series-1)" : "var(--text-secondary)",
                  background: active ? "rgba(57, 135, 229, 0.15)" : "transparent",
                }}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
      <form action={logout}>
        <button
          type="submit"
          className="w-full rounded-lg border px-2.5 py-2 text-left text-sm font-medium transition-colors"
          style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
        >
          Salir
        </button>
      </form>
    </aside>
  );
}
