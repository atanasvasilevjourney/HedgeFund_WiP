"""Triple-EMA / TEMA grids that contain the frozen point (7, 137, 100).

The notebook grid (step 3) is the one that was actually enumerated:

    ema1 = range(4, 40, 3)     # includes 7
    ema2 = range(80, 200, 3)   # includes 137
    ema3 = range(100, 200, 3)  # includes 100
    keep if ema1 < ema2 and ema1 < ema3

``TEMACD-master/config/strategy_config.yaml`` is the step-1 official grid.
``np.arange`` stops are exclusive, and TEMA also requires ``w2 > w1 + 10``.
(7, 137, 100) sits on both grids. Search ranks by in-sample Sharpe and
drops combos with fewer than 2 trades per year, same as the notebook.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from boruta_v14.backtest import window_stats
from boruta_v14.signals import TemaParams, tema_frame


def notebook_grid() -> list[tuple[int, int, int]]:
    ema1 = range(4, 40, 3)
    ema2 = range(80, 200, 3)
    ema3 = range(100, 200, 3)
    return [
        (w1, w2, w3)
        for w1 in ema1
        for w2 in ema2
        for w3 in ema3
        if w1 < w2 and w1 < w3 and w2 != w3
    ]


def on_notebook_grid(w1: int, w2: int, w3: int) -> bool:
    ema1 = set(range(4, 40, 3))
    ema2 = set(range(80, 200, 3))
    ema3 = set(range(100, 200, 3))
    return w1 in ema1 and w2 in ema2 and w3 in ema3 and w1 < w2 and w1 < w3 and w2 != w3


def on_package_grid(w1: int, w2: int, w3: int) -> bool:
    """YAML ranges plus the TEMAStrategy gap rule. ``stop`` is exclusive."""
    in_range = (4 <= w1 < 50) and (50 <= w2 < 150) and (100 <= w3 < 200)
    return in_range and (w2 > w1 + 10) and w3 != w1 and w3 != w2


def grid_search_tema(
    close: pd.Series,
    combos: list[tuple[int, int, int]],
    kind: str = "tema",
    min_trades_per_year: float = 2.0,
    fees: float = 0.001,
    slippage: float = 0.001,
) -> tuple[tuple[int, int, int] | None, float]:
    """Maximize in-sample Sharpe on ``close``. The whole series is the train window.

    Returns ``(best_combo, best_sharpe)``. ``best_combo`` is None when every
    combo fails the trade-count filter.
    """
    best: tuple[int, int, int] | None = None
    best_sharpe = -np.inf
    if close.empty:
        return None, float("nan")
    years = max(len(close) / 252.0, 1e-9)
    start = close.index[0]
    end = close.index[-1]
    for w1, w2, w3 in combos:
        frame = tema_frame(close, TemaParams(w1, w2, w3, kind))
        stats = window_stats(
            close, frame["entries"], frame["exits"], start, end, fees=fees, slippage=slippage
        )
        if stats.trades / years < min_trades_per_year:
            continue
        if stats.sharpe > best_sharpe:
            best_sharpe = stats.sharpe
            best = (w1, w2, w3)
    if best is None:
        return None, float("nan")
    return best, float(best_sharpe)
