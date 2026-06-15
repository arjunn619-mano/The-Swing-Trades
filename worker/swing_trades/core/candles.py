"""Bullish candlestick patterns (Planning Pack/05_STRATEGIES.md).

Each pattern is a boolean over a single candle (engulfing needs the previous candle).
`evaluate()` returns the matched patterns, a score (count matched), the primary type,
and whether the candle is bullish overall.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Priority order when naming the single "candle_type" for a signal.
_PRIORITY = ["marubozu", "bullish_engulfing", "hammer", "strong_green", "long_lower_wick"]


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def is_green(self) -> bool:
        return self.close > self.open


@dataclass(frozen=True)
class CandleResult:
    patterns: dict[str, bool]
    score: int
    candle_type: Optional[str]
    is_bullish: bool


def _ratio(a: float, b: float) -> float:
    return a / b if b else 0.0


def is_marubozu(c: Candle) -> bool:
    """Green candle that is nearly all body — open≈low, close≈high (negligible wicks)."""
    if not c.is_green or c.range <= 0:
        return False
    return (
        _ratio(c.body, c.range) >= 0.90
        and _ratio(c.upper_wick, c.range) <= 0.10
        and _ratio(c.lower_wick, c.range) <= 0.10
    )


def is_strong_green(c: Candle) -> bool:
    """Green candle whose body is a large share of its range."""
    if not c.is_green or c.range <= 0:
        return False
    return _ratio(c.body, c.range) >= 0.60


def is_hammer(c: Candle) -> bool:
    """Small body, long lower wick (≥2× body), small upper wick — rejection of lower prices."""
    if c.range <= 0 or c.body <= 0:
        # a doji-ish/zero-body candle: treat a clear lower wick as a hammer-like rejection
        return c.lower_wick > 0 and c.upper_wick <= c.lower_wick * 0.25
    return (
        _ratio(c.body, c.range) <= 0.35
        and c.lower_wick >= 2 * c.body
        and c.upper_wick <= c.body
    )


def is_long_lower_wick(c: Candle) -> bool:
    """Lower wick at least twice the body and clearly longer than the upper wick."""
    if c.body <= 0:
        return c.lower_wick > 0 and c.lower_wick > c.upper_wick
    return c.lower_wick >= 2 * c.body and c.lower_wick > c.upper_wick


def is_bullish_engulfing(curr: Candle, prev: Optional[Candle]) -> bool:
    """Today's green body fully engulfs yesterday's red body."""
    if prev is None:
        return False
    prev_red = prev.close < prev.open
    return (
        prev_red
        and curr.is_green
        and curr.open <= prev.close
        and curr.close >= prev.open
        and curr.body > prev.body
    )


def evaluate(curr: Candle, prev: Optional[Candle] = None) -> CandleResult:
    patterns = {
        "marubozu": is_marubozu(curr),
        "bullish_engulfing": is_bullish_engulfing(curr, prev),
        "hammer": is_hammer(curr),
        "strong_green": is_strong_green(curr),
        "long_lower_wick": is_long_lower_wick(curr),
    }
    score = sum(1 for v in patterns.values() if v)
    candle_type = next((p for p in _PRIORITY if patterns.get(p)), None)
    return CandleResult(
        patterns=patterns,
        score=score,
        candle_type=candle_type,
        is_bullish=score >= 1,
    )
