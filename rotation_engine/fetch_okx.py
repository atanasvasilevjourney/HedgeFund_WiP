"""
Fetch real crypto market data from OKX's public, keyless API.

Run this WHEREVER you have real network access -- confirmed blocked in this sandboxed
container (same network policy that blocked yfinance and CoinGecko all session), but the
API itself is real, live, and reachable: this exact endpoint returned ~700+ live SPOT
tickers when tested via a one-off fetch.

Two things this gets you that CoinGecko couldn't:
1. All SPOT tickers with 24h volume in ONE request (no pagination needed for the ranking step)
2. Real historical OHLCV candles per instrument via /market/candles -- an exchange gives you
   actual tradeable price history, not a market-cap-data-provider's derived series

No API key required for any of this -- these are OKX's public market-data endpoints.
"""
import time
import requests
import pandas as pd

BASE = "https://www.okx.com/api/v5"


def fetch_all_spot_tickers(quote_filter=None):
    """One request, ALL spot tickers with live price + 24h volume. quote_filter, e.g. 'USDT',
    restricts to pairs quoted in that currency (recommended -- OKX lists the same base asset
    against USDT, USDC, USD, EUR, TRY, BRL... separately, which double/triple-counts volume
    if you don't filter to one quote currency)."""
    resp = requests.get(f"{BASE}/market/tickers", params={"instType": "SPOT"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]
    df = pd.DataFrame(data)
    numeric_cols = ["last", "vol24h", "volCcy24h", "open24h", "high24h", "low24h"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if quote_filter:
        df = df[df["instId"].str.endswith(f"-{quote_filter}")]
    df["base"] = df["instId"].str.split("-").str[0]
    return df.sort_values("volCcy24h", ascending=False).reset_index(drop=True)


def fetch_candles(inst_id, bar="1D", limit=300, before=None, after=None):
    """Historical OHLCV. bar: '1m','5m','15m','1H','4H','1D','1W', etc.
    OKX caps each response at 300 bars -- for a real multi-year daily history, page backward
    using 'after' (the oldest timestamp from the previous batch) across repeated calls."""
    params = {"instId": inst_id, "bar": bar, "limit": limit}
    if before:
        params["before"] = before
    if after:
        params["after"] = after
    resp = requests.get(f"{BASE}/market/history-candles", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]
    cols = ["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"]
    df = pd.DataFrame(data, columns=cols[:len(data[0])] if data else cols)
    if not df.empty:
        df["ts"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms")
        for c in ["open", "high", "low", "close", "vol"]:
            df[c] = pd.to_numeric(df[c])
        df = df.sort_values("ts").reset_index(drop=True)
    return df


def fetch_full_history(inst_id, bar="1D", target_bars=1500, sleep_between=0.3):
    """Pages backward through history-candles to build a longer series than the 300-bar cap."""
    all_chunks = []
    after = None
    while sum(len(c) for c in all_chunks) < target_bars:
        chunk = fetch_candles(inst_id, bar=bar, limit=300, after=after)
        if chunk.empty:
            break
        all_chunks.append(chunk)
        after = str(int(chunk["ts"].iloc[0].timestamp() * 1000))   # page further back
        time.sleep(sleep_between)
    if not all_chunks:
        return pd.DataFrame()
    full = pd.concat(all_chunks).drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    return full.tail(target_bars)


if __name__ == "__main__":
    print("Fetching all USDT-quoted spot tickers, ranked by 24h quote volume...")
    tickers = fetch_all_spot_tickers(quote_filter="USDT")
    print(f"Got {len(tickers)} USDT pairs\n")
    print(tickers[["instId", "last", "vol24h", "volCcy24h"]].head(30).to_string(index=False))
    tickers.to_csv("okx_usdt_tickers_ranked.csv", index=False)

    print("\nFetching ~1500 days of BTC-USDT daily history as a worked example...")
    btc_hist = fetch_full_history("BTC-USDT", bar="1D", target_bars=1500)
    print(f"Got {len(btc_hist)} daily bars, {btc_hist['ts'].min()} -> {btc_hist['ts'].max()}")
    btc_hist.to_csv("okx_btc_usdt_daily.csv", index=False)
