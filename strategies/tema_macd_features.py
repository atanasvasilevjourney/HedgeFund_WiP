"""Feature library for TEMA/MACD BTC ensemble research."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.tema_macd_ensemble_btc import ema, macd, tema, tema_signal, macd_signal


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    rs = up.ewm(alpha=1 / period, adjust=False).mean() / (
        down.ewm(alpha=1 / period, adjust=False).mean() + 1e-12
    )
    return 100 - (100 / (1 + rs))


def build_feature_matrix(
    close: pd.Series,
    tema_periods: tuple[int, ...] = (21, 34, 55, 89),
    macd_configs: tuple[tuple[int, int, int], ...] = ((8, 21, 5), (12, 26, 9), (19, 39, 9)),
) -> pd.DataFrame:
    feats: dict[str, pd.Series] = {}

    for p in tema_periods:
        t = tema(close, p)
        feats[f"tema_{p}_dist"] = (close / t - 1).replace([np.inf, -np.inf], np.nan)
        feats[f"tema_{p}_slope"] = t.pct_change(5)
        feats[f"sig_tema_{p}"] = tema_signal(close, t)

    for i, (fast, slow, sig) in enumerate(macd_configs):
        m = macd(close, fast, slow, sig)
        prefix = f"macd_{fast}_{slow}_{sig}"
        feats[f"{prefix}_hist"] = m["hist"]
        feats[f"{prefix}_hist_norm"] = m["hist"] / (close * 0.01 + 1e-9)
        feats[f"{prefix}_sig"] = macd_signal(m)
        feats[f"{prefix}_line"] = m["macd"]

    for w in (5, 10, 21, 63):
        feats[f"mom_{w}"] = close.pct_change(w)
        feats[f"vol_{w}"] = close.pct_change().rolling(w).std() * np.sqrt(365)

    feats["rsi_14"] = rsi(close, 14)
    feats["rsi_7"] = rsi(close, 7)

    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema200 = ema(close, 200)
    feats["ema20_50_spread"] = ema20 / ema50 - 1
    feats["ema50_200_spread"] = ema50 / ema200 - 1
    feats["above_ema200"] = (close > ema200).astype(float)

    df = pd.DataFrame(feats, index=close.index)
    return df.replace([np.inf, -np.inf], np.nan)


def forward_return_labels(close: pd.Series, horizon: int = 1) -> pd.Series:
    """Binary label: 1 if forward return > 0."""
    fwd = close.shift(-horizon) / close - 1
    return (fwd > 0).astype(int)
