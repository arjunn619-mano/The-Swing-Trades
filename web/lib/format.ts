// Neon returns NUMERIC as strings to preserve precision — coerce explicitly.
export const num = (x: unknown): number | null =>
  x === null || x === undefined || x === "" ? null : Number(x);

export const pct = (x: number | null, dp = 1) =>
  x === null || Number.isNaN(x) ? "—" : `${(x * 100).toFixed(dp)}%`;

export const money = (x: number | null) =>
  x === null || Number.isNaN(x)
    ? "—"
    : `₹${Number(x).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export const fixed = (x: number | null, dp = 2) =>
  x === null || Number.isNaN(x) ? "—" : Number(x).toFixed(dp);

export const dateStr = (x: string | null) =>
  x ? new Date(x).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";

// Per-stock TradingView chart (Dhan has no per-stock URL). e.g. NSE:RELIANCE.
export function chartUrl(exchange: string | null, ticker: string | null): string | null {
  if (!ticker || !exchange) return null;
  const ex = exchange.toUpperCase() === "BSE" ? "BSE" : "NSE";
  return `https://in.tradingview.com/chart/?symbol=${ex}:${encodeURIComponent(ticker)}`;
}
