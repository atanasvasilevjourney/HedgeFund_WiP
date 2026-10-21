"""OR_EVENT membership.

Each member emits entry and exit events. The book goes long when any entry
fires and flat when any exit fires. A bar that is both uses the entry, which
is the hand-written position loop in the triple-EMA notebook (buy is tested
first). Events are shifted one bar at execution time, same as ``main.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from boruta_v14.indicators import kama, resolve_stc_preset, smooth_series, stc


@dataclass(frozen=True)
class TemaParams:
    w1: int = 7
    w2: int = 137
    w3: int = 100
    kind: str = "tema"


@dataclass(frozen=True)
class StcParams:
    fast: int = 23
    slow: int = 50
    preset: str = "a"
    low: int = 25
    high: int = 80


@dataclass(frozen=True)
class DoubleKamaParams:
    """Parameter-free on the panel: the chart prints ``DOUBLE_KAMA`` with no tuple.

    ``cross`` is a fast Kaufman MA (10, 2, 30) against the same constants on a
    doubled efficiency window (20, 2, 30). ``smooth`` is KAMA-of-KAMA at the
    notebook default (10, 2, 30). Both are fixed presets, not a per-ticker fit.
    """

    n_fast: int = 10
    n_slow: int = 20
    fast: int = 2
    slow: int = 30
    mode: str = "cross"


def crossed_above(a: pd.Series, b: pd.Series) -> pd.Series:
    prev_a = a.shift(1)
    prev_b = b.shift(1)
    return ((a > b) & (prev_a <= prev_b)).fillna(False)


def crossed_below(a: pd.Series, b: pd.Series) -> pd.Series:
    prev_a = a.shift(1)
    prev_b = b.shift(1)
    return ((a < b) & (prev_a >= prev_b)).fillna(False)


def crossed_above_level(series: pd.Series, level: float) -> pd.Series:
    prev = series.shift(1)
    return ((series > level) & (prev <= level)).fillna(False)


def crossed_below_level(series: pd.Series, level: float) -> pd.Series:
    prev = series.shift(1)
    return ((series < level) & (prev >= level)).fillna(False)


def position_from_events(entries: pd.Series, exits: pd.Series) -> pd.Series:
    """Long/flat state. Entry wins when both are true on the same bar."""
    e = entries.fillna(False).to_numpy(dtype=bool)
    x = exits.fillna(False).to_numpy(dtype=bool)
    x = x & ~e
    pos = np.zeros(len(e), dtype=np.int8)
    state = 0
    event_idx = np.flatnonzero(e | x)
    if len(event_idx) == 0:
        return pd.Series(pos, index=entries.index, name="position")
    prev = 0
    for i in event_idx:
        pos[prev:i] = state
        state = 1 if e[i] else 0
        prev = i
    pos[prev:] = state
    return pd.Series(pos, index=entries.index, name="position")


def tema_frame(close: pd.Series, params: TemaParams) -> dict[str, pd.Series]:
    t1 = smooth_series(close, params.w1, params.kind)
    t2 = smooth_series(close, params.w2, params.kind)
    t3 = smooth_series(close, params.w3, params.kind)
    entries = crossed_above(t1, t2) | crossed_above(t1, t3) | crossed_above(t2, t3)
    exits = crossed_below(t1, t2) | crossed_below(t1, t3) | crossed_below(t2, t3)
    return {"entries": entries, "exits": exits, "t1": t1, "t2": t2, "t3": t3}


def stc_frame(close: pd.Series, params: StcParams) -> dict[str, pd.Series]:
    preset = resolve_stc_preset(params.preset)
    oscillator = stc(
        close,
        fast=params.fast,
        slow=params.slow,
        cycle=preset["cycle"],
        factor=preset["factor"],
    )
    entries = crossed_above_level(oscillator, params.low)
    exits = crossed_below_level(oscillator, params.high)
    return {"entries": entries, "exits": exits, "stc": oscillator}


def kama_frame(close: pd.Series, params: DoubleKamaParams) -> dict[str, pd.Series]:
    fast_ma = kama(close, params.n_fast, params.fast, params.slow)
    if params.mode == "smooth":
        slow_ma = kama(fast_ma, params.n_fast, params.fast, params.slow)
    elif params.mode == "cross":
        slow_ma = kama(close, params.n_slow, params.fast, params.slow)
    else:
        raise ValueError(f"unknown DOUBLE_KAMA mode {params.mode!r}")
    return {
        "entries": crossed_above(fast_ma, slow_ma),
        "exits": crossed_below(fast_ma, slow_ma),
        "kama_fast": fast_ma,
        "kama_slow": slow_ma,
    }


def or_events(frames: list[dict], index: pd.Index) -> tuple[pd.Series, pd.Series]:
    entries = pd.Series(False, index=index)
    exits = pd.Series(False, index=index)
    for frame in frames:
        entries = entries | frame["entries"].reindex(index).fillna(False).astype(bool)
        exits = exits | frame["exits"].reindex(index).fillna(False).astype(bool)
    return entries, exits


def params_line(tema: TemaParams, stc_params: StcParams) -> str:
    return (
        f"TEMA({tema.w1},{tema.w2},{tema.w3}) OR "
        f"STC_REGIME({stc_params.fast},{stc_params.slow},{stc_params.preset},"
        f"{stc_params.low},{stc_params.high}) OR DOUBLE_KAMA"
    )
