"use client";

import { useState } from "react";

// stockanalysis.com ya es la fuente de precios del lado Python (src/data/market.py) —
// su CDN de logos no pide API key y respondio 200 en los 8 tickers que se probaron antes
// de usarla (acciones y ETFs por igual): https://logos.stockanalysis.com/{ticker}.svg
export default function TickerLogo({ ticker, size = 24 }: { ticker: string; size?: number }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    // Si el logo no existe para ese ticker, un circulo con las iniciales en vez de un
    // icono roto — nunca un <img> sin src visible.
    return (
      <span
        className="flex shrink-0 items-center justify-center rounded-full text-[9px] font-semibold"
        style={{
          width: size,
          height: size,
          background: "var(--surface-raised)",
          color: "var(--text-muted)",
        }}
      >
        {ticker.slice(0, 2)}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- CDN externa de un dominio ya
    // confiable del proyecto (stockanalysis.com); next/image exigiria whitelist + config
    // de SVG remoto por una etiqueta chica que no necesita optimizacion.
    <img
      src={`https://logos.stockanalysis.com/${ticker.toLowerCase()}.svg`}
      alt=""
      width={size}
      height={size}
      className="shrink-0 rounded-full"
      style={{ width: size, height: size, objectFit: "contain" }}
      onError={() => setFailed(true)}
    />
  );
}
