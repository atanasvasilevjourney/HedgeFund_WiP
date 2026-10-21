"""TEMA, Schaff trend-cycle regime, and double KAMA.

TEMA matches TA-Lib: each EMA is SMA-seeded, and TEMA = 3*E1 - 3*E2 + E3.
The ``ema`` kind matches the triple-EMA notebook (pandas ewm, adjust=False),
which searches the same (7, 137, 100) point but smooths with a single EMA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Panel token "a" is the named Schaff preset: cycle 10, smoothing factor 0.5.
STC_PRESETS = {
    "a": {"cycle": 10, "factor": 0.5},
}


def ema_pandas(x: np.ndarray, n: int) -> np.ndarray:
    """EMA seeded the way ``ewm(span=n, adjust=False)`` seeds it."""
    x = np.asarray(x, dtype=float)
    out = np.empty(len(x), dtype=float)
    if len(x) == 0:
        return out
    alpha = 2.0 / (n + 1.0)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1.0 - alpha) * out[i - 1]
    return out


def ema_talib(x: np.ndarray, n: int) -> np.ndarray:
    """TA-Lib EMA. ``x`` must be a contiguous finite window. First n-1 bars are NaN."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan, dtype=float)
    if n < 1 or len(x) < n:
        return out
    alpha = 2.0 / (n + 1.0)
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = alpha * x[i] + (1.0 - alpha) * out[i - 1]
    return out


def tema(x: np.ndarray, n: int) -> np.ndarray:
    """TA-Lib TEMA. First valid bar is at index ``3 * (n - 1)``."""
    x = np.asarray(x, dtype=float)
    e1 = ema_talib(x, n)
    e2 = np.full(len(x), np.nan, dtype=float)
    e3 = np.full(len(x), np.nan, dtype=float)
    if len(x) < n:
        return e1
    s1 = n - 1
    e2[s1:] = ema_talib(e1[s1:], n)
    s2 = s1 + (n - 1)
    if s2 < len(x):
        e3[s2:] = ema_talib(e2[s2:], n)
    return 3.0 * e1 - 3.0 * e2 + e3


def smooth_series(close: pd.Series, n: int, kind: str) -> pd.Series:
    values = close.to_numpy(dtype=float)
    if kind == "tema":
        out = tema(values, n)
    elif kind == "ema":
        out = ema_pandas(values, n)
    else:
        raise ValueError(f"unknown smooth kind {kind!r}")
    return pd.Series(out, index=close.index, name=f"{kind}{n}")


def kama(close: pd.Series, n: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
    """Kaufman adaptive MA, ported from ``KAMA-DF-stability-scoring``.

    Efficiency ratio over ``n``, smoothing constant squared between the
    fast and slow EMAs. The value at bar ``n`` is seeded with price.
    """
    x = close.to_numpy(dtype=float)
    out = np.full(len(x), np.nan, dtype=float)
    if len(x) <= n:
        return pd.Series(out, index=close.index, name=f"kama{n}")
    change = np.full(len(x), np.nan)
    volatility = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        window = x[i - n : i + 1]
        if not np.isfinite(window).all():
            continue
        change[i] = abs(x[i] - x[i - n])
        volatility[i] = np.abs(np.diff(window)).sum()
    er = change / (volatility + 1e-9)
    fast_sc = 2.0 / (fast + 1.0)
    slow_sc = 2.0 / (slow + 1.0)
    sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
    out[n] = x[n]
    for i in range(n + 1, len(x)):
        if not np.isfinite(out[i - 1]):
            continue
        step = sc[i] if np.isfinite(sc[i]) else 0.0
        out[i] = out[i - 1] + step * (x[i] - out[i - 1])
    return pd.Series(out, index=close.index, name=f"kama{n}")


def _rolling_stoch(values: np.ndarray, length: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    for i in range(length - 1, len(values)):
        window = values[i - length + 1 : i + 1]
        if not np.isfinite(window).all():
            continue
        lo = window.min()
        hi = window.max()
        if hi == lo:
            out[i] = 0.0 if i == length - 1 or not np.isfinite(out[i - 1]) else out[i - 1]
        else:
            out[i] = 100.0 * (values[i] - lo) / (hi - lo)
    return out


def _factor_smooth(values: np.ndarray, factor: float) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=float)
    started = False
    prev = 0.0
    for i, v in enumerate(values):
        if not np.isfinite(v):
            if started:
                out[i] = prev
            continue
        if not started:
            prev = v
            started = True
        else:
            prev = prev + factor * (v - prev)
        out[i] = prev
    return out


def stc(
    close: pd.Series,
    fast: int = 23,
    slow: int = 50,
    cycle: int = 10,
    factor: float = 0.5,
) -> pd.Series:
    """Schaff trend cycle.

    MACD(fast, slow), stochastic over ``cycle``, smoothed by ``factor``,
    stochastic again, smoothed again. The result sits on 0..100.
    """
    if cycle < 2:
        raise ValueError("STC cycle must be >= 2")
    fast_ma = ema_pandas(close.to_numpy(dtype=float), fast)
    slow_ma = ema_pandas(close.to_numpy(dtype=float), slow)
    macd = fast_ma - slow_ma
    k1 = _rolling_stoch(macd, cycle)
    d1 = _factor_smooth(k1, factor)
    k2 = _rolling_stoch(d1, cycle)
    d2 = _factor_smooth(k2, factor)
    return pd.Series(d2, index=close.index, name="stc")


def resolve_stc_preset(preset: str) -> dict:
    key = str(preset).lower()
    if key not in STC_PRESETS:
        raise KeyError(f"unknown STC preset {preset!r}; known: {sorted(STC_PRESETS)}")
    return STC_PRESETS[key]
