"""Replay the frozen LLY BORUTA v1.4 card, and score the readings that the panel leaves implicit.

The published card fixes TEMA(7, 137, 100), STC fast/slow/bands, preset "a",
and a parameter-free DOUBLE_KAMA. What it does not print is whether TEMA is
the TA-Lib triple EMA or the notebook's single EMA, which DOUBLE_KAMA preset
is in the OR, and whether STC events are the 25/80 band crosses. ``--fit``
tries those readings on LLY through the run date and ranks them by distance
to the printed in-sample Sharpe, out-of-sample Sharpe, drawdown, and trade count.

Nothing here refits the frozen lengths. The grid search that produced
(7, 137, 100) already happened; this script only replays it.
"""

from __future__ import annotations

import argparse
import pandas as pd

from boruta_v14.model import PUBLISHED, ModelParams, Replay, format_panel, frozen_params, replay
from boruta_v14.plot import plot_replay
from boruta_v14.signals import DoubleKamaParams, TemaParams

RUN_END = "2024-10-14"  # yfinance end is exclusive; the card is run 20241013
DOWNLOAD_START = "2014-01-01"
TRADING_START = "2018-01-01"


def fetch_lly(end: str = RUN_END) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download("LLY", start=DOWNLOAD_START, end=end, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    if df.empty or "Close" not in df.columns:
        raise RuntimeError("LLY download returned no Close column")
    return df


def _distance(result: Replay) -> float:
    trade_gap = abs(result.oos_stats.trades - PUBLISHED["oos_trades"]) / PUBLISHED["oos_trades"]
    sharpe_gap = abs(result.is_stats.sharpe - PUBLISHED["is_sharpe"]) + abs(
        result.oos_stats.sharpe - PUBLISHED["oos_sharpe"]
    )
    dd_gap = abs(result.oos_stats.max_dd - PUBLISHED["oos_dd"])
    return 3.0 * trade_gap + sharpe_gap + dd_gap


def fit_implicit(close: pd.Series) -> list[tuple[float, str, Replay]]:
    """Rank the panel slots the screenshot does not spell out."""
    rows = []
    kama_presets = {
        "cross_10_20": DoubleKamaParams(mode="cross", n_fast=10, n_slow=20),
        "smooth_10": DoubleKamaParams(mode="smooth", n_fast=10, n_slow=10),
        "cross_10_30": DoubleKamaParams(mode="cross", n_fast=10, n_slow=30),
    }
    for kind in ("tema", "ema"):
        for name, kama in kama_presets.items():
            params = ModelParams(tema=TemaParams(kind=kind), kama=kama)
            result = replay(
                close,
                params,
                trading_start=TRADING_START,
                run_boruta=False,
                run_sensitivity=False,
            )
            label = f"kind={kind} kama={name}"
            rows.append((_distance(result), label, result))
    rows.sort(key=lambda row: row[0])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay LLY BORUTA v1.4")
    parser.add_argument("--fit", action="store_true", help="rank implicit TEMA/KAMA readings")
    parser.add_argument("--end", default=RUN_END)
    parser.add_argument(
        "--out",
        default="/opt/cursor/artifacts/lly_boruta_v14.png",
    )
    args = parser.parse_args()

    print(format_panel(None))
    print()
    frame = fetch_lly(args.end)
    close = frame["Close"].astype(float)
    print(f"LLY bars {close.index[0].date()} -> {close.index[-1].date()}  n={len(close)}")

    params = frozen_params()
    if args.fit:
        ranked = fit_implicit(close)
        print("\nImplicit-slot fit (lower distance is closer to the printed card)")
        for dist, label, result in ranked[:6]:
            print(
                f"  {dist:6.3f}  {label:28s}  "
                f"IS {result.is_stats.sharpe:6.3f}  "
                f"OOS {result.oos_stats.sharpe:6.3f}  "
                f"DD {result.oos_stats.max_dd:7.2%}  "
                f"trades {result.oos_stats.trades:3d}"
            )
    result = replay(close, params, trading_start=TRADING_START)
    print()
    print(format_panel(result))
    out = plot_replay(close, result, args.out, ohlc=frame)
    print(f"\nchart {out}")


if __name__ == "__main__":
    main()
