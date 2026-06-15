import datetime as dt

from swing_trades.core.candles import Candle
from swing_trades.core.candles import evaluate as evaluate_candle
from swing_trades.pipeline.features import InstrumentFeatures
from swing_trades.strategies import registered_strategies
from swing_trades.strategies.supertrend_buy import SupertrendBuy
from swing_trades.strategies.top_breakout import TopBreakout

_BULL = evaluate_candle(Candle(100, 110, 100, 109), Candle(101, 101, 99, 100))
_VOL = {"volume_ratio_min": 1.5, "volume_min_absolute": 50000}


def _feat(iid, *, rsi=60.0, vr=2.0, vol=100000, flip=False):
    return InstrumentFeatures(
        instrument_id=iid, trade_date=dt.date(2025, 8, 18), close=109.0, volume=vol,
        rsi=rsi, volume_ratio=vr, candle=_BULL,
        supertrend_direction=(1 if flip else -1), supertrend_flipped_long=flip,
    )


class _Ctx:
    def __init__(self, feats):
        self.features = feats
        self.trade_date = dt.date(2025, 8, 18)


def test_all_three_strategies_registered():
    assert {"bullish_vol_rsi_candle", "top_breakout", "supertrend_buy"} <= set(registered_strategies())


def test_top_breakout_qualifies_on_high_rsi():
    s = TopBreakout({**_VOL, "rsi_min": 55, "require_candle_pattern": True, "min_candle_score": 1})
    assert [x.instrument_id for x in s.evaluate(_Ctx([_feat(1, rsi=60)]))] == [1]


def test_top_breakout_rejects_low_rsi():
    s = TopBreakout({**_VOL, "rsi_min": 55})
    assert list(s.evaluate(_Ctx([_feat(1, rsi=50)]))) == []


def test_supertrend_buy_qualifies_on_flip():
    s = SupertrendBuy({**_VOL, "require_volume_confirmation": True})
    assert [x.instrument_id for x in s.evaluate(_Ctx([_feat(1, flip=True)]))] == [1]


def test_supertrend_buy_rejects_without_flip():
    s = SupertrendBuy({**_VOL, "require_volume_confirmation": True})
    assert list(s.evaluate(_Ctx([_feat(1, flip=False)]))) == []


def test_supertrend_buy_rejects_weak_volume():
    s = SupertrendBuy({**_VOL, "require_volume_confirmation": True})
    assert list(s.evaluate(_Ctx([_feat(1, flip=True, vr=1.0)]))) == []
