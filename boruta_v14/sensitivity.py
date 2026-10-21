"""One-factor sensitivity neighborhood.

``TEMACD-master/optimization/sensitivity.py`` walks ``value ± ranges`` with
``ranges=10``, one parameter at a time. Four lengths on the frozen model have
a full ±10 neighborhood that never drops below 2:

    TEMA w2, TEMA w3, STC fast, STC slow
    4 x 20 = 80 neighbors

That is the ``80`` in the panel's ``MED (80/80 HIGH)``. The word in front is
how far in-sample Sharpe falls inside that neighborhood. The triple-EMA
notebook calls the drop HIGH once it exceeds 40%. v1.4 splits the rest:

    LOW   worst in-sample Sharpe drop <= 20%
    MED   drop <= 40%
    HIGH  drop >  40%

The parenthetical is how many of those neighbors are themselves still a
HIGH Sharpe, defined here as in-sample Sharpe >= 1.
"""

from __future__ import annotations

from dataclasses import dataclass

HIGH_SHARPE = 1.0
RADIUS = 10
# Four lengths whose ±10 neighborhood is entirely valid on the frozen model.
SENSITIVITY_KNOBS = ("tema_w2", "tema_w3", "stc_fast", "stc_slow")


@dataclass(frozen=True)
class SensitivityResult:
    label: str
    worst_drop_pct: float
    n_high: int
    n_total: int
    neighbor_sharpes: tuple[float, ...]


def format_sensitivity(worst_drop_pct: float, n_high: int, n_total: int) -> str:
    if n_total <= 0:
        return "n/a"
    if worst_drop_pct <= 20.0:
        word = "LOW"
    elif worst_drop_pct <= 40.0:
        word = "MED"
    else:
        word = "HIGH"
    return f"{word} ({n_high}/{n_total} HIGH)"


def neighbor_deltas(knobs: tuple[str, ...] = SENSITIVITY_KNOBS, radius: int = RADIUS) -> list[tuple[str, int]]:
    """``(knob, delta)`` pairs. The base point (delta 0) is not a neighbor."""
    out: list[tuple[str, int]] = []
    for knob in knobs:
        for delta in range(-radius, radius + 1):
            if delta == 0:
                continue
            out.append((knob, delta))
    return out
