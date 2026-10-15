import "server-only";
import sharp from "sharp";

// El color "de marca" de cada logo, extraido del propio archivo SVG — no hay API de
// colores de marca gratis y confiable sin cuenta (se evaluaron Logo.dev, Brandfetch,
// LogoKit: las tres piden client ID/API key), asi que se calcula del logo que ya se usa
// (logos.stockanalysis.com). El CDN no manda CORS (verificado: sin header
// Access-Control-Allow-Origin), asi que leer pixeles con <canvas> en el navegador
// fallaria por "tainted canvas" — la extraccion tiene que ser del lado del servidor.
//
// Metodo: rasterizar el SVG a 32x32 con sharp (ya es dependencia de Next.js, no se agrega
// nada nuevo), descartar pixeles transparentes, casi-blancos, casi-negros y de poca
// saturacion (eso suele ser fondo o texto neutro, no la marca), y quedarse con el color
// mas frecuente entre lo que queda. Logos monocromos (Apple, Uber: la marca es literalmente
// negra) no tienen nada que pase el filtro de saturacion — caen al color por defecto.
//
// Ojo: esto NO paso por scripts/validate_palette.js de la skill dataviz. Son colores de
// marca real de cada empresa, no una paleta categorica elegida — el catalogo de colores
// categoricos exige separacion CVD validada entre slots, y 13+ colores de marca sin
// coordinar entre si no la garantizan. La mitigacion es que cada barra ya lleva el logo y
// el ticker como etiqueta directa (references/marks-and-anatomy.md): la identidad nunca
// depende solo del color, asi que un color de marca mal distinguido para un lector con
// daltonismo sigue siendo legible por el logo y el texto.
const DEFAULT_COLOR = "#3987e5"; // --series-1 dark, mismo que el bar solido anterior

const cache = new Map<string, Promise<string>>();

async function extractDominantColor(ticker: string): Promise<string> {
  try {
    const res = await fetch(`https://logos.stockanalysis.com/${ticker.toLowerCase()}.svg`);
    if (!res.ok) return DEFAULT_COLOR;
    const svg = Buffer.from(await res.arrayBuffer());

    const { data } = await sharp(svg)
      .resize(32, 32, { fit: "contain" })
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });

    const counts = new Map<string, number>();
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const a = data[i + 3];
      if (a < 128) continue; // transparente
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      const saturation = max === 0 ? 0 : (max - min) / max;
      if (max > 240 && min > 230) continue; // casi blanco — fondo tipico
      if (max < 40) continue; // casi negro — suele ser texto, no la marca
      if (saturation < 0.15) continue; // gris: no aporta identidad de color

      // Se agrupa en baldes de 16 para que variaciones minimas de antialiasing no
      // dispersen el conteo entre docenas de tonos casi iguales.
      const bucket = [r, g, b]
        .map((v) => Math.min(240, Math.round(v / 16) * 16))
        .join(",");
      counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
    }

    let best: string | null = null;
    let bestCount = 0;
    for (const [bucket, count] of counts) {
      if (count > bestCount) {
        bestCount = count;
        best = bucket;
      }
    }
    if (!best) return DEFAULT_COLOR;
    const [r, g, b] = best.split(",").map(Number);
    return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
  } catch {
    return DEFAULT_COLOR;
  }
}

/** Colores de marca para un lote de tickers, calculados en paralelo y cacheados en
 * memoria del proceso (el color de un logo no cambia entre requests — recalcularlo en
 * cada carga de pagina seria descargar y rasterizar los mismos SVGs una y otra vez). */
export async function getLogoColors(tickers: string[]): Promise<Record<string, string>> {
  const unique = [...new Set(tickers.map((t) => t.toUpperCase()))];
  const entries = await Promise.all(
    unique.map(async (ticker) => {
      if (!cache.has(ticker)) {
        cache.set(ticker, extractDominantColor(ticker));
      }
      return [ticker, await cache.get(ticker)!] as const;
    })
  );
  return Object.fromEntries(entries);
}
