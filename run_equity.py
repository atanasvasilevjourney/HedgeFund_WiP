"""Dollar equity of the frozen TEMA book versus buy-and-hold.

One path from the training start through the latest bar. The position is
carried across the test date. $100,000 notional per asset. The equal-weight
book puts $10,000 in each name and rebalances the return streams daily.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from boruta_v14.model import build_signals, frozen_params
from boruta_v14.study import ASSETS, DOWNLOAD_START, TRADING_START, align_closes, equity_path, fetch_close, make_split

NOTIONAL = 100_000.0


def _daily_return(equity: pd.Series) -> pd.Series:
    """Return stream whose compound equals the equity path, including day-one cost."""
    ret = equity.pct_change()
    ret.iloc[0] = float(equity.iloc[0] - 1.0)
    return ret.fillna(0.0)


def hold_events(close: pd.Series, start) -> tuple[pd.Series, pd.Series]:
    loc = int(close.index.searchsorted(pd.Timestamp(start), side="left"))
    entries = pd.Series(False, index=close.index)
    exits = pd.Series(False, index=close.index)
    entries.iloc[max(loc - 1, 0)] = True
    return entries, exits


def _pnl_row(symbol: str, book: pd.Series, hold: pd.Series, split) -> dict:
    oos = book.index[book.index >= split.oos_start]
    book_at_test = float(book.loc[: split.is_end].iloc[-1])
    hold_at_test = float(hold.loc[: split.is_end].iloc[-1])
    book_end = float(book.iloc[-1])
    hold_end = float(hold.iloc[-1])
    book_dd = float((book / book.cummax() - 1.0).min())
    hold_dd = float((hold / hold.cummax() - 1.0).min())
    return {
        "symbol": symbol,
        "start": NOTIONAL,
        "book_end": NOTIONAL * book_end,
        "hold_end": NOTIONAL * hold_end,
        "book_pnl": NOTIONAL * (book_end - 1.0),
        "hold_pnl": NOTIONAL * (hold_end - 1.0),
        "book_test_pnl": NOTIONAL * book_at_test * (book_end / book_at_test - 1.0),
        "hold_test_pnl": NOTIONAL * hold_at_test * (hold_end / hold_at_test - 1.0),
        "book_max_dd": book_dd,
        "hold_max_dd": hold_dd,
        "test_start_equity_book": NOTIONAL * book_at_test,
        "bars": int(len(book)),
        "oos_bars": int(len(oos)),
    }


def _month_end(equity: pd.Series) -> pd.Series:
    return equity.resample("ME").last().dropna()


def plot_portfolio(book: pd.Series, hold: pd.Series, split, path: Path) -> None:
    dollars_b = book * NOTIONAL
    dollars_h = hold * NOTIONAL
    fig, axes = plt.subplots(2, 1, figsize=(12, 7.2), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax, ax_dd = axes
    ax.plot(dollars_b.index, dollars_b.values, color="#0f766e", lw=1.8, label="Frozen TEMA book")
    ax.plot(dollars_h.index, dollars_h.values, color="#64748b", lw=1.4, label="Buy and hold")
    ax.axvline(split.oos_start, color="#b45309", lw=1.0, ls="--", label="Test start")
    ax.axhline(NOTIONAL, color="#cbd5e1", lw=0.8)
    ax.set_ylabel("Equity ($)")
    ax.set_title("Equal-weight book, $100,000 start, daily Yahoo closes")
    b_pnl = dollars_b.iloc[-1] - NOTIONAL
    h_pnl = dollars_h.iloc[-1] - NOTIONAL
    ax.text(
        0.01,
        0.98,
        f"Book P&L {b_pnl:+,.0f}    Hold P&L {h_pnl:+,.0f}",
        transform=ax.transAxes,
        va="top",
        fontsize=10,
        color="#0f172a",
    )
    ax.legend(frameon=False, loc="lower right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    dd = dollars_b / dollars_b.cummax() - 1.0
    ax_dd.fill_between(dd.index, dd.values, 0, color="#0f766e", alpha=0.35)
    ax_dd.set_ylabel("Book drawdown")
    ax_dd.spines["top"].set_visible(False)
    ax_dd.spines["right"].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_assets(curves: dict[str, tuple[pd.Series, pd.Series]], rows: pd.DataFrame, split, path: Path) -> None:
    symbols = list(curves)
    fig, axes = plt.subplots(2, 5, figsize=(16, 7.2), sharex=True)
    for ax, symbol in zip(axes.ravel(), symbols):
        book, hold = curves[symbol]
        ax.plot(book.index, book.values * NOTIONAL, color="#0f766e", lw=1.2, label="Book")
        ax.plot(hold.index, hold.values * NOTIONAL, color="#64748b", lw=1.0, label="Hold")
        ax.axvline(split.oos_start, color="#b45309", lw=0.7, ls="--")
        rec = rows.set_index("symbol").loc[symbol]
        ax.set_title(f"{symbol}   book {rec.book_pnl:+,.0f}", fontsize=9)
        ax.tick_params(labelsize=7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.suptitle("$100,000 per asset. Teal is the frozen book, gray is holding the asset.", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    closes = align_closes({symbol: fetch_close(symbol, DOWNLOAD_START) for symbol in ASSETS})
    index = next(iter(closes.values())).index
    split = make_split(index, TRADING_START)
    curves = {}
    rows = []
    book_rets = []
    hold_rets = []
    for symbol, close in closes.items():
        built = build_signals(close, frozen_params())
        book = equity_path(close, built.entries, built.exits, split.is_start, split.oos_end)
        h_ent, h_ext = hold_events(close, split.is_start)
        hold = equity_path(close, h_ent, h_ext, split.is_start, split.oos_end)
        curves[symbol] = (book, hold)
        rows.append(_pnl_row(symbol, book, hold, split))
        book_rets.append(_daily_return(book))
        hold_rets.append(_daily_return(hold))
        print(f"{symbol} book {rows[-1]['book_pnl']:+,.0f} hold {rows[-1]['hold_pnl']:+,.0f} test {rows[-1]['book_test_pnl']:+,.0f}")

    port_book = (1.0 + pd.concat(book_rets, axis=1).mean(axis=1)).cumprod()
    port_hold = (1.0 + pd.concat(hold_rets, axis=1).mean(axis=1)).cumprod()
    port_row = _pnl_row("EQUAL", port_book, port_hold, split)
    print(
        f"EQUAL book {port_row['book_pnl']:+,.0f} hold {port_row['hold_pnl']:+,.0f} "
        f"test book {port_row['book_test_pnl']:+,.0f} test hold {port_row['hold_test_pnl']:+,.0f}"
    )

    out = Path("results")
    out.mkdir(exist_ok=True)
    table = pd.DataFrame(rows)
    table.to_csv(out / "pnl.csv", index=False)
    plot_portfolio(port_book, port_hold, split, out / "equity_portfolio.png")
    plot_portfolio(port_book, port_hold, split, Path("/opt/cursor/artifacts/equity_portfolio.png"))
    plot_assets(curves, table, split, out / "equity_assets.png")
    plot_assets(curves, table, split, Path("/opt/cursor/artifacts/equity_assets.png"))

    months = _month_end(port_book).index
    payload = {
        "start": str(split.is_start.date()),
        "test": str(split.oos_start.date()),
        "end": str(split.oos_end.date()),
        "notional": NOTIONAL,
        "months": [ts.strftime("%Y-%m") for ts in months],
        "portfolio": {
            "book": [round(float(v) * NOTIONAL, 2) for v in _month_end(port_book).reindex(months).ffill()],
            "hold": [round(float(v) * NOTIONAL, 2) for v in _month_end(port_hold).reindex(months).ffill()],
        },
        "assets": {},
        "rows": rows,
        "portfolio_row": port_row,
    }
    for symbol, (book, hold) in curves.items():
        payload["assets"][symbol] = {
            "book": [round(float(v) * NOTIONAL, 2) for v in _month_end(book).reindex(months).ffill()],
            "hold": [round(float(v) * NOTIONAL, 2) for v in _month_end(hold).reindex(months).ffill()],
        }
    (out / "equity_monthly.json").write_text(json.dumps(payload))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
