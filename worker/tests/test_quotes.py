import datetime as dt

from swing_trades.data_layer.models import UniverseInstrument
from swing_trades.data_layer.quotes import batch_instruments, parse_quote_response


def _mk(i: int, segment: str = "NSE_EQ") -> UniverseInstrument:
    return UniverseInstrument(
        isin=f"X{i}",
        security_id=str(i),
        exchange_pref="NSE" if segment == "NSE_EQ" else "BSE",
        exchange_segment=segment,
        nse_symbol="S",
        bse_scrip_code=None,
        symbol_name="S",
        series="EQ",
        lot_size=1,
        asm_gsm_flag="N",
    )


def test_parse_quote_extracts_ohlcv():
    payload = {
        "data": {
            "NSE_EQ": {
                "2885": {
                    "last_price": 1400,
                    "ohlc": {"open": 1390, "high": 1410, "low": 1385, "close": 1400},
                    "volume": 123456,
                    "average_price": 1399,
                }
            }
        },
        "status": "success",
    }
    out = parse_quote_response(payload, dt.date(2025, 8, 18))
    bar = out["2885"]
    assert bar.open == 1390 and bar.high == 1410 and bar.close == 1400
    assert bar.volume == 123456
    assert bar.trade_date == dt.date(2025, 8, 18)


def test_batch_splits_at_1000():
    batches = batch_instruments([_mk(i) for i in range(2500)], max_per_call=1000)
    counts = [sum(len(v) for v in b.values()) for b in batches]
    assert counts == [1000, 1000, 500]


def test_batch_groups_by_segment():
    batches = batch_instruments([_mk(1, "NSE_EQ"), _mk(2, "BSE_EQ"), _mk(3, "NSE_EQ")])
    assert len(batches) == 1
    b = batches[0]
    assert set(b) == {"NSE_EQ", "BSE_EQ"}
    assert b["NSE_EQ"] == [1, 3] and b["BSE_EQ"] == [2]
