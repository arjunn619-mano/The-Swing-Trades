import datetime as dt

from swing_trades.core.candles import Candle
from swing_trades.core.candles import evaluate as evaluate_candle
from swing_trades.pipeline.features import InstrumentFeatures
from swing_trades.strategies import registered_strategies
from swing_trades.strategies.bullish_vol_rsi_candle import BullishVolRsiCandle

_PARAMS = {
    "volume_ratio_min": 1.5,
    "volume_min_absolute": 50000,
    "rsi_max": 50,
    "require_candle_pattern": True,
    "min_candle_score": 1,
}
_BULLISH = evaluate_candle(Candle(100, 110, 100, 109), Candle(101, 101, 99, 100))  # marubozu-ish


def _feat(iid, rsi, vr, vol):
    return InstrumentFeatures(
        instrument_id=iid, trade_date=dt.date(2025, 8, 18), close=109.0,
        volume=vol, rsi=rsi, volume_ratio=vr, candle=_BULLISH,
    )


class _Ctx:
    def __init__(self, feats):
        self.features = feats
        self.trade_date = dt.date(2025, 8, 18)


def test_strategy_is_registered():
    assert "bullish_vol_rsi_candle" in registered_strategies()


def test_qualifies_on_low_rsi_surge_bullish():
    sigs = list(BullishVolRsiCandle(_PARAMS).evaluate(_Ctx([_feat(1, 40, 2.0, 100000)])))
    assert [s.instrument_id for s in sigs] == [1]
    assert sigs[0].candle_type is not None


def test_rejects_high_rsi():
    assert list(BullishVolRsiCandle(_PARAMS).evaluate(_Ctx([_feat(1, 60, 2.0, 100000)]))) == []


def test_rejects_weak_volume_ratio():
    assert list(BullishVolRsiCandle(_PARAMS).evaluate(_Ctx([_feat(1, 40, 1.2, 100000)]))) == []


def test_rejects_below_absolute_volume_floor():
    assert list(BullishVolRsiCandle(_PARAMS).evaluate(_Ctx([_feat(1, 40, 2.0, 1000)]))) == []


def test_rejects_missing_indicators():
    assert list(BullishVolRsiCandle(_PARAMS).evaluate(_Ctx([_feat(1, None, None, 100000)]))) == []
