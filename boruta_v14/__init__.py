"""BORUTA v1.4 signal engine reconstructed from the LLY daily chart.

The panel on that chart is a frozen Python model, not a discretionary overlay:

    Logic     OR_EVENT
    Members   TEMA / STC_REGIME / DOUBLE_KAMA
    Params    TEMA(7,137,100) OR STC_REGIME(23,50,a,25,80) OR DOUBLE_KAMA
    Model src LLY (frozen)
    run       20241013_153745

OR_EVENT is the same rule as ``TEMAStrategy`` and the triple-EMA notebook:
a long opens when any bullish cross fires, and it closes when any bearish
cross fires. Boruta grades the three members against shadow features.
The grid and the ±10 one-factor neighborhood are the ones already in
``TEMACD-master`` and ``TEMA-TEMPLATE_adjusted6_warmup``.
"""

from boruta_v14.model import PUBLISHED, FrozenModel, Replay, replay

__all__ = ["PUBLISHED", "FrozenModel", "Replay", "replay"]
