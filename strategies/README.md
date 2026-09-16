# Strategies (Python modules)

These modules power the TEMA/MACD BTC stack and the Vercel terminal.

**Prefer Jupyter?** Use the converted notebooks in [`../notebooks/`](../notebooks/README.md) — same logic, cell-by-cell execution.

| Module | Notebook |
|--------|----------|
| `tema_macd_ensemble_btc.py` | `notebooks/tema_macd_01_engine.ipynb` |
| `tema_macd_features.py` | (included in `tema_macd_01_engine.ipynb`) |
| `tema_macd_ensemble_optimize.py` | `notebooks/tema_macd_03_optimization.ipynb` |
| `tema_macd_live_config.py` | `notebooks/tema_macd_04_live_config.ipynb` |

Regenerate from source:

```bash
python3 scripts/py_to_notebook.py strategies/tema_macd_ensemble_optimize.py -o notebooks/tema_macd_03_optimization.ipynb
```
