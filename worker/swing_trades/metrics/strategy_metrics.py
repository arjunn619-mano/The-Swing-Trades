"""Edge metrics (M1/M2). Raw hit rate alone can't show edge, so we also report it against a
base rate (excess), plus expectancy and win/loss size. Pure functions — given a list of
outcome returns, produce the aggregate. The index (Nifty) benchmark is a documented hook:
pass `base_returns` for the universe base rate; index wiring comes when Nifty is loaded."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Optional, Sequence


@dataclass(frozen=True)
class StrategyMetrics:
    horizon_days: int
    sample_size: int
    hit_rate: Optional[float] = None
    base_rate: Optional[float] = None
    excess_hit_rate: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    expectancy: Optional[float] = None
    median_return: Optional[float] = None
    hit_rate_at_5pct: Optional[float] = None
    hit_rate_at_10pct: Optional[float] = None


def compute_strategy_metrics(
    returns: Sequence[Optional[float]],
    *,
    base_returns: Optional[Sequence[Optional[float]]] = None,
    horizon_days: int = 100,
) -> StrategyMetrics:
    rs = [r for r in returns if r is not None]
    n = len(rs)
    if n == 0:
        return StrategyMetrics(horizon_days=horizon_days, sample_size=0)

    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    hit_rate = len(wins) / n

    base_rate: Optional[float] = None
    excess: Optional[float] = None
    if base_returns:
        b = [r for r in base_returns if r is not None]
        if b:
            base_rate = sum(1 for r in b if r > 0) / len(b)
            excess = hit_rate - base_rate

    return StrategyMetrics(
        horizon_days=horizon_days,
        sample_size=n,
        hit_rate=hit_rate,
        base_rate=base_rate,
        excess_hit_rate=excess,
        avg_win=(mean(wins) if wins else 0.0),
        avg_loss=(mean(losses) if losses else 0.0),
        expectancy=mean(rs),  # == win%*avg_win + loss%*avg_loss
        median_return=median(rs),
        hit_rate_at_5pct=sum(1 for r in rs if r >= 0.05) / n,
        hit_rate_at_10pct=sum(1 for r in rs if r >= 0.10) / n,
    )
