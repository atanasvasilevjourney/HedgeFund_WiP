export interface CoinMarketRow {
  id: string;
  symbol: string;
  name: string;
  market_cap: number;
  total_volume: number;
}

export interface CoinGeckoBar {
  timestamp: number;
  close: number;
  volume: number;
}

export async function fetchTopCoins(limit = 100): Promise<CoinMarketRow[]> {
  const url = `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=${limit}&page=1&sparkline=false`;
  const res = await fetch(url, { next: { revalidate: 1800 } });
  if (!res.ok) throw new Error(`CoinGecko error: ${res.status}`);
  return res.json();
}

/** Hourly-ish bars via market_chart (fallback when Binance is blocked). */
export async function fetchCoinGeckoHourly(
  coinId: string,
  days = 7
): Promise<CoinGeckoBar[]> {
  const url = `https://api.coingecko.com/api/v3/coins/${coinId}/market_chart?vs_currency=usd&days=${days}`;
  const res = await fetch(url, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error(`CoinGecko chart error for ${coinId}: ${res.status}`);
  const json = await res.json();
  const prices: [number, number][] = json.prices ?? [];
  const volumes: [number, number][] = json.total_volumes ?? [];
  const volMap = new Map(volumes.map(([t, v]) => [t, v]));

  return prices.map(([ts, price]) => ({
    timestamp: ts,
    close: price,
    volume: volMap.get(ts) ?? 0,
  }));
}
