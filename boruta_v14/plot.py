"""Dark price panel in the shape of the LLY BORUTA v1.4 chart."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from boruta_v14.backtest import execute
from boruta_v14.model import Replay, format_panel
from boruta_v14.signals import position_from_events


def _shade(ax, position: pd.Series) -> None:
    if position.empty:
        return
    pos = position.astype(int)
    changes = pos.ne(pos.shift(1)).to_numpy()
    idx = np.flatnonzero(changes)
    bounds = list(idx) + [len(pos)]
    for start, end in zip(bounds[:-1], bounds[1:]):
        color = "#1b7f4a" if pos.iloc[start] == 1 else "#7f1d2d"
        ax.axvspan(pos.index[start], pos.index[end - 1], color=color, alpha=0.18, lw=0)


def _trade_markers(ax, close: pd.Series, position: pd.Series) -> None:
    px = close.to_numpy(dtype=float)
    pos = position.to_numpy(dtype=int)
    entry_i = None
    prev = 0
    for i, cur in enumerate(pos):
        if prev == 0 and cur == 1:
            entry_i = i
            ax.scatter(close.index[i], px[i], color="#3dd68c", s=28, zorder=5)
            ax.annotate(
                "BUY",
                (close.index[i], px[i]),
                textcoords="offset points",
                xytext=(0, 8),
                color="#3dd68c",
                fontsize=7,
                ha="center",
            )
        elif prev == 1 and cur == 0 and entry_i is not None:
            points = px[i] - px[entry_i]
            ax.scatter(close.index[i], px[i], color="#e879f9", s=28, zorder=5)
            ax.annotate(
                f"SELL {points:+.0f}",
                (close.index[i], px[i]),
                textcoords="offset points",
                xytext=(0, -12),
                color="#e879f9",
                fontsize=7,
                ha="center",
            )
            entry_i = None
        prev = int(cur)


def plot_replay(close: pd.Series, result: Replay, path: str | Path, ohlc: pd.DataFrame | None = None) -> Path:
    """Save a two-row chart: price with the OR position, and the STC oscillator."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ent, _ = execute(result.signals.entries, result.signals.exits)
    ext = result.signals.exits.shift(1).fillna(False).astype(bool)
    # Show the book from the in-sample start onward, still using full-sample fills
    # that were shifted before the slice, matching the metric windows.
    view = close.loc[result.is_start :]
    ent_v = ent.reindex(view.index).fillna(False).astype(bool)
    ext_v = ext.reindex(view.index).fillna(False).astype(bool)
    pos = position_from_events(ent_v, ext_v)

    fig, (ax_px, ax_stc) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    fig.patch.set_facecolor("#0e1116")
    for ax in (ax_px, ax_stc):
        ax.set_facecolor("#0e1116")
        ax.tick_params(colors="#c5cdd6")
        for spine in ax.spines.values():
            spine.set_color("#2a3140")
        ax.grid(True, color="#1c2330", lw=0.6)

    _shade(ax_px, pos)
    ax_px.plot(view.index, view.values, color="#d7dde6", lw=1.0, label="Close")
    tema = result.signals.tema
    ax_px.plot(view.index, tema["t1"].reindex(view.index), color="#22d3ee", lw=1.0, label=f"TEMA {result.params.tema.w1}")
    ax_px.plot(view.index, tema["t2"].reindex(view.index), color="#fb923c", lw=1.0, label=f"TEMA {result.params.tema.w2}")
    ax_px.plot(view.index, tema["t3"].reindex(view.index), color="#facc15", lw=1.0, label=f"TEMA {result.params.tema.w3}")
    sma = close.rolling(200).mean().reindex(view.index)
    ax_px.plot(view.index, sma, color="#4ade80", lw=0.8, label="SMA 200")
    _trade_markers(ax_px, view, pos)
    ax_px.legend(loc="upper left", fontsize=8, frameon=False, labelcolor="#c5cdd6")
    ax_px.set_title(
        f"LLY  BORUTA v1.4    {result.params_text}",
        color="#e8eef6",
        loc="left",
        fontsize=11,
    )

    stc = result.signals.stc["stc"].reindex(view.index)
    ax_stc.plot(view.index, stc, color="#38bdf8", lw=1.0)
    ax_stc.axhline(result.params.stc.low, color="#3dd68c", lw=0.7, ls="--")
    ax_stc.axhline(result.params.stc.high, color="#e879f9", lw=0.7, ls="--")
    ax_stc.set_ylim(-5, 105)
    ax_stc.set_ylabel("STC", color="#c5cdd6")

    fig.text(
        0.99,
        0.62,
        format_panel(result),
        ha="right",
        va="center",
        color="#d7dde6",
        fontsize=7,
        family="monospace",
        linespacing=1.35,
    )
    fig.tight_layout(rect=(0, 0, 0.78, 1))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
