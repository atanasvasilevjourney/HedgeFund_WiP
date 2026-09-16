# TEMA + MACD BTC — Notebook Guide

Python modules in `strategies/` are mirrored here as Jupyter notebooks for interactive use.

## Recommended order

| # | Notebook | Source `.py` | Purpose |
|---|----------|--------------|---------|
| 1 | **`tema_macd_01_engine.ipynb`** | `tema_macd_ensemble_btc.py` + `tema_macd_features.py` | Indicators, backtest, feature matrix |
| 2 | `tema_macd_03_optimization.ipynb` | `tema_macd_ensemble_optimize.py` | Boruta, grid, Optuna, walk-forward |
| 3 | `tema_macd_04_live_config.ipynb` | `tema_macd_live_config.py` | JSON schema for Vercel terminal |
| 4 | **`tema_macd_05_export_terminal.ipynb`** | `scripts/export_tema_macd_live_config.py` | Export optimized live config |

Root-level shortcuts:

- `tema_macd_ensemble_btc.ipynb` — quick start backtest
- `tema_macd_ensemble_btc_research.ipynb` — full research workflow

## Regenerate notebooks from `.py`

```bash
python3 scripts/py_to_notebook.py strategies/tema_macd_ensemble_btc.py -o notebooks/tema_macd_01_engine_core.ipynb
```

## Note

The **`.py` files remain** for the Vercel terminal and CLI scripts. Edit Python for production; use notebooks for exploration, then re-run `py_to_notebook.py` or sync manually.
