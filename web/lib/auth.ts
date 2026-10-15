// Password gate del dashboard. No hay usuarios ni tabla de sesiones — es un portafolio
// personal con un solo visitante esperado (LP), asi que una cookie firmada con expiracion
// alcanza. Se usa Web Crypto (subtle) en vez del modulo "crypto" de Node para que esto
// corra igual en el runtime Edge que en Node, sin tener que fijar el runtime del middleware.

const COOKIE_NAME = "ataraxia_dashboard_session";
const SESSION_DURATION_MS = 1000 * 60 * 60 * 24 * 30; // 30 dias

function getSecret(): string {
  const secret = process.env.SESSION_SECRET;
  if (!secret) {
    throw new Error(
      "Falta SESSION_SECRET en el entorno. Generar con: openssl rand -base64 32"
    );
  }
  return secret;
}

async function hmac(data: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return Buffer.from(sig).toString("base64url");
}

export async function createSessionToken(): Promise<string> {
  const payload = JSON.stringify({ exp: Date.now() + SESSION_DURATION_MS });
  const encodedPayload = Buffer.from(payload).toString("base64url");
  const signature = await hmac(encodedPayload, getSecret());
  return `${encodedPayload}.${signature}`;
}

export async function isValidSessionToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const [encodedPayload, signature] = token.split(".");
  if (!encodedPayload || !signature) return false;

  const expectedSignature = await hmac(encodedPayload, getSecret());
  // Comparacion de longitud fija para no filtrar informacion de timing sobre cuanto del
  // hash coincide. No es el riesgo principal aca (es un dashboard personal, no un banco),
  // pero no cuesta nada hacerlo bien.
  if (signature.length !== expectedSignature.length) return false;
  let diff = 0;
  for (let i = 0; i < signature.length; i++) {
    diff |= signature.charCodeAt(i) ^ expectedSignature.charCodeAt(i);
  }
  if (diff !== 0) return false;

  try {
    const payload = JSON.parse(Buffer.from(encodedPayload, "base64url").toString());
    return typeof payload.exp === "number" && payload.exp > Date.now();
  } catch {
    return false;
  }
}

export function checkPassword(candidate: string): boolean {
  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) {
    throw new Error("Falta DASHBOARD_PASSWORD en el entorno.");
  }
  // Mismo criterio de comparacion de tiempo constante que la firma, por la misma razon.
  if (candidate.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < candidate.length; i++) {
    diff |= candidate.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return diff === 0;
}

export { COOKIE_NAME };
