// Nombres de empresa para mostrar junto al ticker. No hay columna "nombre" en
// portfolio_lots (Schwab tampoco la trae en el Lot Details export), asi que esto es un
// mapeo estatico de los tickers vistos hasta ahora en el portafolio — no una fuente de
// datos. Un ticker nuevo que no este aca cae al fallback (mostrar solo el ticker, sin
// nombre), no a un error ni a un nombre inventado. Actualizar a mano cuando entre una
// posicion nueva.
export const TICKER_NAMES: Record<string, string> = {
  AMZN: "Amazon.com",
  GOOG: "Alphabet",
  META: "Meta Platforms",
  UNH: "UnitedHealth Group",
  XOM: "ExxonMobil",
  SPGI: "S&P Global",
  GE: "GE Aerospace",
  UBER: "Uber Technologies",
  BN: "Brookfield Corp",
  CIFR: "Cipher Digital",
  IREN: "IREN",
  INFQ: "Infleqtion",
  LRCX: "Lam Research",
  MTZ: "MasTec",
  MA: "Mastercard",
  KO: "Coca-Cola",
  OXY: "Occidental Petroleum",
  CLSK: "CleanSpark",
  VOO: "Vanguard S&P 500 ETF",
  SCHD: "Schwab U.S. Dividend Equity ETF",
  SCHG: "Schwab U.S. Large-Cap Growth ETF",
  ITOT: "iShares Core S&P Total US Stock Market ETF",
  VXUS: "Vanguard Total International Stock ETF",
};

export function tickerName(ticker: string): string | null {
  return TICKER_NAMES[ticker.toUpperCase()] ?? null;
}
