export interface OhlcvBar {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export async function fetchBinanceOhlcv(
  symbol: string,
  interval = "1h",
  limit = 90
): Promise<OhlcvBar[]> {
  const url = `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`;
  const res = await fetch(url, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error(`Binance error for ${symbol}: ${res.status}`);
  const rows: unknown[][] = await res.json();
  return rows.map((r) => ({
    timestamp: r[0] as number,
    open: parseFloat(r[1] as string),
    high: parseFloat(r[2] as string),
    low: parseFloat(r[3] as string),
    close: parseFloat(r[4] as string),
    volume: parseFloat(r[5] as string),
  }));
}

export async function fetchBinanceExchangeInfo(): Promise<Set<string>> {
  const res = await fetch("https://api.binance.com/api/v3/exchangeInfo", {
    next: { revalidate: 3600 },
  });
  if (!res.ok) throw new Error(`Binance exchangeInfo error: ${res.status}`);
  const json = await res.json();
  const symbols = new Set<string>();
  for (const s of json.symbols ?? []) {
    if (s.status === "TRADING" && s.quoteAsset === "USDT" && s.isSpotTradingAllowed) {
      symbols.add(s.symbol as string);
    }
  }
  return symbols;
}
