"""
TEMA + MACD ensemble for BTC-USD (daily).

- TEMA: classic triple-exponential moving average trend filter
- MACD: 12/26/9 momentum confirmation
- Ensemble: weighted vote (default 50/50) with optional consensus mode

Signals are shifted by one bar before P&L (no lookahead).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

EnsembleMode = Literal["weighted", "consensus"]


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def tema(close: pd.Series, period: int) -> pd.Series:
    e1 = ema(close, period)
    e2 = ema(e1, period)
    e3 = ema(e2, period)
    return 3 * e1 - 3 * e2 + e3


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    line = fast_ema - slow_ema
    sig = ema(line, signal)
    hist = line - sig
    return pd.DataFrame({"macd": line, "signal": sig, "hist": hist})


def tema_signal(close: pd.Series, tema_line: pd.Series) -> pd.Series:
    """+1 bullish, 0 neutral, -1 bearish."""
    above = close > tema_line
    slope = tema_line.diff() > 0
    sig = pd.Series(0.0, index=close.index)
    sig[above & slope] = 1.0
    sig[(~above) & (~slope)] = -1.0
    return sig


def macd_signal(m: pd.DataFrame) -> pd.Series:
    sig = pd.Series(0.0, index=m.index)
    sig[(m["hist"] > 0) & (m["macd"] > m["signal"])] = 1.0
    sig[(m["hist"] < 0) & (m["macd"] < m["signal"])] = -1.0
    return sig


@dataclass(frozen=True)
class EnsembleConfig:
    ticker: str = "BTC-USD"
    tema_period: int = 55
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    tema_weight: float = 0.5
    macd_weight: float = 0.5
    mode: EnsembleMode = "weighted"
    long_only: bool = True
    long_threshold: float = 0.35
    flat_threshold: float = 0.05
    cost_bps: float = 10.0
    ann_days: int = 365


def combine_signals(
    s_tema: pd.Series,
    s_macd: pd.Series,
    cfg: EnsembleConfig,
) -> pd.Series:
    w_t = cfg.tema_weight
    w_m = cfg.macd_weight
    w_sum = w_t + w_m
    score = (w_t * s_tema + w_m * s_macd) / w_sum

    if cfg.mode == "consensus":
        pos = pd.Series(0.0, index=score.index)
        pos[(s_tema > 0) & (s_macd > 0)] = 1.0
        if not cfg.long_only:
            pos[(s_tema < 0) & (s_macd < 0)] = -1.0
        return pos

    pos = pd.Series(0.0, index=score.index)
    pos[score >= cfg.long_threshold] = 1.0
    if not cfg.long_only:
        pos[score <= -cfg.long_threshold] = -1.0
    # hysteresis band around zero
    pos[(score.abs() < cfg.flat_threshold)] = 0.0
    return pos


def build_ensemble_frame(close: pd.Series, cfg: EnsembleConfig) -> pd.DataFrame:
    t = tema(close, cfg.tema_period)
    m = macd(close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    s_t = tema_signal(close, t)
    s_m = macd_signal(m)
    pos_raw = combine_signals(s_t, s_m, cfg)
    pos = pos_raw.shift(1).fillna(0.0)

    ret = close.pct_change().fillna(0.0)
    turnover = pos.diff().abs().fillna(0.0)
    strat_ret = pos * ret - turnover * (cfg.cost_bps / 1e4)
    equity = (1 + strat_ret).cumprod()

    out = pd.DataFrame(
        {
            "close": close,
            "tema": t,
            "macd": m["macd"],
            "macd_signal": m["signal"],
            "macd_hist": m["hist"],
            "sig_tema": s_t,
            "sig_macd": s_m,
            "ensemble_score": (cfg.tema_weight * s_t + cfg.macd_weight * s_m)
            / (cfg.tema_weight + cfg.macd_weight),
            "position": pos,
            "return": strat_ret,
            "equity": equity,
        },
        index=close.index,
    )
    return out


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1
    return float(dd.min())


def sharpe(returns: pd.Series, ann_days: int = 365) -> float:
    r = returns.dropna()
    if len(r) < 2 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * np.sqrt(ann_days))


def summarize_backtest(df: pd.DataFrame, ann_days: int = 365) -> dict:
    eq = df["equity"].dropna()
    if len(eq) < 2:
        return {}
    tot = eq.iloc[-1] - 1
    years = len(df) / ann_days
    cagr = (eq.iloc[-1] ** (1 / max(years, 1e-9)) - 1) if years > 0 else float("nan")
    return {
        "total_return": float(tot),
        "cagr": float(cagr),
        "sharpe": sharpe(df["return"], ann_days),
        "max_drawdown": max_drawdown(eq),
        "bars": len(df),
    }


def load_btc_close(start: str = "2018-01-01") -> pd.Series:
    import yfinance as yf

    data = yf.download("BTC-USD", start=start, interval="1d", auto_adjust=True, progress=False)
    if data.empty:
        raise RuntimeError("Failed to download BTC-USD")
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
    else:
        close = data["Close"]
    close = close.astype(float).squeeze()
    close.name = "BTC-USD"
    return close.dropna()


def run_default_ensemble(close: pd.Series | None = None) -> tuple[pd.DataFrame, dict]:
    cfg = EnsembleConfig()
    if close is None:
        close = load_btc_close()
    df = build_ensemble_frame(close, cfg)
    stats = summarize_backtest(df, cfg.ann_days)
    return df, stats
