import datetime as dt

from swing_trades.data_layer.dhan_client import DhanDataClient
from swing_trades.data_layer.models import OptionContract
from swing_trades.data_layer.option_chain import parse_option_chain, underlying_ref

from test_dhan_client import FakeResp, FakeSession

PAYLOAD = {
    "status": "success",
    "data": {
        "last_price": 1402.5,
        "oc": {
            "1400.000000": {
                "ce": {
                    "greeks": {"delta": 0.52, "theta": -1.2, "gamma": 0.003, "vega": 4.1},
                    "implied_volatility": 18.5, "last_price": 35.4,
                    "oi": 120000, "previous_oi": 100000,
                    "previous_close_price": 30.0, "volume": 250000,
                },
                "pe": {
                    "greeks": {"delta": -0.48, "theta": -1.1, "gamma": 0.003, "vega": 4.0},
                    "implied_volatility": 19.2, "last_price": 33.0,
                    "oi": 90000, "previous_oi": 95000,
                    "previous_close_price": 36.0, "volume": 80000,
                },
            },
            "1420.000000": {
                # empty/illiquid CE — all zeros, still kept
                "ce": {"greeks": {}, "implied_volatility": 0, "last_price": 0,
                       "oi": 0, "previous_oi": 0, "volume": 0},
                "pe": {"greeks": {"delta": -0.6}, "implied_volatility": 20.0,
                       "last_price": 48.0, "oi": 50000, "previous_oi": 40000, "volume": 120000},
            },
        },
    },
}


def _q(snap, strike, opt_type):
    return next(q for q in snap.quotes if q.strike == strike and q.option_type == opt_type)


def test_parse_returns_all_sides_and_underlying():
    snap = parse_option_chain(PAYLOAD, expiry="2026-07-31")
    assert len(snap.quotes) == 4  # 2 strikes x CE/PE
    assert snap.underlying_last_price == 1402.5
    assert snap.expiry == "2026-07-31"


def test_quote_fields_and_oi_change():
    ce = _q(parse_option_chain(PAYLOAD, expiry="2026-07-31"), 1400.0, "CE")
    assert ce.last_price == 35.4
    assert ce.oi == 120000
    assert ce.volume == 250000
    assert ce.implied_volatility == 18.5
    assert ce.delta == 0.52 and ce.vega == 4.1
    assert abs(ce.oi_change_pct - 0.2) < 1e-9  # (120000-100000)/100000


def test_empty_side_kept_with_zeros_and_none_oi_change():
    ce = _q(parse_option_chain(PAYLOAD, expiry="2026-07-31"), 1420.0, "CE")
    assert ce.last_price == 0 and ce.oi == 0 and ce.volume == 0
    assert ce.previous_oi == 0
    assert ce.oi_change_pct is None  # no previous OI -> undefined


def test_underlying_ref_index_vs_stock():
    idx = OptionContract("35022", "NIFTY", "13", "NSE", "OPTIDX", dt.date(2026, 7, 28), 29300.0, "CE", 75, "x")
    stk = OptionContract("538591", "RELIANCE", "2885", "NSE", "OPTSTK", dt.date(2026, 7, 31), 1400.0, "CE", 500, "y")
    assert underlying_ref(idx) == (13, "IDX_I")
    assert underlying_ref(stk) == (2885, "NSE_EQ")


def test_client_option_chain_posts_expected_body():
    sess = FakeSession([FakeResp(PAYLOAD)])
    client = DhanDataClient("JWT", "C1", session=sess)
    resp = client.option_chain(13, "IDX_I", "2026-07-31")
    url, body, _headers = sess.calls[0]
    assert url.endswith("/optionchain")
    assert body == {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": "2026-07-31"}
    assert resp["data"]["last_price"] == 1402.5


def test_client_expiry_list_parses_data():
    sess = FakeSession([FakeResp({"data": ["2026-07-31", "2026-08-28"], "status": "success"})])
    client = DhanDataClient("JWT", "C1", session=sess)
    out = client.option_expiry_list(13, "IDX_I")
    assert out == ["2026-07-31", "2026-08-28"]
    url, body, _headers = sess.calls[0]
    assert url.endswith("/optionchain/expirylist")
    assert body == {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}
