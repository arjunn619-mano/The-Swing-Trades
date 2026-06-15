import datetime as dt

from swing_trades.data_layer.models import PriceBar
from swing_trades.pipeline.features import compute_features


def _bar(day, o, h, low, c, v):
    return PriceBar(dt.date(2025, 1, day), o, h, low, c, v)


def test_none_with_insufficient_history():
    assert compute_features(1, [_bar(1, 10, 11, 9, 10, 100)]) is None


def test_computes_low_rsi_volume_surge_bullish_candle():
    bars = []
    for i in range(1, 15):  # 14 declining closes 119..106
        c = 120 - i
        bars.append(_bar(i, c + 0.5, c + 1, c - 1, c, 100_000))
    bars.append(_bar(15, 106, 109, 105.9, 108.5, 200_000))  # green up day + volume surge

    f = compute_features(1, bars)
    assert f is not None
    assert f.rsi is not None and f.rsi < 50
    assert f.volume_ratio is not None and f.volume_ratio > 1.5
    assert f.candle.is_bullish
    assert f.close == 108.5
