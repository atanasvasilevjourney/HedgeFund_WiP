"""Long-only close-to-close backtest.

Execution matches ``TEMACD-master/main.py``: raw events are shifted one bar,
then the position is rebuilt from flat inside the evaluation window. Costs
are the config pair (fees 0.001 and slippage 0.001) charged on each fill.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from boruta_v14.signals import position_from_events


@dataclass(frozen=True)
class WindowStats:
    sharpe: float
    total_return: float
    max_dd: float
    trades: int
    point_pnls: tuple[float, ...]

    @property
    def equity_end(self) -> float:
        return 1.0 + self.total_return


def _sharpe(returns: pd.Series, periods: int = 252) -> float:
    r = returns.to_numpy(dtype=float)
    if len(r) < 2:
        return 0.0
    sd = float(np.std(r, ddof=1))
    if not np.isfinite(sd) or sd == 0.0:
        return 0.0
    return float(np.mean(r) / sd * np.sqrt(periods))


def _max_dd(returns: pd.Series) -> float:
    equity = (1.0 + returns).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    if dd.empty:
        return 0.0
    return float(dd.min())


def _closed_points(close: pd.Series, position: pd.Series) -> tuple[float, ...]:
    px = close.to_numpy(dtype=float)
    pos = position.to_numpy(dtype=int)
    pnls: list[float] = []
    entry_i = None
    prev = 0
    for i, cur in enumerate(pos):
        if prev == 0 and cur == 1:
            entry_i = i
        elif prev == 1 and cur == 0 and entry_i is not None:
            pnls.append(float(px[i] - px[entry_i]))
            entry_i = None
        prev = int(cur)
    return tuple(pnls)


def execute(entries: pd.Series, exits: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Shift events by one bar, then build the long/flat position."""
    ent = entries.shift(1)
    ext = exits.shift(1)
    ent = pd.Series(np.where(ent.isna(), False, ent), index=entries.index, dtype=bool)
    ext = pd.Series(np.where(ext.isna(), False, ext), index=exits.index, dtype=bool)
    return ent, position_from_events(ent, ext)


def window_stats(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    start,
    end,
    fees: float = 0.001,
    slippage: float = 0.001,
) -> WindowStats:
    """Stats for ``start:end`` inclusive, position rebuilt from flat in-window.

    ``entries`` / ``exits`` are the raw (unshifted) member events.
    """
    ent_exec, _ = execute(entries, exits)
    ext_exec = exits.shift(1)
    ext_exec = pd.Series(np.where(ext_exec.isna(), False, ext_exec), index=exits.index, dtype=bool)

    sl = close.loc[start:end]
    if sl.empty:
        return WindowStats(0.0, 0.0, 0.0, 0, ())
    ent = ent_exec.reindex(sl.index).fillna(False).astype(bool)
    ext = ext_exec.reindex(sl.index).fillna(False).astype(bool)
    pos = position_from_events(ent, ext)
    ret = sl.pct_change().fillna(0.0)
    turnover = pos.astype(float).diff().abs()
    turnover.iloc[0] = float(pos.iloc[0])
    cost = fees + slippage
    strat = pos.astype(float) * ret - turnover * cost
    points = _closed_points(sl, pos)
    total = float((1.0 + strat).prod() - 1.0)
    return WindowStats(
        sharpe=_sharpe(strat),
        total_return=total,
        max_dd=_max_dd(strat),
        trades=len(points),
        point_pnls=points,
    )
