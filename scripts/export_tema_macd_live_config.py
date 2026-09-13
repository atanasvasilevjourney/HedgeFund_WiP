#!/usr/bin/env python3
"""Run research pipeline and export live config for Vercel terminal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.tema_macd_ensemble_optimize import export_live_config_from_research


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--boruta-iter", type=int, default=100)
    p.add_argument("--optuna-trials", type=int, default=120)
    p.add_argument("--walk-forward-splits", type=int, default=5)
    args = p.parse_args()

    out = export_live_config_from_research(
        start=args.start,
        boruta_iter=args.boruta_iter,
        optuna_trials=args.optuna_trials,
        walk_forward_splits=args.walk_forward_splits,
    )
    print(f"Wrote live config: {out}")


if __name__ == "__main__":
    main()
