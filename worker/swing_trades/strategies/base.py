"""Strategy framework. A strategy subclasses `Strategy`, sets a `key`, and implements
`evaluate(ctx)`. Subclasses auto-register via __init_subclass__, so adding a strategy is
(1) create the class, (2) add a YAML entry — no manual registry edits.

Concrete strategies are added in Phase 3 (lean slice: bullish_vol_rsi_candle first).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Optional

_REGISTRY: dict[str, type["Strategy"]] = {}


@dataclass(frozen=True)
class SignalRow:
    """One qualifying stock under a strategy on a given trade date."""

    instrument_id: int
    close: float
    rsi: Optional[float] = None
    volume_ratio: Optional[float] = None
    candle_type: Optional[str] = None


class Strategy(ABC):
    key: str = ""
    display_name: str = ""
    description: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "key", ""):
            if cls.key in _REGISTRY and _REGISTRY[cls.key] is not cls:
                raise ValueError(f"Duplicate strategy key: {cls.key!r}")
            _REGISTRY[cls.key] = cls

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params: dict[str, Any] = dict(params or {})

    @abstractmethod
    def evaluate(self, ctx: Any) -> Iterable[SignalRow]:
        """Yield a SignalRow for every instrument that qualifies under this strategy."""
        raise NotImplementedError


def registered_strategies() -> dict[str, type[Strategy]]:
    return dict(_REGISTRY)
