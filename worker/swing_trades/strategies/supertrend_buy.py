"""Supertrend Buy: Supertrend flips from short to long today, with volume confirmation."""
from __future__ import annotations

from typing import Iterable

from .base import SignalRow, Strategy


class SupertrendBuy(Strategy):
    key = "supertrend_buy"
    display_name = "Supertrend Buy"
    description = "Supertrend flip from short to long with volume confirmation."

    def evaluate(self, ctx) -> Iterable[SignalRow]:
        p = self.params
        require_volume = bool(p.get("require_volume_confirmation", True))
        vr_min = float(p.get("volume_ratio_min", 1.5))
        vol_min = float(p.get("volume_min_absolute", 50000))

        signals: list[SignalRow] = []
        for f in ctx.features:
            if not f.supertrend_flipped_long:
                continue
            if require_volume:
                if f.volume_ratio is None or f.volume_ratio < vr_min:
                    continue
                if f.volume < vol_min:
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
