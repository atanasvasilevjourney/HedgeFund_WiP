"""
Fetch the top N crypto tokens by market cap from CoinGecko's free, keyless public API.

Run this WHEREVER you have real network access -- it will fail in the same sandboxed
environment that blocked yfinance all session (this isn't a CoinGecko-specific problem,
it's this container's network policy). Colab, local Python, or Claude Code with your own
machine's network access will all work unchanged.

No API key required. Rate-limited on the free tier -- this pages in chunks of 250 (the max
per request) and backs off on 429s, so pulling 1000 names is 4 requests, not 1000.
"""
import time
import requests
import pandas as pd

BASE = "https://api.coingecko.com/api/v3/coins/markets"


def fetch_top_n_tokens(n=1000, vs_currency="usd", per_page=250, sleep_between=1.5):
    """Returns a DataFrame: id, symbol, name, market_cap_rank, market_cap, total_volume,
    current_price, price_change_percentage_24h -- one row per token, ranked by market cap."""
    rows = []
    page = 1
    while len(rows) < n:
        params = {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "24h,7d,30d",
        }
        resp = requests.get(BASE, params=params, timeout=30)
        if resp.status_code == 429:
            print(f"Rate limited on page {page}, backing off 15s...")
            time.sleep(15)
            continue
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break   # ran out of ranked coins before hitting n
        rows.extend(data)
        print(f"Page {page}: got {len(data)} tokens (running total: {len(rows)})")
        page += 1
        time.sleep(sleep_between)   # be polite to the free tier

    df = pd.DataFrame(rows[:n])
    keep = ["id", "symbol", "name", "market_cap_rank", "market_cap", "total_volume",
            "current_price", "price_change_percentage_24h_in_currency"]
    return df[[c for c in keep if c in df.columns]]


if __name__ == "__main__":
    top1000 = fetch_top_n_tokens(1000)
    print(f"\nFetched {len(top1000)} tokens, rank {top1000['market_cap_rank'].min()} "
          f"to {top1000['market_cap_rank'].max()}")
    top1000.to_csv("top_1000_crypto.csv", index=False)
    print("Saved to top_1000_crypto.csv")
    print(top1000.head(20))
