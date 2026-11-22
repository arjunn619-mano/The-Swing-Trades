"""Price-gap fill before the daily scan (swing_trades/pipeline/gapfill.py)."""
import datetime as dt

from swing_trades.data_layer.models import PriceBar
from swing_trades.pipeline.gapfill import fill_price_gap, gap_window
from swing_trades.pipeline.store import FakeStore, InstrumentRef

D = dt.date


class Client:
    def __init__(self, fail_ids=()):
        self.calls, self.fail_ids = [], set(fail_ids)

    def historical_daily(self, security_id, segment, from_date, to_date):
        self.calls.append((security_id, from_date, to_date))
        if security_id in self.fail_ids:
            raise RuntimeError("dhan 500")
        days = [D(2026, 11, 2) + dt.timedelta(days=k) for k in range(22)]
        return [PriceBar(d, 10, 11, 9, 10.5, 1000) for d in days if d.weekday() < 5 and D.fromisoformat(from_date) <= d]


def store_with(last_success):
    s = FakeStore()
    for i in (1, 2):
        s.add_instrument(InstrumentRef(id=i, isin="IN%d" % i, security_id=str(100 + i), exchange_segment="NSE_EQ"))
    s.register_strategy("x", 7)
    if last_success:
        rid = s.start_scan_run(7, last_success)
        s.finish_scan_run(rid, "success", 0)
    return s


def test_no_gap_on_a_normal_day():
    assert gap_window(D(2026, 11, 20), D(2026, 11, 23)) is None        # Fri scanned, Mon scan: no gap
    assert gap_window(None, D(2026, 11, 23)) is None                   # fresh DB is Bootstrap's job


def test_gap_after_the_november_pause():
    assert gap_window(D(2026, 10, 30), D(2026, 11, 23)) == (D(2026, 10, 31), D(2026, 11, 23))


def test_fill_uses_one_client_and_skips_todays_bar():
    s, c = store_with(D(2026, 10, 30)), Client()
    r = fill_price_gap(s, c, D(2026, 11, 23), sleep=lambda _: None)
    assert r["filled"] == 2 and r["failed"] == 0 and r["gap_trading_days"] >= 10
    assert all(call[1:] == ("2026-10-31", "2026-11-23") for call in c.calls)
    assert max(d for (_i, d) in s.prices) < D(2026, 11, 23)            # today's bar still comes from the live quote


def test_a_failing_stock_does_not_stop_the_rest():
    s, c = store_with(D(2026, 10, 30)), Client(fail_ids={"101"})
    r = fill_price_gap(s, c, D(2026, 11, 23), sleep=lambda _: None)
    assert r == {"gap_trading_days": r["gap_trading_days"], "filled": 1, "failed": 1, "from": "2026-10-31"}


def test_normal_day_costs_no_dhan_calls():
    s, c = store_with(D(2026, 11, 20)), Client()
    assert fill_price_gap(s, c, D(2026, 11, 23), sleep=lambda _: None)["gap_trading_days"] == 0 and c.calls == []
