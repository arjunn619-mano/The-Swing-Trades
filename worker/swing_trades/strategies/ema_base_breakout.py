"""EMA Base Breakout: a green candle reclaiming the short EMAs (9/15) while price is
basing right at the long EMA (within +/-2.5%) and is still below the Supertrend line
(red zone) — an early pre-breakout setup before Supertrend confirms."""
from __future__ import annotations

from typing import Iterable

from .base import SignalRow, Strategy


class EmaBaseBreakout(Strategy):
    key = "ema_base_breakout"
    display_name = "EMA Base Breakout"
    description = (
        "Green candle back above EMA9/EMA15, price hugging the long EMA (+/-2.5%), "
        "still below Supertrend (red zone)."
    )

    def evaluate(self, ctx) -> Iterable[SignalRow]:
        p = self.params
        vicinity = float(p.get("long_ema_vicinity_pct", 0.025))
        vol_min = float(p.get("volume_min_absolute", 50000))

        signals: list[SignalRow] = []
        for f in ctx.features:
            # Need today's open and all three EMAs (ema_long is None until enough history).
            if f.open is None or f.ema_fast is None or f.ema_mid is None or f.ema_long is None:
                continue
            # 1. Green candle.
            if not (f.close > f.open):
                continue
            # 2. Short-term momentum: above EMA9 and EMA15.
            if not (f.close > f.ema_fast and f.close > f.ema_mid):
                continue
            # 3. Within +/-2.5% of the long EMA (basing near it).
            if f.ema_long == 0:
                continue
            if abs(f.close - f.ema_long) / f.ema_long > vicinity:
                continue
            # 4. Still below Supertrend (red zone) == direction -1.
            if f.supertrend_direction != -1:
                continue
            # 5. Liquidity floor.
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
