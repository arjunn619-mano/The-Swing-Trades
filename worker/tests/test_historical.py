import datetime as dt

import pytest

from swing_trades.data_layer.historical import parse_historical_response


def test_parse_basic():
    payload = {
        "open": [100, 101],
        "high": [102, 103],
        "low": [99, 100],
        "close": [101, 102],
        "volume": [1000, 2000],
        "timestamp": [1704067200, 1704153600],  # 2024-01-01, 2024-01-02 (UTC midnight)
        "open_interest": [0, 0],
    }
    bars = parse_historical_response(payload)
    assert len(bars) == 2
    assert bars[0].open == 100.0 and bars[0].close == 101.0 and bars[0].volume == 1000
    assert bars[0].trade_date == dt.date(2024, 1, 1)
    assert bars[1].trade_date == dt.date(2024, 1, 2)


def test_empty_payload_yields_no_bars():
    assert parse_historical_response({}) == []


def test_length_mismatch_raises():
    payload = {
        "open": [1, 2],
        "high": [1],
        "low": [1, 2],
        "close": [1, 2],
        "volume": [1, 2],
        "timestamp": [1704067200, 1704153600],
    }
    with pytest.raises(ValueError):
        parse_historical_response(payload)


def test_missing_array_raises():
    with pytest.raises(ValueError):
        parse_historical_response({"open": [1], "high": [1], "low": [1], "close": [1]})
