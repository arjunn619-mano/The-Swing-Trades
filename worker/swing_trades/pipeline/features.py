"""Compute the latest-day feature set per instrument from its trailing price history.
Strategies read these features; they never touch the DB or pandas directly."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional, Sequence

import pandas as pd

from ..core import indicators as ind
from ..core.candles import Candle, CandleResult
from ..core.candles import evaluate as evaluate_candle
from ..data_layer.models import PriceBar


@dataclass(frozen=True)
class InstrumentFeatures:
    instrument_id: int
    trade_date: _dt.date
    close: float
    volume: int
    rsi: Optional[float]
    volume_ratio: Optional[float]
    candle: CandleResult
    supertrend_direction: Optional[int] = None
    supertrend_flipped_long: bool = False
    open: Optional[float] = None
    ema_fast: Optional[float] = None   # short EMA (default 9)
    ema_mid: Optional[float] = None    # mid EMA (default 15)
    ema_long: Optional[float] = None   # long EMA (default 200); None until enough history


def compute_features(
    instrument_id: int,
    bars: Sequence[PriceBar],
    *,
    rsi_period: int = 14,
    volume_lookback: int = 14,
    atr_period: int = 10,
    atr_multiplier: float = 3.0,
    ema_fast: int = 9,
    ema_mid: int = 15,
    ema_long: int = 200,
) -> Optional[InstrumentFeatures]:
    """Build features for the most recent bar. Returns None if there isn't enough history
    to form even a candle (needs >= 2 bars). RSI/volume_ratio are None until their windows fill."""
    if len(bars) < 2:
        return None

    df = pd.DataFrame(
        {
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )

    rsi_series = ind.rsi(df["close"], rsi_period)
    vr_series = ind.volume_ratio(df["volume"], volume_lookback)
    st = ind.supertrend(df["high"], df["low"], df["close"], atr_period, atr_multiplier)
    ema_fast_v = ind.ema(df["close"], ema_fast).iloc[-1]
    ema_mid_v = ind.ema(df["close"], ema_mid).iloc[-1]
    ema_long_v = ind.ema(df["close"], ema_long).iloc[-1]

    last, prev = bars[-1], bars[-2]
    candle = evaluate_candle(
        Candle(last.open, last.high, last.low, last.close),
        Candle(prev.open, prev.high, prev.low, prev.close),
    )

    rsi_v = rsi_series.iloc[-1]
    vr_v = vr_series.iloc[-1]
    dir_now = st["direction"].iloc[-1]
    dir_prev = st["direction"].iloc[-2]
    flipped_long = (not pd.isna(dir_now)) and (not pd.isna(dir_prev)) and dir_prev == -1 and dir_now == 1

    return InstrumentFeatures(
        instrument_id=instrument_id,
        trade_date=last.trade_date,
        close=float(last.close),
        volume=int(last.volume),
        rsi=(None if pd.isna(rsi_v) else float(rsi_v)),
        volume_ratio=(None if pd.isna(vr_v) else float(vr_v)),
        candle=candle,
        supertrend_direction=(None if pd.isna(dir_now) else int(dir_now)),
        supertrend_flipped_long=bool(flipped_long),
        open=float(last.open),
        ema_fast=(None if pd.isna(ema_fast_v) else float(ema_fast_v)),
        ema_mid=(None if pd.isna(ema_mid_v) else float(ema_mid_v)),
        ema_long=(None if pd.isna(ema_long_v) else float(ema_long_v)),
    )
