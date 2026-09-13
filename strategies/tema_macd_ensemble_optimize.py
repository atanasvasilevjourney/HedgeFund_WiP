"""
Grid search, Boruta feature selection, Optuna tuning for TEMA/MACD BTC ensemble.

Objective (default): maximize Sharpe while penalizing drawdown on validation data.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from strategies.tema_macd_ensemble_btc import (
    EnsembleConfig,
    build_ensemble_frame,
    combine_signals,
    load_btc_close,
    macd,
    macd_signal,
    max_drawdown,
    sharpe,
    summarize_backtest,
    tema,
    tema_signal,
)
from strategies.tema_macd_features import build_feature_matrix, forward_return_labels


@dataclass(frozen=True)
class OptObjectiveWeights:
    sharpe: float = 1.0
    calmar: float = 0.35
    max_dd_penalty: float = 2.5  # subtract penalty * |max_dd|


def composite_score(stats: dict, w: OptObjectiveWeights = OptObjectiveWeights()) -> float:
    s = stats.get("sharpe", float("nan"))
    dd = abs(stats.get("max_drawdown", 0))
    calmar = stats.get("calmar", float("nan"))
    if np.isnan(s):
        return -1e9
    score = w.sharpe * s - w.max_dd_penalty * dd
    if not np.isnan(calmar):
        score += w.calmar * calmar
    return float(score)


def enrich_stats(df: pd.DataFrame, ann_days: int = 365) -> dict:
    st = summarize_backtest(df, ann_days)
    dd = abs(st.get("max_drawdown", 0))
    cagr = st.get("cagr", 0)
    st["calmar"] = cagr / dd if dd > 1e-9 else float("nan")
    st["objective"] = composite_score(st)
    return st


def split_series(close: pd.Series, train_ratio=0.6, val_ratio=0.2) -> tuple[pd.Series, pd.Series, pd.Series]:
    n = len(close)
    i1 = int(n * train_ratio)
    i2 = int(n * (train_ratio + val_ratio))
    return close.iloc[:i1], close.iloc[i1:i2], close.iloc[i2:]


def backtest_with_seed(
    close_full: pd.Series,
    eval_slice: pd.Series,
    warmup: int,
    cfg: EnsembleConfig,
) -> pd.DataFrame:
    """Indicators seeded with warmup bars before eval_slice start."""
    start = eval_slice.index[0]
    pos = close_full.index.get_loc(start)
    seed = close_full.iloc[max(0, pos - warmup) : pos + len(eval_slice)]
    df = build_ensemble_frame(seed, cfg)
    return df.loc[eval_slice.index]


def run_boruta_selection(
    close_train: pd.Series,
    max_iter: int = 100,
    random_state: int = 42,
    horizon: int = 1,
) -> tuple[list[str], pd.DataFrame]:
    from boruta import BorutaPy
    from sklearn.ensemble import RandomForestClassifier

    X = build_feature_matrix(close_train).fillna(0)
    y = forward_return_labels(close_train, horizon=horizon).fillna(0).astype(int)

    # Align: drop last `horizon` rows where label is NaN from forward shift
    valid = y.notna()
    X = X.loc[valid]
    y = y.loc[valid]

    rf = RandomForestClassifier(
        n_estimators=500,
        max_depth=5,
        random_state=random_state,
        n_jobs=-1,
        class_weight="balanced",
    )
    boruta = BorutaPy(rf, n_estimators="auto", max_iter=max_iter, random_state=random_state, verbose=0)
    boruta.fit(X.values, y.values)

    selected = X.columns[boruta.support_].tolist()
    tentative = X.columns[boruta.support_weak_].tolist()
    if not selected:
        # Fallback: confirmed + tentative, else top-8 by RF importance
        selected = tentative
        if not selected:
            rf.fit(X.values, y.values)
            imp = pd.Series(rf.feature_importances_, index=X.columns).sort_values(ascending=False)
            selected = imp.head(8).index.tolist()

    ranking = pd.DataFrame(
        {
            "feature": X.columns,
            "selected": boruta.support_,
            "tentative": boruta.support_weak_,
            "rank": boruta.ranking_,
        }
    ).sort_values("rank")
    return selected, ranking


def score_from_boruta_features(
    close: pd.Series,
    cfg: EnsembleConfig,
    selected_features: list[str],
    feature_weights: dict[str, float] | None = None,
) -> pd.Series:
    """Blend base TEMA/MACD ensemble with Boruta-selected feature votes."""
    base = build_ensemble_frame(close, cfg)
    score = base["ensemble_score"].copy()
    if not selected_features:
        return score

    X = build_feature_matrix(close).fillna(0)
    cols = [c for c in selected_features if c in X.columns]
    if not cols:
        return score

    votes = pd.Series(0.0, index=close.index)
    for c in cols:
        w = 1.0 if feature_weights is None else feature_weights.get(c, 1.0)
        col = X[c]
        if c.startswith("sig_") or c.endswith("_sig"):
            votes += w * col.clip(-1, 1)
        elif "rsi" in c:
            votes += w * np.where(col > 55, 1, np.where(col < 45, -1, 0))
        elif "mom_" in c or "dist" in c or "spread" in c:
            votes += w * np.sign(col)
        elif "vol_" in c:
            votes -= w * np.sign(col - col.median())  # high vol caution
        else:
            votes += w * np.sign(col)

    votes = votes / max(len(cols), 1)
    blend = 0.5 * score + 0.5 * votes.clip(-1, 1)
    return blend


def backtest_blended(
    close: pd.Series,
    cfg: EnsembleConfig,
    selected_features: list[str],
) -> pd.DataFrame:
    blend = score_from_boruta_features(close, cfg, selected_features)
    s_t = tema_signal(close, tema(close, cfg.tema_period))
    s_m = macd_signal(macd(close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal))

    pos = pd.Series(0.0, index=close.index)
    pos[blend >= cfg.long_threshold] = 1.0
    if not cfg.long_only:
        pos[blend <= -cfg.long_threshold] = -1.0
    pos[blend.abs() < cfg.flat_threshold] = 0.0

    pos = pos.shift(1).fillna(0.0)
    ret = close.pct_change().fillna(0.0)
    turnover = pos.diff().abs().fillna(0.0)
    strat_ret = pos * ret - turnover * (cfg.cost_bps / 1e4)
    equity = (1 + strat_ret).cumprod()

    return pd.DataFrame(
        {
            "close": close,
            "blend_score": blend,
            "position": pos,
            "return": strat_ret,
            "equity": equity,
            "sig_tema": s_t,
            "sig_macd": s_m,
        },
        index=close.index,
    )


def wide_grid_search(
    close_train: pd.Series,
    close_val: pd.Series,
    close_full: pd.Series,
    selected_features: list[str],
    max_combos: int = 2500,
    random_state: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    tema_periods = list(range(15, 96, 4))
    macd_fasts = [8, 10, 12, 15]
    macd_slows = [21, 26, 34, 39]
    macd_sigs = [5, 7, 9]
    long_th = [0.15, 0.25, 0.35, 0.45, 0.55]
    flat_th = [0.0, 0.05, 0.10, 0.15]

    combos = []
    for tp, mf, ms, msi, lt, ft in itertools.product(
        tema_periods, macd_fasts, macd_slows, macd_sigs, long_th, flat_th
    ):
        if mf >= ms:
            continue
        combos.append((tp, mf, ms, msi, lt, ft))

    if len(combos) > max_combos:
        idx = rng.choice(len(combos), size=max_combos, replace=False)
        combos = [combos[i] for i in idx]

    rows = []
    warmup = 220
    val_start = int(close_full.index.get_loc(close_val.index[0]))
    val_end = int(close_full.index.get_loc(close_val.index[-1]))
    val_seed = close_full.iloc[max(0, val_start - warmup) : val_end + 1]

    for tp, mf, ms, msi, lt, ft in combos:
        cfg = EnsembleConfig(
            tema_period=tp,
            macd_fast=mf,
            macd_slow=ms,
            macd_signal=msi,
            long_threshold=lt,
            flat_threshold=ft,
        )
        try:
            if selected_features:
                df_val = backtest_blended(val_seed, cfg, selected_features).loc[close_val.index]
            else:
                df_val = backtest_with_seed(close_full, close_val, warmup, cfg)
            st = enrich_stats(df_val)
            rows.append(
                {
                    "tema_period": tp,
                    "macd_fast": mf,
                    "macd_slow": ms,
                    "macd_signal": msi,
                    "long_threshold": lt,
                    "flat_threshold": ft,
                    **st,
                }
            )
        except Exception:
            continue

    return pd.DataFrame(rows).sort_values("objective", ascending=False)


def eval_config_on_slice(
    close_full: pd.Series,
    eval_slice: pd.Series,
    cfg: EnsembleConfig,
    selected_features: list[str],
    warmup: int = 220,
) -> dict:
    pos = int(close_full.index.get_loc(eval_slice.index[0]))
    end = int(close_full.index.get_loc(eval_slice.index[-1]))
    seed = close_full.iloc[max(0, pos - warmup) : end + 1]
    df = backtest_blended(seed, cfg, selected_features).loc[eval_slice.index]
    return enrich_stats(df)


def run_optuna_multiobjective(
    close_train: pd.Series,
    close_val: pd.Series,
    close_full: pd.Series,
    selected_features: list[str],
    n_trials: int = 120,
    random_state: int = 42,
) -> tuple[Any, pd.DataFrame, dict]:
    """Pareto: maximize Sharpe, minimize |max_drawdown| on validation."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    warmup = 220

    def objective(trial: optuna.Trial) -> tuple[float, float]:
        cfg = EnsembleConfig(
            tema_period=trial.suggest_int("tema_period", 12, 120),
            macd_fast=trial.suggest_int("macd_fast", 5, 20),
            macd_slow=trial.suggest_int("macd_slow", 21, 55),
            macd_signal=trial.suggest_int("macd_signal", 3, 12),
            long_threshold=trial.suggest_float("long_threshold", 0.1, 0.65),
            flat_threshold=trial.suggest_float("flat_threshold", 0.0, 0.2),
            tema_weight=trial.suggest_float("tema_weight", 0.2, 0.8),
        )
        if cfg.macd_fast >= cfg.macd_slow:
            raise optuna.TrialPruned()

        st = eval_config_on_slice(close_full, close_val, cfg, selected_features, warmup)
        sharpe_v = st.get("sharpe", float("nan"))
        dd_abs = abs(st.get("max_drawdown", 1.0))
        if np.isnan(sharpe_v):
            raise optuna.TrialPruned()
        trial.set_user_attr("calmar", st.get("calmar"))
        trial.set_user_attr("objective", st.get("objective"))
        return sharpe_v, dd_abs

    study = optuna.create_study(
        directions=["maximize", "minimize"],
        sampler=optuna.samplers.NSGAIISampler(seed=random_state),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    picked = pick_pareto_knee(study)
    trials_df = study.trials_dataframe()
    return study, trials_df, picked


def pick_pareto_knee(study: Any) -> dict:
    """Choose Pareto trial balancing Sharpe vs drawdown."""
    best_trials = study.best_trials
    if not best_trials:
        t = study.trials[0]
        return {"trial_number": t.number, "params": t.params, "sharpe": None, "max_drawdown": None}

    rows = []
    for t in best_trials:
        if len(t.values) < 2:
            continue
        sharpe_v, dd_abs = t.values[0], t.values[1]
        rows.append(
            {
                "trial_number": t.number,
                "params": t.params,
                "sharpe": sharpe_v,
                "max_drawdown": -dd_abs,
                "score": sharpe_v - 2.5 * dd_abs,
            }
        )
    if not rows:
        t = best_trials[0]
        return {
            "trial_number": t.number,
            "params": t.params,
            "sharpe": t.values[0] if t.values else None,
            "max_drawdown": -t.values[1] if t.values and len(t.values) > 1 else None,
        }
    best = max(rows, key=lambda r: r["score"])
    return best


def walk_forward_validate(
    close: pd.Series,
    cfg: EnsembleConfig,
    selected_features: list[str],
    n_splits: int = 5,
    min_train: int = 400,
    val_size: int = 120,
    test_size: int = 120,
    step: int = 120,
    boruta_iter: int = 60,
) -> pd.DataFrame:
    """Rolling walk-forward: Boruta on train, evaluate cfg on OOS test slice."""
    rows = []
    start = min_train
    fold = 0
    while start + val_size + test_size <= len(close) and fold < n_splits:
        train = close.iloc[:start]
        val = close.iloc[start : start + val_size]
        test = close.iloc[start + val_size : start + val_size + test_size]

        fold_features, _ = run_boruta_selection(train, max_iter=boruta_iter)
        features = fold_features or selected_features

        st_val = eval_config_on_slice(close, val, cfg, features)
        st_test = eval_config_on_slice(close, test, cfg, features)

        rows.append(
            {
                "fold": fold,
                "train_end": str(train.index[-1].date()),
                "test_start": str(test.index[0].date()),
                "test_end": str(test.index[-1].date()),
                "val_sharpe": st_val.get("sharpe"),
                "val_max_dd": st_val.get("max_drawdown"),
                "test_sharpe": st_test.get("sharpe"),
                "test_max_dd": st_test.get("max_drawdown"),
                "test_objective": st_test.get("objective"),
                "n_features": len(features),
            }
        )
        start += step
        fold += 1

    return pd.DataFrame(rows)


def export_live_config_from_research(
    start: str = "2018-01-01",
    boruta_iter: int = 100,
    optuna_trials: int = 120,
    walk_forward_splits: int = 5,
    config_path: Path | None = None,
) -> Path:
    from strategies.tema_macd_live_config import LiveConfigPayload, save_live_config

    close = load_btc_close(start)
    train, val, test = split_series(close)
    selected, _ = run_boruta_selection(train, max_iter=boruta_iter)

    mo_study, _, picked = run_optuna_multiobjective(
        train, val, close, selected, n_trials=optuna_trials
    )
    cfg = config_from_optuna_params(picked["params"])

    wf_df = walk_forward_validate(
        close, cfg, selected, n_splits=walk_forward_splits
    )
    holdout = evaluate_holdout(close, test, cfg, selected)

    wf_summary = {}
    if not wf_df.empty:
        wf_summary = {
            "folds": int(len(wf_df)),
            "medianTestSharpe": float(wf_df["test_sharpe"].median()),
            "medianTestMaxDd": float(wf_df["test_max_dd"].median()),
            "medianTestObjective": float(wf_df["test_objective"].median()),
        }

    payload = LiveConfigPayload.from_ensemble(
        cfg,
        selected,
        selection={
            "method": "optuna_multiobjective_pareto_knee",
            "sharpe": picked.get("sharpe"),
            "maxDrawdown": picked.get("max_drawdown"),
            "holdout": holdout,
            "trialNumber": picked.get("trial_number"),
        },
        wf=wf_summary or None,
    )
    return save_live_config(payload, config_path)


def run_optuna_study(
    close_train: pd.Series,
    close_val: pd.Series,
    close_full: pd.Series,
    selected_features: list[str],
    n_trials: int = 120,
    random_state: int = 42,
) -> tuple[Any, pd.DataFrame]:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    warmup = 220

    def objective(trial: optuna.Trial) -> float:
        cfg = EnsembleConfig(
            tema_period=trial.suggest_int("tema_period", 12, 120),
            macd_fast=trial.suggest_int("macd_fast", 5, 20),
            macd_slow=trial.suggest_int("macd_slow", 21, 55),
            macd_signal=trial.suggest_int("macd_signal", 3, 12),
            long_threshold=trial.suggest_float("long_threshold", 0.1, 0.65),
            flat_threshold=trial.suggest_float("flat_threshold", 0.0, 0.2),
            tema_weight=trial.suggest_float("tema_weight", 0.2, 0.8),
        )
        if cfg.macd_fast >= cfg.macd_slow:
            return -1e9

        try:
            if selected_features:
                pos = int(close_full.index.get_loc(close_val.index[0]))
                end = int(close_full.index.get_loc(close_val.index[-1]))
                seed = close_full.iloc[max(0, pos - warmup) : end + 1]
                df_val = backtest_blended(seed, cfg, selected_features).loc[close_val.index]
            else:
                df_val = backtest_with_seed(close_full, close_val, warmup, cfg)
            st = enrich_stats(df_val)
            trial.set_user_attr("sharpe", st.get("sharpe"))
            trial.set_user_attr("max_drawdown", st.get("max_drawdown"))
            trial.set_user_attr("calmar", st.get("calmar"))
            return st["objective"]
        except Exception:
            return -1e9

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=random_state))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    trials_df = study.trials_dataframe()
    return study, trials_df


def config_from_optuna_params(params: dict) -> EnsembleConfig:
    tw = float(params.get("tema_weight", 0.5))
    return EnsembleConfig(
        tema_period=int(params["tema_period"]),
        macd_fast=int(params["macd_fast"]),
        macd_slow=int(params["macd_slow"]),
        macd_signal=int(params["macd_signal"]),
        long_threshold=float(params["long_threshold"]),
        flat_threshold=float(params["flat_threshold"]),
        tema_weight=tw,
        macd_weight=1.0 - tw,
    )


def parameter_sensitivity(
    close: pd.Series,
    base_cfg: EnsembleConfig,
    selected_features: list[str],
    tema_delta: int = 12,
    th_delta: float = 0.1,
) -> pd.DataFrame:
    rows = []
    base_tp = base_cfg.tema_period
    base_lt = base_cfg.long_threshold

    for tp in range(max(10, base_tp - tema_delta), base_tp + tema_delta + 1, 4):
        for lt in np.arange(max(0.05, base_lt - th_delta), base_lt + th_delta + 0.01, 0.05):
            cfg = replace(base_cfg, tema_period=tp, long_threshold=round(float(lt), 2))
            df = backtest_blended(close, cfg, selected_features)
            st = enrich_stats(df)
            rows.append({"tema_period": tp, "long_threshold": lt, **st})

    return pd.DataFrame(rows)


def evaluate_holdout(
    close_full: pd.Series,
    close_test: pd.Series,
    cfg: EnsembleConfig,
    selected_features: list[str],
) -> dict:
    warmup = max(cfg.tema_period * 3, cfg.macd_slow + cfg.macd_signal) + 10
    pos = int(close_full.index.get_loc(close_test.index[0]))
    end = int(close_full.index.get_loc(close_test.index[-1]))
    seed = close_full.iloc[max(0, pos - warmup) : end + 1]
    df = backtest_blended(seed, cfg, selected_features).loc[close_test.index]
    return enrich_stats(df)


def run_full_pipeline(
    start: str = "2018-01-01",
    boruta_iter: int = 80,
    grid_max: int = 2000,
    optuna_trials: int = 100,
    use_multiobjective: bool = True,
    walk_forward_splits: int = 5,
) -> dict[str, Any]:
    close = load_btc_close(start)
    train, val, test = split_series(close)
    close_full = close

    selected, boruta_rank = run_boruta_selection(train, max_iter=boruta_iter)
    grid_df = wide_grid_search(train, val, close_full, selected, max_combos=grid_max)

    picked: dict | None = None
    if use_multiobjective:
        mo_study, mo_trials, picked = run_optuna_multiobjective(
            train, val, close_full, selected, n_trials=optuna_trials
        )
        best_cfg = config_from_optuna_params(picked["params"])
        study = mo_study
        trials_df = mo_trials
    else:
        study, trials_df = run_optuna_study(train, val, close_full, selected, n_trials=optuna_trials)
        best_cfg = config_from_optuna_params(study.best_params)

    sens = parameter_sensitivity(pd.concat([train, val]), best_cfg, selected)
    holdout = evaluate_holdout(close_full, test, best_cfg, selected)
    wf_df = walk_forward_validate(
        close_full, best_cfg, selected, n_splits=walk_forward_splits
    )

    return {
        "close": close,
        "train": train,
        "val": val,
        "test": test,
        "boruta_selected": selected,
        "boruta_ranking": boruta_rank,
        "grid_results": grid_df,
        "optuna_study": study,
        "optuna_trials": trials_df,
        "pareto_pick": picked,
        "best_config": best_cfg,
        "sensitivity": sens,
        "holdout_stats": holdout,
        "walk_forward": wf_df,
    }
