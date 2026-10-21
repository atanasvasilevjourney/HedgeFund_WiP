"""Reconstruction checks. No market data."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from boruta_v14.backtest import window_stats
from boruta_v14.boruta import binomial_twosided_pvalue, grade_from_hits, summarize_grades
from boruta_v14.grid import grid_search_tema, notebook_grid, on_notebook_grid, on_package_grid
from boruta_v14.indicators import kama, stc, tema
from boruta_v14.model import (
    PUBLISHED,
    format_panel,
    frozen_params,
    params_valid,
    replay,
    with_knob,
)
from boruta_v14.sensitivity import SENSITIVITY_KNOBS, format_sensitivity, neighbor_deltas
from boruta_v14.signals import (
    StcParams,
    TemaParams,
    params_line,
    position_from_events,
    tema_frame,
)


class IndicatorTests(unittest.TestCase):
    def test_tema_constant_matches_talib_lookback(self):
        n = 3
        values = np.full(20, 5.0)
        out = tema(values, n)
        first = 3 * (n - 1)
        self.assertTrue(np.isnan(out[first - 1]))
        self.assertAlmostEqual(out[first], 5.0)

    def test_kama_matches_notebook_formula(self):
        # n=2, fast=2, slow=3. Hand-expanded from calculate_kama.
        close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        out = kama(close, n=2, fast=2, slow=3)
        self.assertTrue(np.isnan(out.iloc[0]))
        self.assertTrue(np.isnan(out.iloc[1]))
        self.assertAlmostEqual(out.iloc[2], 3.0)
        sc = (2.0 / 3.0) ** 2  # er=1, fast_sc=2/3, slow_sc=0.5, sc=(2/3)^2
        k3 = 3.0 + sc * (4.0 - 3.0)
        k4 = k3 + sc * (5.0 - k3)
        self.assertAlmostEqual(out.iloc[3], k3, places=9)
        self.assertAlmostEqual(out.iloc[4], k4, places=9)

    def test_stc_stays_inside_0_100(self):
        rng = np.random.default_rng(0)
        close = pd.Series(100 + np.cumsum(rng.normal(0, 1, 400)))
        osc = stc(close, fast=23, slow=50, cycle=10, factor=0.5).dropna()
        self.assertGreater(len(osc), 50)
        self.assertGreaterEqual(osc.min(), -1e-6)
        self.assertLessEqual(osc.max(), 100 + 1e-6)


class SignalTests(unittest.TestCase):
    def test_buy_wins_when_entry_and_exit_share_a_bar(self):
        idx = pd.RangeIndex(4)
        entries = pd.Series([False, True, False, True], index=idx)
        exits = pd.Series([False, True, True, False], index=idx)
        pos = position_from_events(entries, exits)
        self.assertEqual(pos.tolist(), [0, 1, 0, 1])

    def test_tema_or_of_three_crosses_opens_a_long(self):
        # A step up pulls the fast TEMA through the slow ones.
        slow = np.full(80, 10.0)
        jump = np.concatenate([slow, np.linspace(10, 40, 40), np.full(40, 40.0)])
        close = pd.Series(jump)
        frame = tema_frame(close, TemaParams(3, 15, 30, kind="tema"))
        self.assertTrue(bool(frame["entries"].any()))
        self.assertGreater(frame["t1"].dropna().iloc[-1], frame["t3"].dropna().iloc[-1])

    def test_panel_param_string(self):
        text = params_line(TemaParams(), StcParams())
        self.assertEqual(
            text,
            "TEMA(7,137,100) OR STC_REGIME(23,50,a,25,80) OR DOUBLE_KAMA",
        )
        self.assertIn(text, format_panel(None))
        self.assertIn(PUBLISHED["run_id"], format_panel(None))
        self.assertIn("MED / STRONG", format_panel(None))


class GridTests(unittest.TestCase):
    def test_frozen_point_is_on_both_grids(self):
        self.assertTrue(on_notebook_grid(7, 137, 100))
        self.assertTrue(on_package_grid(7, 137, 100))
        self.assertIn((7, 137, 100), notebook_grid())

    def test_search_returns_a_combo_from_the_list(self):
        rng = np.random.default_rng(1)
        drift = np.linspace(0, 30, 180) + rng.normal(0, 0.4, 180)
        close = pd.Series(100 + drift, index=pd.bdate_range("2020-01-01", periods=180))
        combos = [(4, 16, 28), (7, 20, 40)]
        best, sharpe = grid_search_tema(close, combos, kind="ema", min_trades_per_year=0)
        self.assertIn(best, combos)
        self.assertTrue(np.isfinite(sharpe))


class BorutaGradeTests(unittest.TestCase):
    def test_binomial_extremes(self):
        self.assertAlmostEqual(binomial_twosided_pvalue(10, 20), 1.0)
        self.assertLess(binomial_twosided_pvalue(20, 20), 0.01)
        self.assertEqual(grade_from_hits(20, 20), "STRONG")
        self.assertEqual(grade_from_hits(0, 20), "WEAK")
        self.assertEqual(grade_from_hits(10, 20), "MED")

    def test_summary_uses_chart_order(self):
        self.assertEqual(
            summarize_grades({"TEMA": "STRONG", "STC_REGIME": "MED", "DOUBLE_KAMA": "WEAK"}),
            "MED / STRONG",
        )

    def test_real_feature_beats_a_shadow(self):
        from boruta_v14.boruta import boruta_grades

        rng = np.random.default_rng(0)
        n = 500
        signal = rng.normal(size=n)
        noise = rng.normal(size=n)
        y = pd.Series((signal > 0).astype(int))
        grades = boruta_grades(
            pd.DataFrame({"signal": signal, "noise": noise}),
            y,
            n_iter=11,
            n_estimators=40,
            seed=0,
        )
        self.assertEqual(grades["signal"], "STRONG")
        self.assertNotEqual(grades["noise"], "STRONG")


class SensitivityTests(unittest.TestCase):
    def test_neighborhood_is_eighty_valid_frozen_neighbors(self):
        self.assertEqual(len(neighbor_deltas()), 80)
        self.assertEqual(len(SENSITIVITY_KNOBS) * 20, 80)
        base = frozen_params()
        for knob, delta in neighbor_deltas():
            current = {
                "tema_w2": base.tema.w2,
                "tema_w3": base.tema.w3,
                "stc_fast": base.stc.fast,
                "stc_slow": base.stc.slow,
            }[knob]
            trial = with_knob(base, knob, current + delta)
            self.assertTrue(params_valid(trial), msg=f"{knob} {delta}")

    def test_panel_sensitivity_sentence(self):
        self.assertEqual(format_sensitivity(25, 80, 80), "MED (80/80 HIGH)")
        self.assertEqual(format_sensitivity(10, 80, 80), "LOW (80/80 HIGH)")
        self.assertEqual(format_sensitivity(55, 40, 80), "HIGH (40/80 HIGH)")


class ReplayTests(unittest.TestCase):
    def test_uptrend_long_makes_money_and_counts_a_closed_trade(self):
        idx = pd.bdate_range("2020-01-01", periods=40)
        close = pd.Series(np.linspace(100, 140, 40), index=idx)
        entries = pd.Series(False, index=idx)
        exits = pd.Series(False, index=idx)
        entries.iloc[1] = True
        exits.iloc[30] = True
        stats = window_stats(close, entries, exits, idx[0], idx[-1], fees=0.0, slippage=0.0)
        self.assertEqual(stats.trades, 1)
        self.assertGreater(stats.point_pnls[0], 0)
        self.assertGreater(stats.total_return, 0)

    def test_replay_on_a_synthetic_book(self):
        rng = np.random.default_rng(2)
        idx = pd.bdate_range("2016-01-01", periods=700)
        close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, 700))), index=idx)
        result = replay(
            close,
            trading_start="2018-01-01",
            run_boruta=False,
            run_sensitivity=False,
        )
        self.assertEqual(result.params_text, params_line(TemaParams(), StcParams()))
        self.assertGreaterEqual(result.oos_stats.trades, 0)
        self.assertLessEqual(result.oos_stats.max_dd, 0.0)
        text = format_panel(result)
        self.assertIn("REPLAY", text)
        self.assertIn("OR_EVENT", text)


if __name__ == "__main__":
    unittest.main()
