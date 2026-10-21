"""Frozen TEMA book versus train-only Boruta, grid search, and Optuna.

Yahoo adjusted daily closes. One shared calendar. One 60/40 cut. Costs on.
The printed table is the median across assets.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from boruta_v14.study import (
    ASSETS,
    DOWNLOAD_START,
    TRADING_START,
    align_closes,
    fetch_close,
    frozen_yearly,
    make_split,
    run_symbol,
    summarize,
)


def _bars(frame: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    methods = ["buy_hold", "frozen", "boruta", "grid", "optuna"]
    symbols = [s for s in frame["symbol"].unique()]
    fig, ax = plt.subplots(figsize=(12, 5.5))
    width = 0.15
    x = np.arange(len(symbols))
    colors = {
        "buy_hold": "#94a3b8",
        "frozen": "#0f766e",
        "boruta": "#0369a1",
        "grid": "#b45309",
        "optuna": "#be123c",
    }
    for i, method in enumerate(methods):
        chunk = frame[frame["method"] == method].set_index("symbol").reindex(symbols)
        ax.bar(x + (i - 2) * width, chunk["oos_sharpe"].to_numpy(), width=width, label=method, color=colors[method])
    ax.axhline(0, color="#334155", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(symbols)
    ax.set_ylabel("Out-of-sample Sharpe")
    ax.set_title("Same 60/40 cut. Search saw the training sample only.")
    ax.legend(ncol=5, frameon=False, fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="*", default=list(ASSETS))
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--out-dir", default="results")
    args = parser.parse_args()

    closes = {}
    for symbol in args.symbols:
        try:
            closes[symbol] = fetch_close(symbol, DOWNLOAD_START)
            print(f"fetched {symbol} {closes[symbol].index[0].date()} -> {closes[symbol].index[-1].date()} n={len(closes[symbol])}")
        except Exception as exc:
            print(f"SKIP {symbol}: {exc}")
    if len(closes) < 2:
        raise SystemExit("not enough assets downloaded")
    closes = align_closes(closes)
    index = next(iter(closes.values())).index
    split = make_split(index, TRADING_START)
    print(
        f"shared bars {index[0].date()} -> {index[-1].date()} n={len(index)}\n"
        f"IS  {split.is_start.date()} -> {split.is_end.date()}\n"
        f"OOS {split.oos_start.date()} -> {split.oos_end.date()}"
    )

    rows = []
    yearly = []
    for symbol, close in closes.items():
        print(f"\n=== {symbol} ===")
        try:
            asset_rows = run_symbol(close, split, n_trials=args.trials)
        except Exception as exc:
            print(f"FAIL {symbol}: {exc}")
            continue
        rows.extend(asset_rows)
        yearly.append(frozen_yearly(close, split))
        for row in asset_rows:
            print(
                f"  {row['method']:<10} IS {row['is_sharpe'] if row['is_sharpe'] is not None else float('nan'):6.2f}  "
                f"OOS {row['oos_sharpe']:6.2f}  DD {row['oos_dd']:7.1%}  "
                f"trades {row['oos_trades']:4}  vs BH {row['oos_minus_bh']:+5.2f}  {row['detail']}"
            )

    frame = pd.DataFrame(rows)
    summary = summarize(frame)
    years = pd.concat(yearly, ignore_index=True) if yearly else pd.DataFrame()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "by_asset.csv", index=False)
    summary.to_csv(out / "summary.csv", index=False)
    years.to_csv(out / "frozen_yearly.csv", index=False)
    _bars(frame, Path("/opt/cursor/artifacts/robust_oos_sharpe.png"))
    _bars(frame, out / "oos_sharpe.png")

    print("\nMEDIAN ACROSS ASSETS")
    print(summary.to_string(index=False))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
