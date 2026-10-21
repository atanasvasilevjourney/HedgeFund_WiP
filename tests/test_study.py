"""The fast grid scorer has to match the book backtest, or the search is fiction."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from boruta_v14.backtest import window_stats
from boruta_v14.indicators import tema
from boruta_v14.signals import TemaParams, tema_frame
from boruta_v14.study import (
    equity_path,
    grid_search_tema_lengths,
    make_split,
    score_window_np,
    tema_event_arrays,
)


class FastScoreTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(4)
        idx = pd.bdate_range("2014-01-01", periods=2600)
        drift = np.linspace(0, 0.4, len(idx)) + rng.normal(0, 0.01, len(idx)).cumsum() * 0.0
        noise = rng.normal(0, 0.012, len(idx))
        self.close = pd.Series(100 * np.exp(np.cumsum(noise) + drift), index=idx, name="SYN")
        self.split = make_split(self.close.index)

    def test_numpy_events_match_the_library(self):
        frame = tema_frame(self.close, TemaParams(7, 40, 70, kind="tema"))
        prices = self.close.to_numpy(dtype=float)
        ent, ext = tema_event_arrays(tema(prices, 7), tema(prices, 40), tema(prices, 70))
        self.assertTrue(np.array_equal(frame["entries"].to_numpy(dtype=bool), ent))
        self.assertTrue(np.array_equal(frame["exits"].to_numpy(dtype=bool), ext))

    def test_numpy_score_matches_window_stats(self):
        frame = tema_frame(self.close, TemaParams(7, 40, 70, kind="tema"))
        stats = window_stats(
            self.close, frame["entries"], frame["exits"], self.split.is_start, self.split.is_end, 0.001, 0.001
        )
        i0 = int(self.close.index.searchsorted(self.split.is_start))
        i1 = int(self.close.index.searchsorted(self.split.is_end, side="right") - 1)
        sharpe, dd, trades, total = score_window_np(
            self.close.to_numpy(dtype=float),
            frame["entries"].to_numpy(dtype=bool),
            frame["exits"].to_numpy(dtype=bool),
            i0,
            i1,
            cost=0.002,
        )
        self.assertAlmostEqual(sharpe, stats.sharpe, places=8)
        self.assertAlmostEqual(dd, stats.max_dd, places=8)
        self.assertAlmostEqual(total, stats.total_return, places=8)
        self.assertEqual(trades, stats.trades)

    def test_grid_picks_the_training_argmax(self):
        combos = [(4, 20, 40), (7, 30, 60), (10, 40, 80)]
        base_ent = np.zeros(len(self.close), dtype=bool)
        base_ext = np.zeros(len(self.close), dtype=bool)
        outcome = grid_search_tema_lengths(
            self.close, base_ent, base_ext, self.split, combos=combos, min_trades_per_year=0.0
        )
        self.assertIn(outcome.best, combos)
        scores = []
        for w1, w2, w3 in combos:
            frame = tema_frame(self.close, TemaParams(w1, w2, w3, "tema"))
            stats = window_stats(
                self.close, frame["entries"], frame["exits"], self.split.is_start, self.split.is_end, 0.001, 0.001
            )
            scores.append(stats.sharpe)
        self.assertEqual(outcome.best, combos[int(np.argmax(scores))])
        self.assertAlmostEqual(outcome.best_is, max(scores), places=6)

    def test_equity_path_matches_total_return(self):
        frame = tema_frame(self.close, TemaParams(7, 40, 70, kind="tema"))
        stats = window_stats(
            self.close, frame["entries"], frame["exits"], self.split.is_start, self.split.oos_end, 0.001, 0.001
        )
        equity = equity_path(
            self.close, frame["entries"], frame["exits"], self.split.is_start, self.split.oos_end
        )
        self.assertAlmostEqual(float(equity.iloc[-1] - 1.0), stats.total_return, places=8)


if __name__ == "__main__":
    unittest.main()
