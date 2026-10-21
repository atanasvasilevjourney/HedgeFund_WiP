"""Train-only search, one out-of-sample cut, same clock on every asset.

The book is the frozen OR_EVENT stack: TEMA(7, 137, 100), STC preset ``a``,
and the fixed double KAMA. Three searches are allowed to touch the training
sample and nothing else.

* Boruta grades the three members on the training sample. A WEAK member is
  dropped. MED and STRONG stay. The grade is not a licence to retune lengths.
* Grid search is the triple-EMA notebook grid (step 3, 16,320 combos). It
  replaces only the three TEMA lengths. STC and KAMA stay on the published
  preset. The combo with the best training Sharpe is scored once out of sample.
  The printed (7, 137, 100) point is one cell of that same grid, so its
  training-Sharpe percentile is a real rank, not a story.
* Optuna (TPE, fixed seed, 50 trials) may move TEMA lengths, STC fast/slow/bands,
  and the two KAMA windows. The best training trial is scored once out of
  sample, and that number is set next to the median out-of-sample Sharpe of
  every completed trial. Selection does not see those out-of-sample numbers.

Costs are 0.001 fee plus 0.001 slippage per fill. A combo with fewer than two
trades per year on the training sample is discarded. Buy-and-hold pays the
same entry cost and is the benchmark. Adjusted Yahoo daily closes, one shared
calendar, one shared 60/40 cut after 2018-01-01.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from boruta_v14.backtest import window_stats
from boruta_v14.boruta import summarize_grades
from boruta_v14.grid import notebook_grid
from boruta_v14.indicators import tema
from boruta_v14.model import (
    ModelParams,
    build_signals,
    frozen_params,
    params_valid,
    replay,
)
from boruta_v14.signals import DoubleKamaParams, TemaParams, position_from_events

ASSETS = ("LLY", "SPY", "QQQ", "IWM", "AAPL", "MSFT", "AMZN", "JPM", "XOM", "GLD")
DOWNLOAD_START = "2014-01-01"
TRADING_START = "2018-01-01"
TRAIN_RATIO = 0.6
MIN_TRADES_PER_YEAR = 2.0
OPTUNA_TRIALS = 50
OPTUNA_SEED = 7
COST = 0.002  # fees 0.001 + slippage 0.001


@dataclass(frozen=True)
class Split:
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp

    @property
    def is_loc(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.is_start, self.is_end

    @property
    def oos_loc(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.oos_start, self.oos_end


def make_split(index: pd.DatetimeIndex, trading_start: str = TRADING_START, train_ratio: float = TRAIN_RATIO) -> Split:
    trade = index[index >= pd.Timestamp(trading_start)]
    if len(trade) < 252:
        raise ValueError(f"trading window has {len(trade)} bars")
    cut = int(len(trade) * train_ratio)
    cut = min(max(cut, 1), len(trade) - 1)
    return Split(
        is_start=pd.Timestamp(trade[0]),
        is_end=pd.Timestamp(trade[cut - 1]),
        oos_start=pd.Timestamp(trade[cut]),
        oos_end=pd.Timestamp(trade[-1]),
    )


def fetch_close(symbol: str, start: str = DOWNLOAD_START, end: str | None = None) -> pd.Series:
    import yfinance as yf

    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        raise RuntimeError(f"{symbol}: empty download")
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    if "Close" not in df.columns:
        raise RuntimeError(f"{symbol}: no Close column")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.astype(float).dropna()
    close = close[~close.index.duplicated(keep="last")].sort_index()
    if getattr(close.index, "tz", None) is not None:
        close.index = close.index.tz_localize(None)
    close.name = symbol
    return close


def align_closes(closes: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Inner-join the calendars so every asset is judged on the same days."""
    idx = None
    for series in closes.values():
        idx = series.index if idx is None else idx.intersection(series.index)
    if idx is None or len(idx) < 500:
        raise RuntimeError("shared calendar is too short")
    return {symbol: series.reindex(idx).astype(float) for symbol, series in closes.items()}


def _slice_bounds(index: pd.DatetimeIndex, start, end) -> tuple[int, int]:
    i0 = int(index.searchsorted(pd.Timestamp(start), side="left"))
    i1 = int(index.searchsorted(pd.Timestamp(end), side="right") - 1)
    if i1 < i0:
        raise ValueError("empty window")
    return i0, i1


def _cross(a: np.ndarray, b: np.ndarray, direction: int) -> np.ndarray:
    """direction +1 is cross above, -1 is cross below. NaN comparisons stay False."""
    out = np.zeros(len(a), dtype=bool)
    if direction > 0:
        hit = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
    else:
        hit = (a[1:] < b[1:]) & (a[:-1] >= b[:-1])
    hit = np.where(np.isfinite(a[1:]) & np.isfinite(b[1:]) & np.isfinite(a[:-1]) & np.isfinite(b[:-1]), hit, False)
    out[1:] = hit
    return out


def tema_event_arrays(t1: np.ndarray, t2: np.ndarray, t3: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    entries = _cross(t1, t2, 1) | _cross(t1, t3, 1) | _cross(t2, t3, 1)
    exits = _cross(t1, t2, -1) | _cross(t1, t3, -1) | _cross(t2, t3, -1)
    return entries, exits


def score_window_np(
    prices: np.ndarray,
    entries: np.ndarray,
    exits: np.ndarray,
    i0: int,
    i1: int,
    cost: float = COST,
) -> tuple[float, float, int, float]:
    """Sharpe, max drawdown, closed trades, total return.

    Same rules as ``window_stats``: shift events one bar, rebuild the position
    from flat inside the slice, charge ``cost`` on each fill, Sharpe with
    sample std and 252 periods.
    """
    ent = np.zeros(i1 - i0 + 1, dtype=bool)
    ext = np.zeros(i1 - i0 + 1, dtype=bool)
    # Execution bar i sees the raw event from i-1. The event on i0-1 is in range
    # when the slice is not the first bar of the series.
    src0 = i0 - 1
    if src0 >= 0:
        ent[:] = entries[src0:i1]
        ext[:] = exits[src0:i1]
    else:
        ent[1:] = entries[i0:i1]
        ext[1:] = exits[i0:i1]
    ext = ext & ~ent
    n = ent.shape[0]
    pos = np.zeros(n, dtype=np.float64)
    state = 0.0
    hits = np.flatnonzero(ent | ext)
    prev = 0
    for i in hits:
        if i > prev:
            pos[prev:i] = state
        state = 1.0 if ent[i] else 0.0
        prev = int(i)
    pos[prev:] = state

    px = prices[i0 : i1 + 1]
    ret = np.zeros(n, dtype=np.float64)
    ret[1:] = px[1:] / px[:-1] - 1.0
    turn = np.empty(n, dtype=np.float64)
    turn[0] = pos[0]
    turn[1:] = np.abs(np.diff(pos))
    strat = pos * ret - turn * cost
    if n < 2:
        return 0.0, 0.0, 0, 0.0
    sd = float(np.std(strat, ddof=1))
    sharpe = 0.0 if sd == 0.0 or not np.isfinite(sd) else float(np.mean(strat) / sd * np.sqrt(252.0))
    equity = np.cumprod(1.0 + strat)
    peak = np.maximum.accumulate(equity)
    dd = float(np.min(equity / peak - 1.0))
    trades = int(np.sum((pos[1:] == 0.0) & (pos[:-1] == 1.0)))
    total = float(equity[-1] - 1.0)
    return sharpe, dd, trades, total


def _years(i0: int, i1: int) -> float:
    return max((i1 - i0 + 1) / 252.0, 1e-9)


@dataclass
class GridOutcome:
    best: tuple[int, int, int] | None
    best_is: float
    best_oos_fast: float
    frozen_is: float
    frozen_percentile: float
    n_valid: int
    n_tested: int
    median_oos: float
    frac_oos_positive: float


def grid_search_tema_lengths(
    close: pd.Series,
    base_entries: np.ndarray,
    base_exits: np.ndarray,
    split: Split,
    combos: list[tuple[int, int, int]] | None = None,
    cost: float = COST,
    min_trades_per_year: float = MIN_TRADES_PER_YEAR,
    frozen: tuple[int, int, int] = (7, 137, 100),
) -> GridOutcome:
    """Maximize training Sharpe over TEMA lengths. STC/KAMA events stay fixed."""
    combos = combos if combos is not None else notebook_grid()
    prices = close.to_numpy(dtype=float)
    periods = sorted({p for combo in combos for p in combo})
    cache = {n: tema(prices, n) for n in periods}
    i0, i1 = _slice_bounds(close.index, split.is_start, split.is_end)
    j0, j1 = _slice_bounds(close.index, split.oos_start, split.oos_end)
    is_years = _years(i0, i1)
    best = None
    best_is = -np.inf
    best_oos = float("nan")
    frozen_is = float("nan")
    valid_is: list[float] = []
    valid_oos: list[float] = []
    for w1, w2, w3 in combos:
        ent, ext = tema_event_arrays(cache[w1], cache[w2], cache[w3])
        ent = ent | base_entries
        ext = ext | base_exits
        is_sh, _, is_tr, _ = score_window_np(prices, ent, ext, i0, i1, cost)
        if is_tr / is_years < min_trades_per_year or not np.isfinite(is_sh):
            continue
        oos_sh, _, _, _ = score_window_np(prices, ent, ext, j0, j1, cost)
        valid_is.append(is_sh)
        valid_oos.append(oos_sh)
        if (w1, w2, w3) == frozen:
            frozen_is = is_sh
        if is_sh > best_is:
            best_is = is_sh
            best_oos = oos_sh
            best = (w1, w2, w3)
    if not valid_is or best is None:
        return GridOutcome(None, float("nan"), float("nan"), frozen_is, float("nan"), 0, len(combos), float("nan"), float("nan"))
    if np.isfinite(frozen_is):
        percentile = float(np.mean(np.asarray(valid_is) <= frozen_is))
    else:
        percentile = float("nan")
    oos_arr = np.asarray(valid_oos, dtype=float)
    return GridOutcome(
        best=best,
        best_is=float(best_is),
        best_oos_fast=float(best_oos),
        frozen_is=float(frozen_is) if np.isfinite(frozen_is) else float("nan"),
        frozen_percentile=percentile,
        n_valid=len(valid_is),
        n_tested=len(combos),
        median_oos=float(np.nanmedian(oos_arr)),
        frac_oos_positive=float(np.mean(oos_arr > 0)),
    )


def _stats_row(method: str, symbol: str, stats, bh_oos: float, detail: str, is_stats=None) -> dict:
    return {
        "symbol": symbol,
        "method": method,
        "is_sharpe": None if is_stats is None else is_stats.sharpe,
        "is_trades": None if is_stats is None else is_stats.trades,
        "oos_sharpe": stats.sharpe,
        "oos_return": stats.total_return,
        "oos_dd": stats.max_dd,
        "oos_trades": stats.trades,
        "bh_oos_sharpe": bh_oos,
        "oos_minus_bh": stats.sharpe - bh_oos,
        "detail": detail,
    }


def equity_path(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    start,
    end,
    fees: float = 0.001,
    slippage: float = 0.001,
) -> pd.Series:
    """Growth of $1. The position is rebuilt flat at ``start`` and carried to ``end``.

    Same fills, costs, and first-bar return as ``window_stats``, so the last
    point minus one equals that function's total return.
    """
    ent_exec, _ = execute_path(entries, exits)
    ext_exec = exits.shift(1)
    ext_exec = pd.Series(np.where(ext_exec.isna(), False, ext_exec), index=exits.index, dtype=bool)
    sl = close.loc[start:end]
    ent = ent_exec.reindex(sl.index).fillna(False).astype(bool)
    ext = ext_exec.reindex(sl.index).fillna(False).astype(bool)
    pos = position_from_events(ent, ext).astype(float)
    ret = sl.pct_change().fillna(0.0)
    turnover = pos.diff().abs()
    turnover.iloc[0] = float(pos.iloc[0])
    equity = (1.0 + pos * ret - turnover * (fees + slippage)).cumprod()
    equity.name = "equity"
    return equity


def execute_path(entries: pd.Series, exits: pd.Series):
    from boruta_v14.backtest import execute

    return execute(entries, exits)


def _hold_stats(close: pd.Series, start, end):
    """Buy and hold across the window, one entry cost, no exit."""
    loc = int(close.index.searchsorted(pd.Timestamp(start), side="left"))
    entries = pd.Series(False, index=close.index)
    exits = pd.Series(False, index=close.index)
    entries.iloc[max(loc - 1, 0)] = True
    return window_stats(close, entries, exits, start, end, fees=0.001, slippage=0.001)


def _book_stats(close: pd.Series, params: ModelParams, split: Split, members: tuple[str, ...]):
    built = build_signals(close, params, members)
    is_stats = window_stats(close, built.entries, built.exits, split.is_start, split.is_end, 0.001, 0.001)
    oos_stats = window_stats(close, built.entries, built.exits, split.oos_start, split.oos_end, 0.001, 0.001)
    return is_stats, oos_stats


def optuna_search(close: pd.Series, split: Split, n_trials: int = OPTUNA_TRIALS, seed: int = OPTUNA_SEED):
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    seen: list[ModelParams] = []

    def objective(trial: "optuna.Trial") -> float:
        tema = TemaParams(
            w1=trial.suggest_int("w1", 4, 18),
            w2=trial.suggest_int("w2", 60, 160),
            w3=trial.suggest_int("w3", 90, 190),
            kind="tema",
        )
        stc = replace(
            frozen_params().stc,
            fast=trial.suggest_int("stc_fast", 8, 30),
            slow=trial.suggest_int("stc_slow", 40, 80),
            low=trial.suggest_int("stc_low", 15, 35),
            high=trial.suggest_int("stc_high", 70, 90),
        )
        kama = DoubleKamaParams(
            n_fast=trial.suggest_int("n_fast", 6, 20),
            n_slow=trial.suggest_int("n_slow", 21, 70),
            fast=2,
            slow=30,
            mode="cross",
        )
        params = ModelParams(tema=tema, stc=stc, kama=kama)
        if not params_valid(params) or kama.n_slow <= kama.n_fast:
            return -999.0
        # Training window only. Out of sample is scored after the study returns.
        built = build_signals(close, params, ("TEMA", "STC_REGIME", "DOUBLE_KAMA"))
        is_stats = window_stats(close, built.entries, built.exits, split.is_start, split.is_end, 0.001, 0.001)
        years = max(len(close.loc[split.is_start : split.is_end]) / 252.0, 1e-9)
        if is_stats.trades / years < MIN_TRADES_PER_YEAR or not np.isfinite(is_stats.sharpe):
            return -999.0
        seen.append(params)
        return float(is_stats.sharpe)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    if study.best_value <= -100 or not seen:
        return None, float("nan"), []
    # The stored params are in trial order, not value order. Recover the winner
    # by rescoring is unnecessary: best_params is the argmax of the objective.
    bp = study.best_params
    winner = ModelParams(
        tema=TemaParams(bp["w1"], bp["w2"], bp["w3"], "tema"),
        stc=replace(
            frozen_params().stc,
            fast=bp["stc_fast"],
            slow=bp["stc_slow"],
            low=bp["stc_low"],
            high=bp["stc_high"],
        ),
        kama=DoubleKamaParams(bp["n_fast"], bp["n_slow"], 2, 30, "cross"),
    )
    return winner, float(study.best_value), seen


def frozen_yearly(close: pd.Series, split: Split) -> pd.DataFrame:
    """Calendar-year compound return of the frozen book, costs included."""
    built = build_signals(close, frozen_params())
    from boruta_v14.backtest import execute
    from boruta_v14.signals import position_from_events

    ent, _ = execute(built.entries, built.exits)
    ext = built.exits.shift(1).fillna(False).astype(bool)
    view = close.loc[split.is_start : split.oos_end]
    pos = position_from_events(ent.reindex(view.index).fillna(False).astype(bool), ext.reindex(view.index).fillna(False).astype(bool))
    ret = view.pct_change().fillna(0.0)
    turn = pos.astype(float).diff().abs()
    turn.iloc[0] = float(pos.iloc[0])
    strat = pos.astype(float) * ret - turn * COST
    rows = []
    for year, chunk in strat.groupby(strat.index.year):
        compound = float((1.0 + chunk).prod() - 1.0)
        end = chunk.index[-1]
        if end < split.oos_start:
            regime = "IS"
        elif chunk.index[0] >= split.oos_start:
            regime = "OOS"
        else:
            regime = "split"
        rows.append({"symbol": close.name, "year": int(year), "regime": regime, "return": compound, "bars": int(len(chunk))})
    return pd.DataFrame(rows)


def run_symbol(close: pd.Series, split: Split, n_trials: int = OPTUNA_TRIALS) -> list[dict]:
    symbol = str(close.name)
    bh_is = _hold_stats(close, split.is_start, split.is_end)
    bh_oos = _hold_stats(close, split.oos_start, split.oos_end)
    rows = [
        _stats_row("buy_hold", symbol, bh_oos, bh_oos.sharpe, "adjusted close, one entry cost", bh_is)
    ]

    frozen = replay(
        close,
        frozen_params(),
        trading_start=str(split.is_start.date()),
        run_boruta=True,
        run_sensitivity=False,
    )
    # replay() applies train_ratio itself. Force the study split by rescoring.
    is_stats, oos_stats = _book_stats(close, frozen_params(), split, ("TEMA", "STC_REGIME", "DOUBLE_KAMA"))
    grade = frozen.boruta_label
    members = frozen.member_grades
    rows.append(
        _stats_row(
            "frozen",
            symbol,
            oos_stats,
            bh_oos.sharpe,
            f"TEMA(7,137,100) grades {members}",
            is_stats,
        )
    )
    kept = tuple(name for name, g in members.items() if g != "WEAK")
    if not kept:
        rows.append(_stats_row("boruta", symbol, _flat(), bh_oos.sharpe, f"all WEAK ({grade})", _flat()))
    else:
        b_is, b_oos = _book_stats(close, frozen_params(), split, kept)
        rows.append(
            _stats_row(
                "boruta",
                symbol,
                b_oos,
                bh_oos.sharpe,
                f"kept {','.join(kept)} label {summarize_grades(members)}",
                b_is,
            )
        )

    base = build_signals(close, frozen_params(), ("STC_REGIME", "DOUBLE_KAMA"))
    grid = grid_search_tema_lengths(
        close,
        base.entries.to_numpy(dtype=bool),
        base.exits.to_numpy(dtype=bool),
        split,
    )
    if grid.best is None:
        rows.append(_stats_row("grid", symbol, _flat(), bh_oos.sharpe, "no combo passed the trade filter", _flat()))
    else:
        w1, w2, w3 = grid.best
        params = replace(frozen_params(), tema=TemaParams(w1, w2, w3, "tema"))
        g_is, g_oos = _book_stats(close, params, split, ("TEMA", "STC_REGIME", "DOUBLE_KAMA"))
        pct = "n/a" if not np.isfinite(grid.frozen_percentile) else f"{grid.frozen_percentile:.0%}"
        rows.append(
            _stats_row(
                "grid",
                symbol,
                g_oos,
                bh_oos.sharpe,
                (
                    f"IS-best TEMA({w1},{w2},{w3}) of {grid.n_valid}/{grid.n_tested}; "
                    f"frozen IS percentile {pct}; "
                    f"median OOS of valid grid {grid.median_oos:.2f}; "
                    f"frac OOS>0 {grid.frac_oos_positive:.0%}"
                ),
                g_is,
            )
        )

    winner, best_is, seen = optuna_search(close, split, n_trials=n_trials)
    if winner is None:
        rows.append(_stats_row("optuna", symbol, _flat(), bh_oos.sharpe, "no valid trial", _flat()))
    else:
        o_is, o_oos = _book_stats(close, winner, split, ("TEMA", "STC_REGIME", "DOUBLE_KAMA"))
        trial_oos = []
        for params in seen:
            _, trial_stats = _book_stats(close, params, split, ("TEMA", "STC_REGIME", "DOUBLE_KAMA"))
            trial_oos.append(trial_stats.sharpe)
        med = float(np.median(trial_oos)) if trial_oos else float("nan")
        t = winner.tema
        s = winner.stc
        k = winner.kama
        rows.append(
            _stats_row(
                "optuna",
                symbol,
                o_oos,
                bh_oos.sharpe,
                (
                    f"TEMA({t.w1},{t.w2},{t.w3}) STC({s.fast},{s.slow},{s.low},{s.high}) "
                    f"KAMA({k.n_fast},{k.n_slow}); trials {len(seen)}; "
                    f"IS {best_is:.2f}; median trial OOS {med:.2f}"
                ),
                o_is,
            )
        )
    return rows


def _flat():
    from boruta_v14.backtest import WindowStats

    return WindowStats(0.0, 0.0, 0.0, 0, ())


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    """Median across assets. The median is the result. The best asset is not."""
    rows = []
    for method, chunk in frame.groupby("method"):
        rows.append(
            {
                "method": method,
                "n": int(len(chunk)),
                "median_is_sharpe": float(chunk["is_sharpe"].median()),
                "median_oos_sharpe": float(chunk["oos_sharpe"].median()),
                "median_oos_dd": float(chunk["oos_dd"].median()),
                "median_oos_trades": float(chunk["oos_trades"].median()),
                "median_oos_minus_bh": float(chunk["oos_minus_bh"].median()),
                "n_oos_sharpe_pos": int((chunk["oos_sharpe"] > 0).sum()),
                "n_beat_bh": int((chunk["oos_minus_bh"] > 0).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("method").reset_index(drop=True)
