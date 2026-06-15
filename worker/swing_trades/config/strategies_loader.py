"""Loads strategy definitions + parameters from strategies.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).with_name("strategies.yaml")
DEFAULT_HORIZON_DAYS = 100


@dataclass(frozen=True)
class StrategyConfig:
    key: str
    display_name: str
    description: str
    active: bool
    params: dict[str, Any] = field(default_factory=dict)


def _load_raw(path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "strategies" not in data:
        raise ValueError(f"{path}: expected a top-level 'strategies' mapping")
    return data


def load_strategy_configs(path: str | Path = DEFAULT_PATH) -> list[StrategyConfig]:
    data = _load_raw(path)
    configs: list[StrategyConfig] = []
    for key, cfg in data["strategies"].items():
        if not isinstance(cfg, dict):
            raise ValueError(f"strategy '{key}': expected a mapping of fields")
        configs.append(
            StrategyConfig(
                key=key,
                display_name=cfg.get("display_name", key),
                description=cfg.get("description", ""),
                active=bool(cfg.get("active", True)),
                params=dict(cfg.get("params", {})),
            )
        )
    return configs


def load_tracking_horizon_days(path: str | Path = DEFAULT_PATH) -> int:
    return int(_load_raw(path).get("tracking_horizon_days", DEFAULT_HORIZON_DAYS))
