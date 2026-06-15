"""Top Breakout: volume surge + high RSI (continuation) + bullish candle."""
from __future__ import annotations

from typing import Iterable

from .base import SignalRow, Strategy


class TopBreakout(Strategy):
    key = "top_breakout"
    display_name = "Top Breakout"
    description = "Volume surge + high RSI (continuation) + bullish candle."

    def evaluate(self, ctx) -> Iterable[SignalRow]:
        p = self.params
        vr_min = float(p.get("volume_ratio_min", 1.5))
        vol_min = float(p.get("volume_min_absolute", 50000))
        rsi_min = float(p.get("rsi_min", 55))
        require_candle = bool(p.get("require_candle_pattern", True))
        min_score = int(p.get("min_candle_score", 1))

        signals: list[SignalRow] = []
        for f in ctx.features:
            if f.rsi is None or f.volume_ratio is None:
                continue
            if f.volume_ratio < vr_min:
                continue
            if f.volume < vol_min:
                continue
            if f.rsi <= rsi_min:
                continue
            if require_candle and (not f.candle.is_bullish or f.candle.score < min_score):
                continue
            signals.append(
                SignalRow(
                    instrument_id=f.instrument_id,
                    close=f.close,
                    rsi=f.rsi,
                    volume_ratio=f.volume_ratio,
                    candle_type=f.candle.candle_type,
                )
            )
        return signals
