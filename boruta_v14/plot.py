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
    last_label = None
    gap = pd.Timedelta(days=50)
    for i, cur in enumerate(pos):
        if prev == 0 and cur == 1:
            entry_i = i
            ax.scatter(close.index[i], px[i], marker="^", color="#3dd68c", s=22, zorder=5)
            if last_label is None or close.index[i] - last_label >= gap:
                ax.annotate(
                    "BUY",
                    (close.index[i], px[i]),
                    textcoords="offset points",
                    xytext=(0, 7),
                    color="#3dd68c",
                    fontsize=7,
                    ha="center",
                )
                last_label = close.index[i]
        elif prev == 1 and cur == 0 and entry_i is not None:
            points = px[i] - px[entry_i]
            ax.scatter(close.index[i], px[i], marker="v", color="#e879f9", s=22, zorder=5)
            if last_label is None or close.index[i] - last_label >= gap:
                ax.annotate(
                    f"{points:+.0f}",
                    (close.index[i], px[i]),
                    textcoords="offset points",
                    xytext=(0, -11),
                    color="#e879f9",
                    fontsize=7,
                    ha="center",
                )
                last_label = close.index[i]
            entry_i = None
        prev = int(cur)


def plot_replay(close: pd.Series, result: Replay, path: str | Path, ohlc: pd.DataFrame | None = None) -> Path:
    """Save price, STC, and the published-versus-replay card side by side."""
    del ohlc  # OHLC is accepted so callers can pass the download through unchanged.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ent, _ = execute(result.signals.entries, result.signals.exits)
    ext = result.signals.exits.shift(1).fillna(False).astype(bool)
    # Fills were shifted on the full sample, then the book is shown from the
    # in-sample start, which is the first bar the card evaluates.
    view = close.loc[result.is_start :]
    ent_v = ent.reindex(view.index).fillna(False).astype(bool)
    ext_v = ext.reindex(view.index).fillna(False).astype(bool)
    pos = position_from_events(ent_v, ext_v)

    fig = plt.figure(figsize=(18, 8.4))
    fig.patch.set_facecolor("#0e1116")
    grid = fig.add_gridspec(2, 2, width_ratios=[3.4, 1.7], height_ratios=[3, 1], wspace=0.06, hspace=0.08)
    ax_px = fig.add_subplot(grid[0, 0])
    ax_stc = fig.add_subplot(grid[1, 0], sharex=ax_px)
    ax_card = fig.add_subplot(grid[:, 1])
    for ax in (ax_px, ax_stc, ax_card):
        ax.set_facecolor("#0e1116")
        ax.tick_params(colors="#c5cdd6")
        for spine in ax.spines.values():
            spine.set_color("#2a3140")
    for ax in (ax_px, ax_stc):
        ax.grid(True, color="#1c2330", lw=0.6)
    ax_card.set_xticks([])
    ax_card.set_yticks([])

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
    ax_px.set_title("LLY  BORUTA v1.4", color="#e8eef6", loc="left", fontsize=12)
    ax_px.tick_params(labelbottom=False)

    stc = result.signals.stc["stc"].reindex(view.index)
    ax_stc.plot(view.index, stc, color="#38bdf8", lw=1.0)
    ax_stc.axhline(result.params.stc.low, color="#3dd68c", lw=0.7, ls="--")
    ax_stc.axhline(result.params.stc.high, color="#e879f9", lw=0.7, ls="--")
    ax_stc.set_ylim(-5, 105)
    ax_stc.set_ylabel("STC", color="#c5cdd6")

    ax_card.text(
        0.04,
        0.98,
        format_panel(result),
        ha="left",
        va="top",
        color="#d7dde6",
        fontsize=7,
        family="monospace",
        linespacing=1.35,
        transform=ax_card.transAxes,
    )
    fig.savefig(path, dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
