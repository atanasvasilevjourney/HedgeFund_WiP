# Rotation engine — notebook archive

Single folder for Carver / TEMA / KAMA / unified swing / crypto allocation notebooks and related docs.

## Start here

| Priority | Notebook | Purpose |
|----------|----------|---------|
| **1** | `unified_swing_momentum_engine (4).ipynb` | Integrated swing engine (Carver + SwingEMA + KAMA + CS + validation) |
| **2** | `carver_ultimate_daily_prop_engine_v1.ipynb` | Multi-bucket daily prop (indices / stocks / crypto) |
| **3** | `carver_engine_tutorial_qqq.ipynb` | Layer-by-layer Carver tutorial on QQQ |
| **4** | `carver_engine_with_cross_sectional.ipynb` | Cross-sectional momentum (Strategy 19) |
| **5** | `rotation_engine.ipynb` | Equity/index rotation (multi-name book) |
| **6** | `crypto_rotation_engine.ipynb` | Crypto-only rotation (OKX universe) |
| **7** | `tema_macd_ensemble.ipynb` | TEMA + MACD ensemble research |
| **8** | `live_momentum_scanner_slack.ipynb` | Crypto live scanner + Slack |

## Data scripts

| Script | Purpose |
|--------|---------|
| `fetch_okx.py` | OKX OHLCV fetch helper |
| `fetch_top_1000.py` | Top market-cap universe helper |

## Lineage

```
carver_engine_tutorial_qqq
  → carver_engine_with_cross_sectional
       → carver_ultimate_daily_prop_engine_v1
            → unified_swing_momentum_engine (4)

TEMA-TEMPLATE_adjusted6_warmup (1)  →  SwingEMA in unified (fixed params, no grid)
KAMA-DF-stability-scoring            →  fixed KAMA in unified (no per-ticker Optuna)

crypto_ranked_asset_allocation_*     →  live scanner / v2
crypto_alpha_engine_v4_multi_asset_prop →  daily snapshot + beta rotation
```

## Duplicates

`unified_swing_momentum_engine (1)–(3)` are often identical to `unified_swing_momentum_engine.ipynb`; keep **(4)** as canonical.

`Pasted markdown(1).md` — cross-sectional layer narrative (Carver bootcamp notes).

## Dependencies

See `requirements_qqq_tema_macd.txt` (minimal); full notebook stacks also need `yfinance`, `vectorbt`, `talib`, `optuna`, etc. per notebook headers.

## Note

Copies also remain at repo root for backward compatibility. New work should prefer this folder or extract shared code into `strategies/` when available.
