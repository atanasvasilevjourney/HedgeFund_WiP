"""Beta-rotation gate: ranking, regime vote, and the one-bar lag."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from boruta_v14.rotation import (
    _cap_weights,
    beta_regime,
    combine_sleeves,
    equal_hold_weights,
    execute_decision,
    net_returns,
    sleeve_weights,
)


class CapTests(unittest.TestCase):
    def test_single_name_stays_inside_the_cap(self):
        weights = _cap_weights(np.array([5.0]), 0.20)
        self.assertAlmostEqual(float(weights[0]), 0.20)

    def test_uncapped_weights_sum_to_one(self):
        weights = _cap_weights(np.array([1.0, 1.0, 1.0, 1.0, 1.0]), 0.20)
        self.assertAlmostEqual(float(weights.sum()), 1.0, places=8)
        self.assertTrue((weights <= 0.20 + 1e-12).all())


class SleeveTests(unittest.TestCase):
    def test_only_positive_scores_and_top_count(self):
        idx = pd.bdate_range("2020-01-01", periods=40)
        score = pd.DataFrame(
            {
                "A": np.linspace(0.1, 3.0, len(idx)),
                "B": np.linspace(0.1, 2.0, len(idx)),
                "C": np.full(len(idx), -1.0),
                "D": np.linspace(0.1, 1.0, len(idx)),
            },
            index=idx,
        )
        vol = pd.DataFrame(0.20, index=idx, columns=score.columns)
        rets = pd.DataFrame(0.0, index=idx, columns=score.columns)
        weights = sleeve_weights(score, vol, rets, n_assets=2, max_weight=0.70, corr_window=10)
        self.assertTrue((weights["C"] == 0).all())
        self.assertTrue((weights["D"] == 0).all())
        self.assertTrue((weights.sum(axis=1) <= 1.0 + 1e-8).all())
        self.assertGreater(float(weights["A"].iloc[-1]), 0.0)
        self.assertGreater(float(weights["B"].iloc[-1]), 0.0)


class RegimeTests(unittest.TestCase):
    def test_cyclicals_and_breadth_vote_risk_on(self):
        idx = pd.bdate_range("2014-01-01", periods=500)
        spy = np.linspace(100, 140, len(idx))
        panel = pd.DataFrame(
            {
                "SPY": spy,
                "XLP": np.linspace(100, 105, len(idx)),
                "XLY": np.linspace(100, 220, len(idx)),
                "XLU": np.linspace(100, 70, len(idx)),
                "RSP": np.linspace(100, 210, len(idx)),
            },
            index=idx,
        )
        regime = beta_regime(panel).dropna()
        self.assertEqual(regime["state"].iloc[-1], "RISK_ON")
        self.assertAlmostEqual(float(regime["scale"].iloc[-1]), 1.0)

    def test_defensive_leadership_votes_risk_off(self):
        idx = pd.bdate_range("2014-01-01", periods=500)
        panel = pd.DataFrame(
            {
                "SPY": np.linspace(100, 160, len(idx)),
                "XLP": np.linspace(100, 220, len(idx)),
                "XLY": np.linspace(100, 100, len(idx)),
                "XLU": np.linspace(100, 240, len(idx)),
                "RSP": np.linspace(100, 110, len(idx)),
            },
            index=idx,
        )
        regime = beta_regime(panel).dropna()
        self.assertEqual(regime["state"].iloc[-1], "RISK_OFF")
        self.assertAlmostEqual(float(regime["scale"].iloc[-1]), 0.35)


class ExecutionTests(unittest.TestCase):
    def test_gate_uses_todays_tema_and_yesterdays_rank(self):
        idx = pd.bdate_range("2020-01-01", periods=4)
        decision = pd.DataFrame({"AAA": [0.0, 0.40, 0.40, 0.10]}, index=idx)
        tema = pd.DataFrame({"AAA": [0.0, 1.0, 0.0, 1.0]}, index=idx)
        held = execute_decision(decision, tema)
        # Day 0 has no prior decision. Day 1 holds yesterday's 0 with today's long.
        self.assertEqual(held["AAA"].tolist(), [0.0, 0.0, 0.0, 0.40])

    def test_regime_scale_is_inside_the_lagged_decision(self):
        idx = pd.bdate_range("2020-01-01", periods=3)
        sleeves = {"indices": pd.DataFrame({"SPY": [1.0, 1.0, 1.0]}, index=idx)}
        scale = pd.Series([1.0, 0.35, 1.0], index=idx)
        decision = combine_sleeves(sleeves, scale, caps={"indices": 0.50})
        # The 20% name cap lives in sleeve_weights. This layer applies the sleeve cap.
        self.assertAlmostEqual(float(decision["SPY"].iloc[0]), 0.50)
        self.assertAlmostEqual(float(decision["SPY"].iloc[1]), 0.50 * 0.35)
        held = execute_decision(decision)
        self.assertAlmostEqual(float(held["SPY"].iloc[1]), float(decision["SPY"].iloc[0]))

    def test_turnover_charges_the_first_weight(self):
        idx = pd.bdate_range("2020-01-01", periods=3)
        weights = equal_hold_weights(idx, ["AAA", "BBB"])
        rets = pd.DataFrame(0.0, index=idx, columns=["AAA", "BBB"])
        net = net_returns(weights, rets, cost=0.002)
        self.assertAlmostEqual(float(net.iloc[0]), -0.002)
        self.assertAlmostEqual(float(net.iloc[1]), 0.0)


if __name__ == "__main__":
    unittest.main()
