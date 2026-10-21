"""Dollar book: frozen OR gate on the beta-rotation leaders.

Sleeves are the Carver equity buckets (indices and stocks). The regime vote
uses XLY/XLP, RSP/SPY, and XLU/SPY. Crypto stays out: the OR book was built
for equity daily bars, and the sleeves are not mixed.

Four books, one $100,000 start, one cost (0.002 per unit of turnover):

* hold — equal weight in every sleeve name
* rotation — top names, regime scale, no OR gate
* tema_leaders — that same book, held only while each name's OR book is long
* tema_equal — the OR book on every name, equal weight, no rank and no vote

The rank is recomputed every day from trailing data. The test sample is not
used to choose names or parameters.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from boruta_v14.rotation import (
    ANN_DAYS,
    COST,
    INDICES,
    REGIME,
    STOCKS,
    beta_regime,
    combine_sleeves,
    equal_hold_weights,
    equal_tema_weights,
    execute_decision,
    net_returns,
    score_panels,
    sleeve_weights,
    tema_positions,
)
from boruta_v14.study import DOWNLOAD_START, TRADING_START, align_closes, fetch_close, make_split

NOTIONAL = 100_000.0
SLEEVES = {"indices": INDICES, "stocks": STOCKS}


def _sharpe(ret: pd.Series) -> float:
    r = ret.dropna()
    if len(r) < 2:
        return 0.0
    sd = float(r.std(ddof=1))
    if sd == 0.0:
        return 0.0
    return float(r.mean() / sd * (ANN_DAYS**0.5))


def _max_dd(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1.0).min())


def _window_pnl(equity: pd.Series, start) -> float:
    """Dollar gain from the equity already in the book at the prior close."""
    before = equity.loc[: pd.Timestamp(start)].iloc[:-1]
    if before.empty:
        base = float(equity.iloc[0])
    else:
        base = float(before.iloc[-1])
    return float(equity.iloc[-1] - base)


def _summarize(name: str, net: pd.Series, split) -> dict:
    equity = NOTIONAL * (1.0 + net).cumprod()
    is_ret = net.loc[split.is_start : split.is_end]
    oos_ret = net.loc[split.oos_start : split.oos_end]
    return {
        "book": name,
        "end": float(equity.iloc[-1]),
        "pnl": float(equity.iloc[-1] - NOTIONAL),
        "max_dd": _max_dd(equity),
        "is_sharpe": _sharpe(is_ret),
        "oos_sharpe": _sharpe(oos_ret),
        "test_pnl": _window_pnl(equity, split.oos_start),
        "equity": equity,
    }


def _month_end(equity: pd.Series) -> pd.Series:
    return equity.resample("ME").last().dropna()


def main() -> None:
    symbols = tuple(dict.fromkeys([*INDICES, *STOCKS, *REGIME]))
    closes = align_closes({symbol: fetch_close(symbol, DOWNLOAD_START) for symbol in symbols})
    panel = pd.DataFrame(closes)
    split = make_split(panel.index, TRADING_START)
    trade = panel.loc[split.is_start : split.oos_end]
    rets = panel.pct_change().fillna(0.0)

    sleeves = {}
    for name, members in SLEEVES.items():
        score, vol = score_panels(panel.loc[:, list(members)])
        sleeves[name] = sleeve_weights(score, vol, rets.loc[:, list(members)])

    regime = beta_regime(panel.loc[:, list(REGIME)])
    decision = combine_sleeves(sleeves, regime["scale"])
    tema = tema_positions({symbol: panel[symbol] for symbol in (*INDICES, *STOCKS)})

    books = {
        "hold": equal_hold_weights(panel.index, list(tema.columns)),
        "rotation": execute_decision(decision),
        "tema_leaders": execute_decision(decision, tema),
        "tema_equal": equal_tema_weights(tema),
    }
    # Prices before the trading start are warmup. The book starts flat there
    # in the report even though the indicators have already been warming up.
    books = {name: weights.loc[split.is_start : split.oos_end] for name, weights in books.items()}
    trade_rets = rets.loc[split.is_start : split.oos_end]

    rows = []
    curves = {}
    for name, weights in books.items():
        net = net_returns(weights, trade_rets, COST)
        row = _summarize(name, net, split)
        curves[name] = row.pop("equity")
        held = weights.sum(axis=1)
        row["avg_gross"] = float(held.mean())
        row["avg_names"] = float((weights > 1e-8).sum(axis=1).mean())
        rows.append(row)
        print(
            f"{name:14s} end {row['end']:10,.0f}  pnl {row['pnl']:+10,.0f}  "
            f"test {row['test_pnl']:+10,.0f}  IS {row['is_sharpe']:.2f}  OOS {row['oos_sharpe']:.2f}  "
            f"dd {row['max_dd']:.1%}  gross {row['avg_gross']:.2f}"
        )

    leaders = books["tema_leaders"]
    occupancy = (leaders > 1e-8).mean().sort_values(ascending=False)
    print("days in the gated book:")
    print(occupancy.round(2).to_string())
    print("regime share", regime.loc[split.is_start : split.oos_end, "state"].value_counts(normalize=True).round(2).to_dict())

    out = Path("results")
    out.mkdir(exist_ok=True)
    table = pd.DataFrame(rows)
    table.to_csv(out / "rotation_pnl.csv", index=False)
    occupancy.rename("share_of_days").to_csv(out / "rotation_occupancy.csv", header=True)

    fig, ax = plt.subplots(figsize=(12, 6.2))
    colors = {"hold": "#64748b", "rotation": "#1d4ed8", "tema_leaders": "#0f766e", "tema_equal": "#b45309"}
    labels = {
        "hold": "Buy and hold, equal weight",
        "rotation": "Rotation leaders",
        "tema_leaders": "OR book on those leaders",
        "tema_equal": "OR book, equal weight",
    }
    for name, equity in curves.items():
        ax.plot(equity.index, equity.values, color=colors[name], lw=1.6, label=labels[name])
    ax.axvline(split.oos_start, color="#b45309", lw=1.0, ls="--", label="Test start")
    ax.axhline(NOTIONAL, color="#cbd5e1", lw=0.8)
    ax.set_ylabel("Equity ($)")
    ax.set_title("Beta-rotation sleeves, $100,000 start, daily Yahoo closes")
    ax.legend(frameon=False, loc="upper left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    for path in (out / "rotation_equity.png", Path("/opt/cursor/artifacts/rotation_equity.png")):
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=130)
    plt.close(fig)

    months = _month_end(curves["hold"]).index
    payload = {
        "start": str(split.is_start.date()),
        "test": str(split.oos_start.date()),
        "end": str(split.oos_end.date()),
        "months": [ts.strftime("%Y-%m") for ts in months],
        "series": {
            name: [round(float(v), 2) for v in _month_end(curves[name]).reindex(months).ffill()]
            for name in curves
        },
        "rows": rows,
        "occupancy": {symbol: round(float(share), 4) for symbol, share in occupancy.items()},
        "regime": regime.loc[split.is_start : split.oos_end, "state"].value_counts(normalize=True).round(4).to_dict(),
    }
    (out / "rotation_monthly.json").write_text(json.dumps(payload))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
