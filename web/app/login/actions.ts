"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { checkPassword, createSessionToken, COOKIE_NAME } from "@/lib/auth";

export async function login(formData: FormData): Promise<{ error?: string }> {
  const password = String(formData.get("password") ?? "");
  const from = String(formData.get("from") ?? "/");

  if (!checkPassword(password)) {
    return { error: "Contraseña incorrecta." };
  }

  const token = await createSessionToken();
  const store = await cookies();
  store.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });

  // from viene del middleware (a donde intentabas entrar antes del redirect a /login). Se
  // valida que sea una ruta relativa propia, nunca una URL absoluta externa — si no, esto
  // seria una redireccion abierta que alguien podria usar para phishing con el dominio real.
  redirect(from.startsWith("/") && !from.startsWith("//") ? from : "/");
}

export async function logout(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
  redirect("/login");
}
