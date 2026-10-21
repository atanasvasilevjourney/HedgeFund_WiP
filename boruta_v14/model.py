"""Frozen LLY BORUTA v1.4 model and the replay that grades it."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from boruta_v14.backtest import WindowStats, window_stats
from boruta_v14.boruta import (
    boruta_grades,
    grade_members,
    member_feature_frame,
    summarize_grades,
)
from boruta_v14.sensitivity import (
    HIGH_SHARPE,
    SENSITIVITY_KNOBS,
    SensitivityResult,
    format_sensitivity,
    neighbor_deltas,
)
from boruta_v14.signals import (
    DoubleKamaParams,
    StcParams,
    TemaParams,
    kama_frame,
    or_events,
    params_line,
    stc_frame,
    tema_frame,
)

# Numbers read off the LLY daily panel, run 20241013_153745.
PUBLISHED = {
    "name": "LLY - BORUTA v1.4",
    "badge": "PYTHON OFFICIAL",
    "logic": "OR_EVENT",
    "members": "TEMA / STC_REGIME / DOUBLE_KAMA",
    "model_src": "LLY (frozen)",
    "is_sharpe": 1.451,
    "oos_sharpe": 1.475,
    "oos_dd": -0.2109,
    "oos_trades": 23,
    "boruta": "MED / STRONG",
    "sensitivity": "MED (80/80 HIGH)",
    "timeframe": "1D",
    "run_id": "20241013_153745",
}


@dataclass(frozen=True)
class ModelParams:
    tema: TemaParams = TemaParams()
    stc: StcParams = StcParams()
    kama: DoubleKamaParams = DoubleKamaParams()
    fees: float = 0.001
    slippage: float = 0.001
    train_ratio: float = 0.6


def frozen_params() -> ModelParams:
    return ModelParams()


def params_valid(params: ModelParams) -> bool:
    tema, stc, kama = params.tema, params.stc, params.kama
    if min(tema.w1, tema.w2, tema.w3, stc.fast, stc.slow, kama.n_fast, kama.n_slow) < 2:
        return False
    if not (tema.w2 > tema.w1 + 10):
        return False
    if tema.w3 in (tema.w1, tema.w2):
        return False
    if stc.slow <= stc.fast or stc.low >= stc.high:
        return False
    if params.train_ratio <= 0.0 or params.train_ratio >= 1.0:
        return False
    return True


def with_knob(params: ModelParams, knob: str, value: int) -> ModelParams:
    if knob == "tema_w1":
        return replace(params, tema=replace(params.tema, w1=value))
    if knob == "tema_w2":
        return replace(params, tema=replace(params.tema, w2=value))
    if knob == "tema_w3":
        return replace(params, tema=replace(params.tema, w3=value))
    if knob == "stc_fast":
        return replace(params, stc=replace(params.stc, fast=value))
    if knob == "stc_slow":
        return replace(params, stc=replace(params.stc, slow=value))
    raise KeyError(knob)


def knob_value(params: ModelParams, knob: str) -> int:
    return {
        "tema_w1": params.tema.w1,
        "tema_w2": params.tema.w2,
        "tema_w3": params.tema.w3,
        "stc_fast": params.stc.fast,
        "stc_slow": params.stc.slow,
    }[knob]


@dataclass
class BuiltSignals:
    entries: pd.Series
    exits: pd.Series
    tema: dict[str, pd.Series]
    stc: dict[str, pd.Series]
    kama: dict[str, pd.Series]
    members: tuple[str, ...]


def build_signals(
    close: pd.Series,
    params: ModelParams = None,
    members: tuple[str, ...] = ("TEMA", "STC_REGIME", "DOUBLE_KAMA"),
) -> BuiltSignals:
    params = params or frozen_params()
    tema = tema_frame(close, params.tema)
    stc = stc_frame(close, params.stc)
    kama = kama_frame(close, params.kama)
    frames = []
    if "TEMA" in members:
        frames.append(tema)
    if "STC_REGIME" in members:
        frames.append(stc)
    if "DOUBLE_KAMA" in members:
        frames.append(kama)
    entries, exits = or_events(frames, close.index)
    return BuiltSignals(entries, exits, tema, stc, kama, tuple(members))


def trading_index(close: pd.Series, trading_start) -> pd.Index:
    if trading_start is None:
        return close.index
    start = pd.Timestamp(trading_start)
    return close.index[close.index >= start]


def split_bounds(index: pd.Index, train_ratio: float) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    if len(index) < 10:
        raise ValueError("need at least 10 bars in the trading window")
    cut = int(len(index) * train_ratio)
    cut = min(max(cut, 1), len(index) - 1)
    is_end = index[cut - 1]
    oos_start = index[cut]
    return index[0], is_end, oos_start


@dataclass
class Replay:
    params: ModelParams
    params_text: str
    is_stats: WindowStats
    oos_stats: WindowStats
    boruta_label: str
    member_grades: dict[str, str]
    feature_grades: dict[str, str]
    sensitivity: SensitivityResult
    signals: BuiltSignals
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp

    def panel(self) -> str:
        return format_panel(self)


def _boruta_on_is(close: pd.Series, built: BuiltSignals, is_start, is_end) -> tuple[str, dict, dict]:
    sl = close.loc[is_start:is_end]
    t1, t2, t3 = built.tema["t1"], built.tema["t2"], built.tema["t3"]
    tema_state = ((t1 > t2) & (t2 > t3)).astype(float)
    tema_spread = (t1 - t3) / close.replace(0, np.nan)
    stc_value = built.stc["stc"] / 100.0
    stc_state = (built.stc["stc"] > 25).astype(float)
    k_fast = built.kama["kama_fast"]
    k_slow = built.kama["kama_slow"]
    kama_state = (k_fast > k_slow).astype(float)
    kama_spread = (k_fast - k_slow) / close.replace(0, np.nan)
    frame = member_feature_frame(
        sl.index,
        tema_state.reindex(sl.index),
        tema_spread.reindex(sl.index),
        stc_state.reindex(sl.index),
        stc_value.reindex(sl.index),
        kama_state.reindex(sl.index),
        kama_spread.reindex(sl.index),
    )
    forward = close.shift(-5) / close - 1.0
    y = (forward.reindex(sl.index) > 0).astype(float)
    # Last 5 bars have no label. Keep them out.
    y.iloc[-5:] = np.nan
    grades = boruta_grades(frame, y)
    members = grade_members(grades)
    return summarize_grades(members), members, grades


def _sensitivity(close, params: ModelParams, is_start, is_end, base_sharpe: float) -> SensitivityResult:
    sharpes: list[float] = []
    deltas: list[float] = []
    for knob, delta in neighbor_deltas():
        value = knob_value(params, knob) + delta
        trial = with_knob(params, knob, value)
        if not params_valid(trial):
            continue
        built = build_signals(close, trial)
        stats = window_stats(
            close,
            built.entries,
            built.exits,
            is_start,
            is_end,
            fees=params.fees,
            slippage=params.slippage,
        )
        if not np.isfinite(stats.sharpe):
            continue
        sharpes.append(stats.sharpe)
        if not np.isfinite(base_sharpe) or base_sharpe == 0:
            deltas.append(0.0 if stats.sharpe == base_sharpe else np.inf)
        else:
            deltas.append((stats.sharpe - base_sharpe) / abs(base_sharpe) * 100.0)
    if not sharpes:
        return SensitivityResult("n/a", float("nan"), 0, 0, ())
    finite_drops = [d for d in deltas if np.isfinite(d)]
    worst_drop = max([0.0, *(-d for d in finite_drops)])
    n_high = sum(1 for s in sharpes if s >= HIGH_SHARPE)
    label = format_sensitivity(worst_drop, n_high, len(sharpes))
    return SensitivityResult(label, worst_drop, n_high, len(sharpes), tuple(sharpes))


def replay(
    close: pd.Series,
    params: ModelParams = None,
    trading_start=None,
    run_boruta: bool = True,
    run_sensitivity: bool = True,
    members: tuple[str, ...] = ("TEMA", "STC_REGIME", "DOUBLE_KAMA"),
) -> Replay:
    """Replay the frozen model. Indicators see the whole series; P&L starts at ``trading_start``."""
    params = params or frozen_params()
    if not params_valid(params):
        raise ValueError(f"invalid params: {params}")
    close = close.astype(float).copy()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    built = build_signals(close, params, members)
    index = trading_index(close, trading_start)
    is_start, is_end, oos_start = split_bounds(index, params.train_ratio)
    oos_end = index[-1]
    is_stats = window_stats(
        close, built.entries, built.exits, is_start, is_end, params.fees, params.slippage
    )
    oos_stats = window_stats(
        close, built.entries, built.exits, oos_start, oos_end, params.fees, params.slippage
    )
    if run_boruta:
        boruta_label, member_grades, feature_grades = _boruta_on_is(close, built, is_start, is_end)
    else:
        boruta_label, member_grades, feature_grades = "n/a", {}, {}
    if run_sensitivity:
        sens = _sensitivity(close, params, is_start, is_end, is_stats.sharpe)
    else:
        sens = SensitivityResult("n/a", float("nan"), 0, 0, ())
    return Replay(
        params=params,
        params_text=params_line(params.tema, params.stc),
        is_stats=is_stats,
        oos_stats=oos_stats,
        boruta_label=boruta_label,
        member_grades=member_grades,
        feature_grades=feature_grades,
        sensitivity=sens,
        signals=built,
        is_start=pd.Timestamp(is_start),
        is_end=pd.Timestamp(is_end),
        oos_start=pd.Timestamp(oos_start),
    )


def format_panel(result: Replay | None = None) -> str:
    """Published card from the screenshot, then the replay underneath it when given."""
    p = PUBLISHED
    lines = [
        f"{p['name']}",
        p["badge"],
        f"Logic          {p['logic']}",
        f"Members        {p['members']}",
        f"Params         {params_line(TemaParams(), StcParams())}",
        f"Model src      {p['model_src']}",
        f"IS Sharpe      {p['is_sharpe']:.3f}",
        f"OOS Sharpe     {p['oos_sharpe']:.3f}",
        f"OOS DD         {p['oos_dd']:.2%}",
        f"OOS Trades     {p['oos_trades']}",
        f"Boruta         {p['boruta']}",
        f"Sensitivity    {p['sensitivity']}",
        f"Timeframe      {p['timeframe']}",
        f"run            {p['run_id']}",
    ]
    if result is None:
        return "\n".join(lines)
    lines += [
        "",
        "REPLAY",
        f"Params         {result.params_text}",
        f"IS window      {result.is_start.date()} -> {result.is_end.date()}",
        f"OOS window     {result.oos_start.date()} -> end",
        f"IS Sharpe      {result.is_stats.sharpe:.3f}",
        f"OOS Sharpe     {result.oos_stats.sharpe:.3f}",
        f"OOS return     {result.oos_stats.total_return:.2%}",
        f"OOS DD         {result.oos_stats.max_dd:.2%}",
        f"OOS Trades     {result.oos_stats.trades}",
        f"Boruta         {result.boruta_label}",
        *[f"  {name:<12} {grade}" for name, grade in result.member_grades.items()],
        f"Sensitivity    {result.sensitivity.label}",
    ]
    return "\n".join(lines)


class FrozenModel:
    """The LLY card. ``replay`` does not refit the three lengths."""

    def __init__(self, params: ModelParams = None):
        self.params = params or frozen_params()

    def replay(self, close: pd.Series, trading_start="2018-01-01", **kwargs) -> Replay:
        return replay(close, self.params, trading_start=trading_start, **kwargs)

    def panel(self) -> str:
        return format_panel(None)
