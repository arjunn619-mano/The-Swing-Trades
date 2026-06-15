from swing_trades.core.candles import (
    Candle,
    evaluate,
    is_bullish_engulfing,
    is_hammer,
    is_long_lower_wick,
    is_marubozu,
    is_strong_green,
)


def test_marubozu():
    c = Candle(100, 110, 100, 110)
    assert is_marubozu(c)
    res = evaluate(c)
    assert res.is_bullish and res.candle_type == "marubozu"
    assert res.patterns["strong_green"]


def test_hammer():
    c = Candle(100, 101.2, 95, 101)
    assert is_hammer(c)
    assert evaluate(c).is_bullish


def test_bullish_engulfing():
    prev = Candle(105, 106, 99, 100)   # red
    curr = Candle(99, 107, 98, 106)    # green, engulfs prev body
    assert is_bullish_engulfing(curr, prev)
    assert evaluate(curr, prev).candle_type == "bullish_engulfing"


def test_engulfing_needs_prev():
    curr = Candle(99, 107, 98, 106)
    assert not evaluate(curr).patterns["bullish_engulfing"]


def test_long_lower_wick():
    assert is_long_lower_wick(Candle(100, 101, 94, 100.5))


def test_strong_green_but_not_marubozu():
    c = Candle(100, 110, 100, 107)  # body 7 / range 10 = 0.7
    assert is_strong_green(c)
    assert not is_marubozu(c)


def test_plain_red_not_bullish():
    res = evaluate(Candle(110, 111, 99, 100))
    assert res.score == 0
    assert not res.is_bullish
    assert res.candle_type is None
