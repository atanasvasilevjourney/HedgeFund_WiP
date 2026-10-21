"""Boruta grades for the three OR_EVENT members.

Boruta (Kursa & Rudnicki) compares each real feature's random-forest
importance to the best shadow feature, which is that column shuffled.
Across iterations a binomial test turns the hit count into:

    STRONG  confirmed   importance beats the shadows
    MED     tentative   not separable from the shadows
    WEAK    rejected    importance loses to the shadows

The chart prints the surviving grades, weaker label first: ``MED / STRONG``.
"""

from __future__ import annotations

from math import exp, log, lgamma

import numpy as np
import pandas as pd

RANK = {"WEAK": 0, "MED": 1, "STRONG": 2}
GROUPS = {
    "TEMA": ("tema_state", "tema_spread"),
    "STC_REGIME": ("stc_state", "stc_value"),
    "DOUBLE_KAMA": ("kama_state", "kama_spread"),
}


def binomial_twosided_pvalue(k: int, n: int, p: float = 0.5) -> float:
    """Two-sided binomial p-value: mass of outcomes no more likely than ``k``."""
    if n <= 0:
        return 1.0
    k = int(min(max(k, 0), n))

    def logpmf(i: int) -> float:
        log_c = lgamma(n + 1) - lgamma(i + 1) - lgamma(n - i + 1)
        return log_c + i * log(p) + (n - i) * log(1.0 - p)

    logs = [logpmf(i) for i in range(n + 1)]
    target = logs[k]
    pivot = max(logs)
    acc = 0.0
    for lp in logs:
        if lp <= target + 1e-12:
            acc += exp(lp - pivot)
    return float(min(1.0, exp(pivot) * acc))


def grade_from_hits(hits: int, n_iter: int, alpha: float = 0.05) -> str:
    if n_iter <= 0:
        return "MED"
    p_value = binomial_twosided_pvalue(hits, n_iter)
    if p_value >= alpha:
        return "MED"
    if hits > n_iter / 2.0:
        return "STRONG"
    return "WEAK"


def summarize_grades(member_grades: dict[str, str]) -> str:
    """Chart order is the weaker surviving grade first: ``MED / STRONG``."""
    surviving = [g for g in member_grades.values() if g != "WEAK"]
    labels = [g for g in ("MED", "STRONG") if g in surviving]
    if labels:
        return " / ".join(labels)
    if member_grades:
        return "WEAK"
    return "n/a"


def _hit_mask(X: np.ndarray, y: np.ndarray, rng: np.random.Generator, n_estimators: int) -> np.ndarray:
    from sklearn.ensemble import RandomForestClassifier

    n_features = X.shape[1]
    shadow = np.empty_like(X)
    for j in range(n_features):
        shadow[:, j] = rng.permutation(X[:, j])
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=5,
        min_samples_leaf=5,
        random_state=int(rng.integers(0, 1_000_000)),
        n_jobs=1,
        class_weight="balanced",
    )
    model.fit(np.hstack([X, shadow]), y)
    importance = model.feature_importances_
    threshold = float(importance[n_features:].max())
    return importance[:n_features] > threshold


def boruta_grades(
    features: pd.DataFrame,
    y: pd.Series,
    n_iter: int = 21,
    n_estimators: int = 80,
    seed: int = 7,
    alpha: float = 0.05,
) -> dict[str, str]:
    """Grade each column. A constant label, or no finite rows, is MED."""
    frame = features.copy()
    frame["__y"] = y
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    names = [c for c in features.columns]
    if frame.empty or frame["__y"].nunique() < 2:
        return {name: "MED" for name in names}
    X = frame[names].to_numpy(dtype=float)
    target = frame["__y"].to_numpy(dtype=int)
    rng = np.random.default_rng(seed)
    hits = np.zeros(len(names), dtype=int)
    for _ in range(n_iter):
        hits += _hit_mask(X, target, rng, n_estimators).astype(int)
    return {name: grade_from_hits(int(hits[i]), n_iter, alpha) for i, name in enumerate(names)}


def member_feature_frame(
    index: pd.Index,
    tema_state: pd.Series,
    tema_spread: pd.Series,
    stc_state: pd.Series,
    stc_value: pd.Series,
    kama_state: pd.Series,
    kama_spread: pd.Series,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tema_state": tema_state,
            "tema_spread": tema_spread,
            "stc_state": stc_state,
            "stc_value": stc_value,
            "kama_state": kama_state,
            "kama_spread": kama_spread,
        },
        index=index,
    ).astype(float)


def grade_members(feature_grades: dict[str, str]) -> dict[str, str]:
    """A member takes the strongest grade among the columns that belong to it."""
    out = {}
    for member, columns in GROUPS.items():
        grades = [feature_grades[c] for c in columns if c in feature_grades]
        if not grades:
            out[member] = "MED"
            continue
        out[member] = max(grades, key=lambda g: RANK[g])
    return out
