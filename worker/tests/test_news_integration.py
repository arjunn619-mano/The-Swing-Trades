"""End-to-end: capture a BSE order-win -> news_events, then run the EOD scan with enable_news
-> the event is priced + enrolled into the news_positive tracker (entry = today's close, catalyst
tag stored, 100-day observation started), and re-runs are idempotent."""
import datetime as dt
import json

from swing_trades.data_layer.models import UniverseInstrument
from swing_trades.data_layer.news.capture import capture_news
from swing_trades.data_layer.news.resolver import InstrumentResolver
from swing_trades.data_layer.news.sources.base import FetchResult
from swing_trades.data_layer.news.sources.bse import BseAdapter
from swing_trades.pipeline.scan import run_scan
from swing_trades.pipeline.store import FakeStore

TD = dt.date(2026, 7, 13)  # a Monday trading day

R = InstrumentResolver([
    UniverseInstrument(isin="INE002A01018", security_id="2885", exchange_pref="NSE", exchange_segment="NSE_EQ",
                       nse_symbol="RELIANCE", bse_scrip_code="500325", symbol_name="Reliance Industries",
                       series="EQ", lot_size=1, asm_gsm_flag="N"),
])

BSE_ORDER = json.dumps({"Table": [
    {"SCRIP_CD": 500325, "SLONGNAME": "Reliance Industries Ltd", "CATEGORYNAME": "Company Update",
     "SUBCATNAME": "Award of Order / Receipt of Order", "HEADLINE": "Reliance bags Rs 5000 cr order",
     "NEWS_DT": "2026-07-13T15:00:00", "NEWSID": "b1"},
], "Table1": [{"ROWCNT": 1}]})


def fake_get(url, headers=None, params=None):
    return FetchResult(200, "application/json", BSE_ORDER)


class FakeClient:
    def __init__(self, q):
        self.q = q

    def quote(self, batch):
        data = {}
        for seg, ids in batch.items():
            data.setdefault(seg, {})
            for sid in ids:
                if str(sid) in self.q:
                    data[seg][str(sid)] = self.q[str(sid)]
        return {"data": data, "status": "success"}


def test_capture_then_scan_enrols_news_positive():
    s = FakeStore()
    s.register_strategy("news_positive", 99)

    # 1. capture: a BSE order-win becomes one ORDER_WIN news_event (and adds Reliance to the universe)
    capture_news(TD, adapters=[BseAdapter()], http_get=fake_get, resolver=R, store=s,
                 is_trading_day=True, log_only_count=True)
    assert len(s.news_events) == 1
    rel = next(r for r in s.instruments if r.isin == "INE002A01018")  # expand-on-the-fly added it

    # 2. scan: quote Reliance, then price + enrol the pending news_event
    client = FakeClient({"2885": {"ohlc": {"open": 3000, "high": 3050, "low": 2990, "close": 3025}, "volume": 1_000_000}})
    summary = run_scan(TD, store=s, dhan_client=client, strategy_configs=[], horizon_days=100, enable_news=True)

    assert summary.status == "success"
    assert summary.news["created"] == 1
    entry = s.tracker[(rel.id, 99)]
    assert entry["entry_close"] == 3025            # entry = today's EOD close (Rule 3)
    assert entry["catalyst_tag"] == "ORDER_WIN"
    assert (rel.id, 99, TD) in s.observations      # 100-day curve started day 0


def test_rerun_scan_does_not_double_enrol():
    s = FakeStore()
    s.register_strategy("news_positive", 99)
    capture_news(TD, adapters=[BseAdapter()], http_get=fake_get, resolver=R, store=s, log_only_count=True)
    client = FakeClient({"2885": {"ohlc": {"open": 3000, "high": 3050, "low": 2990, "close": 3025}, "volume": 1_000_000}})
    run_scan(TD, store=s, dhan_client=client, strategy_configs=[], horizon_days=100, enable_news=True)
    summary2 = run_scan(TD, store=s, dhan_client=client, strategy_configs=[], horizon_days=100, enable_news=True)
    assert summary2.news["created"] == 0           # event already enrolled -> not re-created
    assert len([k for k in s.tracker if k[1] == 99]) == 1


def test_scan_without_enable_news_is_untouched():
    s = FakeStore()
    s.register_strategy("news_positive", 99)
    capture_news(TD, adapters=[BseAdapter()], http_get=fake_get, resolver=R, store=s, log_only_count=True)
    client = FakeClient({"2885": {"ohlc": {"open": 3000, "high": 3050, "low": 2990, "close": 3025}, "volume": 1_000_000}})
    summary = run_scan(TD, store=s, dhan_client=client, strategy_configs=[], horizon_days=100)  # enable_news default False
    assert summary.news == {}                       # news untouched when the flag is off
    assert not any(k[1] == 99 for k in s.tracker)
