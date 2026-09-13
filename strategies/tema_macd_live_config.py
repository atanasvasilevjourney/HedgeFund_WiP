"""Load/save live TEMA+MACD BTC config for the Vercel terminal."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strategies.tema_macd_ensemble_btc import EnsembleConfig

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "terminal" / "config" / "tema_macd_btc_live.json"


@dataclass
class LiveConfigPayload:
    version: int
    updated_at: str
    ensemble: dict[str, Any]
    boruta_features: list[str]
    selection: dict[str, Any]
    walk_forward: dict[str, Any] | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": self.version,
                "updatedAt": self.updated_at,
                "ensemble": self.ensemble,
                "borutaFeatures": self.boruta_features,
                "selection": self.selection,
                "walkForward": self.walk_forward,
            },
            indent=2,
        )

    @staticmethod
    def from_ensemble(cfg: EnsembleConfig, features: list[str], selection: dict, wf: dict | None = None) -> LiveConfigPayload:
        return LiveConfigPayload(
            version=1,
            updated_at=datetime.now(timezone.utc).isoformat(),
            ensemble={
                "temaPeriod": cfg.tema_period,
                "macdFast": cfg.macd_fast,
                "macdSlow": cfg.macd_slow,
                "macdSignal": cfg.macd_signal,
                "temaWeight": cfg.tema_weight,
                "macdWeight": cfg.macd_weight,
                "longThreshold": cfg.long_threshold,
                "flatThreshold": cfg.flat_threshold,
                "longOnly": cfg.long_only,
                "costBps": cfg.cost_bps,
            },
            boruta_features=features,
            selection=selection,
            walk_forward=wf,
        )


def save_live_config(payload: LiveConfigPayload, path: Path | None = None) -> Path:
    out = path or DEFAULT_CONFIG_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload.to_json(), encoding="utf-8")
    return out


def load_live_config(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_CONFIG_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
