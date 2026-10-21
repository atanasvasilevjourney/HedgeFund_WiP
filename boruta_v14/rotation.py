"""Frozen OR book on the beta-rotation sleeves.

The rotation system in ``carver_ultimate_daily_prop_engine_v1`` does two
jobs, and this module keeps both:

* Each sleeve ranks its own peers and keeps the strongest names. Indices
  stay with indices, stocks stay with stocks. A name is eligible only when
  its long forecast, its trend, its momentum, and its cross-sectional
  forecast are all positive. The sleeve then takes the top four, divides
  score by volatility, haircuts crowded names, and caps any one name at
  20% of the sleeve. Cash stays in the sleeve when the cap binds. The
  notebook rescales that remainder back to 100%, which puts a single name
  through the 20% cap. This port leaves the remainder in cash.
* XLY/XLP, RSP/SPY, and XLU/SPY vote one gross scale: 1.00 risk-on, 0.65
  neutral, 0.35 risk-off. The vote never opens a short.

The frozen TEMA / STC / double-KAMA book is a gate on those leaders, not a
second ranking. A leader is held only while its own OR book is long. Flat
leaders become cash. They are not replaced by the next name down the list.

Nothing here is chosen on the test sample. Lengths, sleeve caps, the top-four
count, the 20% cap, and the regime thresholds are the published presets.
The one departure from the notebook is the cross-sectional scale: the
notebook takes a median over the whole history, which looks ahead. The scale
here is a trailing median.

Decisions at the close of day t earn the return of day t+1. The OR position
is already lagged one bar inside ``execute``, so it lines up with that
same next-bar weight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from boruta_v14.backtest import execute
from boruta_v14.model import build_signals, frozen_params

ANN_DAYS = 252
FC_CAP = 20.0
FC_TARGET = 10.0
MAX_SINGLE_WEIGHT = 0.20
N_ASSETS = 4
CORR_WINDOW = 90
VOL_WINDOW = 30
TREND_FAST = 50
TREND_SLOW = 200
COST = 0.002  # 0.10% fee + 0.10% slippage per unit of turnover

CS_HORIZONS = (21, 63, 126)
CS_HORIZON_WEIGHTS = (0.25, 0.35, 0.40)
TS_MOM_HORIZONS = (5, 21, 63, 126, 252)
TS_MOM_WEIGHTS = (0.10, 0.20, 0.25, 0.25, 0.20)
EWMAC_PAIRS = ((8, 32, 5.95), (16, 64, 4.10), (32, 128, 2.79), (64, 256, 1.91))

INDICES = ("SPY", "QQQ", "DIA", "IWM")
STOCKS = ("AAPL", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "NVDA", "TSLA")
REGIME = ("XLY", "XLP", "XLU", "SPY", "RSP")
SLEEVE_CAPS = {"indices": 0.50, "stocks": 0.50}
REGIME_SCALES = {"RISK_ON": 1.0, "NEUTRAL": 0.65, "RISK_OFF": 0.35}


def ewm_std(x: pd.Series, span: int) -> pd.Series:
    alpha = 2.0 / (span + 1.0)
    mean = x.ewm(alpha=alpha, adjust=False).mean()
    second = (x * x).ewm(alpha=alpha, adjust=False).mean()
    var = (second - mean * mean).clip(lower=0)
    bias = (2.0 - 2.0 * alpha) / (2.0 - alpha)
    return np.sqrt(var / bias)


def vol_stack(close: pd.Series, ann_days: int = ANN_DAYS) -> pd.DataFrame:
    ret = close.pct_change().clip(-0.9, 9.0)
    short = ewm_std(ret, VOL_WINDOW) * np.sqrt(ann_days)
    anchor = short.rolling(5 * ann_days, min_periods=ann_days).mean()
    vol = pd.Series(np.where(anchor.isna(), short, 0.70 * short + 0.30 * anchor), index=close.index).clip(lower=1e-6)
    sigma_p = close * vol / np.sqrt(ann_days)
    return pd.DataFrame({"ret": ret, "vol": vol, "sigma_p": sigma_p})


def _clip_fc(x: pd.Series) -> pd.Series:
    return x.clip(-FC_CAP, FC_CAP)


def ewmac_forecast(close: pd.Series, sigma_p: pd.Series) -> pd.Series:
    parts = []
    for fast, slow, scale in EWMAC_PAIRS:
        raw = (close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()) / sigma_p
        parts.append((raw * scale).clip(-FC_CAP, FC_CAP))
    return _clip_fc(sum(parts) / len(parts) * 1.13)


def breakout_forecast(close: pd.Series) -> pd.Series:
    parts = []
    for window, scale, smooth in ((40, 0.70, 10), (80, 0.73, 20), (160, 0.74, 40), (320, 0.74, 80)):
        lo = close.rolling(window).min()
        hi = close.rolling(window).max()
        span = (hi - lo).replace(0, np.nan)
        pos = ((close - lo) / span).fillna(0.5)
        parts.append((((pos - 0.5) * 40).ewm(span=smooth, adjust=False).mean()) * scale)
    return _clip_fc(sum(parts) / len(parts) * 1.17)


def acceleration_forecast(close: pd.Series, sigma_p: pd.Series) -> pd.Series:
    bases = []
    for fast, slow, scale in EWMAC_PAIRS:
        raw = (close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()) / sigma_p
        bases.append((raw * scale).clip(-FC_CAP, FC_CAP))
    parts = []
    for base, shift, scale in zip(bases, (8, 16, 32, 64), (1.87, 1.90, 1.98, 2.05)):
        parts.append((base - base.shift(shift)) * scale)
    return _clip_fc(sum(parts) / len(parts) * 1.55)


def skew_forecast(ret: pd.Series) -> pd.Series:
    parts = []
    for window, scale, smooth in ((60, 33.3, 15), (120, 37.2, 30), (240, 39.2, 60)):
        skew = ret.rolling(window, min_periods=window // 2).skew()
        parts.append((-skew).ewm(span=smooth, adjust=False).mean() * scale)
    return _clip_fc(sum(parts) / len(parts) * 1.18)


def multihorizon_momentum(close: pd.Series) -> pd.Series:
    raw = sum(weight * (close / close.shift(horizon) - 1.0) for horizon, weight in zip(TS_MOM_HORIZONS, TS_MOM_WEIGHTS))
    scaled = raw / raw.rolling(252, min_periods=63).std()
    return scaled.clip(-3, 3) * (FC_TARGET / 2)


def trend_score(close: pd.Series) -> pd.Series:
    fast = close.ewm(span=TREND_FAST, adjust=False).mean()
    slow = close.ewm(span=TREND_SLOW, adjust=False).mean()
    return ((fast / slow) - 1.0).clip(-0.10, 0.10) * 100


def vol_attenuation(vol: pd.Series) -> pd.Series:
    pct = vol.rolling(1260, min_periods=252).rank(pct=True)
    return (1.5 - pct.ewm(span=10, adjust=False).mean()).clip(0.5, 1.5).fillna(1.0)


def time_series_forecasts(close: pd.Series, ann_days: int = ANN_DAYS) -> dict[str, pd.Series]:
    stack = vol_stack(close, ann_days)
    ewmac = ewmac_forecast(close, stack["sigma_p"])
    breakout = breakout_forecast(close)
    accel = acceleration_forecast(close, stack["sigma_p"])
    skew = skew_forecast(stack["ret"])
    momentum = multihorizon_momentum(close)
    trend = trend_score(close)
    combined = 0.25 * ewmac + 0.20 * breakout + 0.15 * accel + 0.15 * skew + 0.15 * momentum + 0.10 * trend
    combined = _clip_fc(combined * vol_attenuation(stack["vol"]))
    return {
        "long_fc": combined.clip(lower=0),
        "vol": stack["vol"],
        "trend": trend,
        "momentum": momentum,
    }


def normalized_price(close: pd.Series, ann_days: int = ANN_DAYS) -> pd.Series:
    stack = vol_stack(close, ann_days)
    risk_norm = (stack["ret"] / (stack["vol"] / np.sqrt(ann_days))).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return 100 * risk_norm.cumsum()


def _causal_scale(smooth: pd.Series) -> pd.Series:
    """10 / trailing median of absolute smoothed forecast. No full-sample median."""
    trail = smooth.abs().rolling(756, min_periods=126).mean()
    return 10.0 / trail.rolling(756, min_periods=126).median().clip(lower=1e-6)


def cross_sectional_forecasts(panel: pd.DataFrame, ann_days: int = ANN_DAYS) -> pd.DataFrame:
    prices = pd.DataFrame({name: normalized_price(panel[name], ann_days) for name in panel.columns})
    center = prices.mean(axis=1)
    out = {}
    for name in panel.columns:
        relative = prices[name] - center
        parts = []
        for horizon, weight in zip(CS_HORIZONS, CS_HORIZON_WEIGHTS):
            raw = (relative - relative.shift(horizon)) / horizon
            smooth = raw.ewm(span=max(2, horizon // 4), adjust=False).mean()
            parts.append(weight * (smooth * _causal_scale(smooth)))
        out[name] = sum(parts).clip(-FC_CAP, FC_CAP)
    return pd.DataFrame(out, index=panel.index)


def score_panels(panel: pd.DataFrame, ann_days: int = ANN_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Positive score and volatility, indexed like ``panel``. Ineligible names score 0."""
    cross = cross_sectional_forecasts(panel, ann_days)
    scores = {}
    vols = {}
    for name in panel.columns:
        forecast = time_series_forecasts(panel[name], ann_days)
        blended = (0.55 * forecast["long_fc"] + 0.45 * cross[name]).clip(lower=0)
        eligible = (forecast["trend"] > 0) & (forecast["momentum"] > 0) & (cross[name] > 0)
        scores[name] = blended.where(eligible, 0.0).fillna(0.0)
        vols[name] = forecast["vol"]
    return pd.DataFrame(scores), pd.DataFrame(vols)


def _cap_weights(raw: np.ndarray, max_weight: float) -> np.ndarray:
    """Scale to 1, then cap. Leftover weight stays unallocated."""
    total = float(raw.sum())
    if total <= 0:
        return np.zeros_like(raw)
    weights = raw / total
    for _ in range(10):
        over = weights > max_weight + 1e-12
        if not over.any():
            break
        excess = float((weights[over] - max_weight).sum())
        weights[over] = max_weight
        under = ~over
        if under.any() and float(weights[under].sum()) > 0:
            weights[under] += excess * weights[under] / float(weights[under].sum())
        else:
            break
    return weights


def sleeve_weights(
    score: pd.DataFrame,
    vol: pd.DataFrame,
    rets: pd.DataFrame,
    n_assets: int = N_ASSETS,
    max_weight: float = MAX_SINGLE_WEIGHT,
    corr_window: int = CORR_WINDOW,
) -> pd.DataFrame:
    """Top ``n_assets`` names with a positive score. Weights sum to at most 1."""
    cols = list(score.columns)
    n, k = len(score), len(cols)
    scores = score.to_numpy(dtype=float)
    vols = vol.reindex(index=score.index, columns=cols).to_numpy(dtype=float)
    returns = rets.reindex(index=score.index, columns=cols).to_numpy(dtype=float)
    out = np.zeros((n, k), dtype=float)
    for t in range(n):
        eligible = np.flatnonzero(scores[t] > 0)
        if len(eligible) == 0:
            continue
        order = eligible[np.argsort(-scores[t, eligible])][:n_assets]
        start = max(0, t - corr_window + 1)
        window = returns[start : t + 1][:, order]
        finite = np.isfinite(window).all(axis=1)
        window = window[finite]
        raw = np.zeros(len(order), dtype=float)
        corr = np.eye(len(order))
        if len(order) > 1 and len(window) >= 20:
            with np.errstate(invalid="ignore", divide="ignore"):
                corr = np.corrcoef(window, rowvar=False)
            if not np.all(np.isfinite(corr)):
                corr = np.eye(len(order))
        for i, col in enumerate(order):
            others = [abs(corr[i, j]) for j in range(len(order)) if j != i]
            average = float(np.mean(others)) if others else 0.0
            penalty = float(np.clip(1.0 - average, 0.25, 1.0))
            raw[i] = (scores[t, col] / max(float(vols[t, col]), 1e-6)) * penalty
        capped = _cap_weights(raw, max_weight)
        out[t, order] = capped
    return pd.DataFrame(out, index=score.index, columns=cols)


def zscore(series: pd.Series, window: int = 126) -> pd.Series:
    mean = series.rolling(window, min_periods=63).mean()
    std = series.rolling(window, min_periods=63).std()
    return ((series - mean) / std.replace(0, np.nan)).clip(-3, 3)


def beta_regime(panel: pd.DataFrame) -> pd.DataFrame:
    """Three-ratio vote. Utilities leading the market counts as risk-off."""
    prices = panel.loc[:, list(REGIME)].dropna(how="all").ffill().dropna()
    score = (
        zscore(prices["XLY"] / prices["XLP"])
        + zscore(prices["RSP"] / prices["SPY"])
        - zscore(prices["XLU"] / prices["SPY"])
    ) / 3.0
    state = pd.Series("NEUTRAL", index=score.index)
    state = state.mask(score >= 0.50, "RISK_ON").mask(score <= -0.50, "RISK_OFF")
    scale = state.map(REGIME_SCALES).astype(float)
    return pd.DataFrame({"score": score, "state": state, "scale": scale})


def tema_positions(closes: dict[str, pd.Series]) -> pd.DataFrame:
    """OR-book position held on each bar. Already shifted one bar by ``execute``."""
    columns = {}
    params = frozen_params()
    for symbol, close in closes.items():
        built = build_signals(close, params)
        _, position = execute(built.entries, built.exits)
        columns[symbol] = position.astype(float)
    return pd.DataFrame(columns)


def combine_sleeves(
    sleeves: dict[str, pd.DataFrame],
    regime_scale: pd.Series,
    caps: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Sleeve caps, then the regime scale. Gross is capped at 1.

    The frame at t is known at the close of t. It does not yet earn t's return.
    """
    caps = SLEEVE_CAPS if caps is None else caps
    total = None
    for name, weights in sleeves.items():
        scaled = weights * float(caps.get(name, 1.0))
        total = scaled if total is None else total.add(scaled, fill_value=0.0)
    if total is None:
        raise ValueError("no sleeves")
    total = total.fillna(0.0)
    scale = regime_scale.reindex(total.index).ffill()
    scale = scale.fillna(REGIME_SCALES["NEUTRAL"])
    total = total.mul(scale, axis=0)
    gross = total.sum(axis=1)
    cap = (1.0 / gross).where(gross > 1.0, 1.0)
    return total.mul(cap, axis=0).clip(lower=0.0)


def execute_decision(decision: pd.DataFrame, tema: pd.DataFrame | None = None) -> pd.DataFrame:
    """Lag the sleeve decision one bar. The OR position is already lagged.

    ``tema`` is the position held while today's return is earned, so it is
    applied after the lag. Multiplying it first would delay the book a second day.
    """
    held = decision.shift(1).fillna(0.0)
    if tema is None:
        return held
    gate = tema.reindex(index=held.index, columns=held.columns).fillna(0.0)
    return held * gate


def net_returns(weights: pd.DataFrame, rets: pd.DataFrame, cost: float = COST) -> pd.Series:
    aligned = rets.reindex(index=weights.index, columns=weights.columns).fillna(0.0)
    gross = (weights * aligned).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1)
    turnover.iloc[0] = float(weights.iloc[0].abs().sum())
    net = gross - turnover * cost
    net.name = "net"
    return net


def equal_tema_weights(tema: pd.DataFrame) -> pd.DataFrame:
    """Same OR book on every name, equal dollars, no rank and no regime vote."""
    live = tema.fillna(0.0)
    return live.div(max(live.shape[1], 1))


def equal_hold_weights(index: pd.DatetimeIndex, columns: list[str]) -> pd.DataFrame:
    weight = 1.0 / max(len(columns), 1)
    return pd.DataFrame(weight, index=index, columns=columns)
