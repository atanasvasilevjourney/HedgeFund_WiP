export type PricePanel = Record<string, number[]>;

async function fetchSingleTickerCloses(
  ticker: string,
  range: string
): Promise<{ dates: string[]; closes: number[] }> {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=${range}&interval=1d&includePrePost=false`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 HedgeFundTerminal/0.1" },
    next: { revalidate: 300 },
  });

  if (!res.ok) {
    throw new Error(`Yahoo Finance error for ${ticker}: ${res.status}`);
  }

  const json = await res.json();
  const r = json?.chart?.result?.[0];
  if (!r) {
    throw new Error(`Yahoo Finance returned no data for ${ticker}`);
  }

  const timestamps: number[] = r.timestamp ?? [];
  const closes: number[] = r.indicators?.quote?.[0]?.close ?? [];
  const dates = timestamps.map((t) => new Date(t * 1000).toISOString().slice(0, 10));
  return { dates, closes: closes.map((c) => c ?? NaN) };
}

export async function fetchYahooCloses(
  tickers: string[],
  range = "3y"
): Promise<{ dates: string[]; panel: PricePanel }> {
  if (tickers.length === 0) {
    throw new Error("No tickers provided");
  }

  if (tickers.length === 1) {
    const { dates, closes } = await fetchSingleTickerCloses(tickers[0], range);
    return { dates, panel: { [tickers[0]]: closes } };
  }

  // Multi-ticker: fetch individually (Yahoo batch chart is unreliable)
  const panels: Array<{ ticker: string; closes: number[]; dates: string[] }> = [];
  const chunkSize = 6;
  for (let i = 0; i < tickers.length; i += chunkSize) {
    const chunk = tickers.slice(i, i + chunkSize);
    const chunkResults = await Promise.all(
      chunk.map(async (ticker) => {
        const { dates, closes } = await fetchSingleTickerCloses(ticker, range);
        return { ticker, closes, dates };
      })
    );
    panels.push(...chunkResults);
  }

  const dateSet = new Set<string>();
  panels.forEach((p) => p.dates.forEach((d) => dateSet.add(d)));
  const dates = [...dateSet].sort();

  const panel: PricePanel = {};
  for (const { ticker, closes, dates: dts } of panels) {
    const map = new Map(dts.map((d, i) => [d, closes[i]]));
    let last = NaN;
    panel[ticker] = dates.map((d) => {
      const v = map.get(d);
      if (v !== undefined && !Number.isNaN(v)) last = v;
      return last;
    });
  }

  return { dates, panel };
}

export async function fetchLiveQuotes(tickers: string[]): Promise<Record<string, number>> {
  const out: Record<string, number> = {};
  await Promise.all(
    tickers.map(async (ticker) => {
      try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=1d&interval=1d`;
        const res = await fetch(url, {
          headers: { "User-Agent": "Mozilla/5.0 HedgeFundTerminal/0.1" },
          cache: "no-store",
        });
        const json = await res.json();
        const meta = json?.chart?.result?.[0]?.meta;
        out[ticker] = meta?.regularMarketPrice ?? meta?.previousClose ?? NaN;
      } catch {
        out[ticker] = NaN;
      }
    })
  );
  return out;
}
