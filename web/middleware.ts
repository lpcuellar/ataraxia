import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME, isValidSessionToken } from "@/lib/auth";

export async function middleware(request: NextRequest) {
  // /login y sus assets quedan afuera del gate — si no, nadie podria ni cargar el
  // formulario para loguearse.
  if (request.nextUrl.pathname.startsWith("/login")) {
    return NextResponse.next();
  }

  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (await isValidSessionToken(token)) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("from", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Corre sobre todo excepto los assets internos de Next y favicon — esos no exponen datos
  // y bloquearlos innecesariamente podria romper el render de la pagina de login misma.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
