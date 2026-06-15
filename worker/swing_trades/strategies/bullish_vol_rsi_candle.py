"""Bottom Breakout: volume surge + low RSI + bullish candle. The first strategy shipped
end-to-end (the lean vertical slice)."""
from __future__ import annotations

from typing import Iterable

from .base import SignalRow, Strategy


class BullishVolRsiCandle(Strategy):
    key = "bullish_vol_rsi_candle"
    display_name = "Bottom Breakout"
    description = "Volume surge + low RSI + bullish candle (oversold reversal setup)."

    def evaluate(self, ctx) -> Iterable[SignalRow]:
        p = self.params
        vr_min = float(p.get("volume_ratio_min", 1.5))
        vol_min = float(p.get("volume_min_absolute", 50000))
        rsi_max = float(p.get("rsi_max", 50))
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
            if f.rsi >= rsi_max:
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
