"""End-to-end capture: BSE fetch -> Stage-A -> tag -> resolve -> Stage-B ledger. Proves the
deterministic (no-LLM) backbone enrols Tier-A catalysts and defers Tier-B/C, and that the LLM path
closes the rest. Idempotent across re-runs."""
import datetime as dt
import json

from swing_trades.data_layer.models import UniverseInstrument
from swing_trades.data_layer.news.capture import capture_news
from swing_trades.data_layer.news.resolver import InstrumentResolver
from swing_trades.data_layer.news.sources.base import FetchResult
from swing_trades.data_layer.news.sources.bse import BseAdapter
from swing_trades.data_layer.news.sources.rss import RssAdapter
from swing_trades.pipeline.store import FakeStore

TD = dt.date(2026, 7, 13)

UNI = [
    UniverseInstrument(isin="INE002A01018", security_id="2885", exchange_pref="NSE", exchange_segment="NSE_EQ",
                       nse_symbol="RELIANCE", bse_scrip_code="500325", symbol_name="Reliance Industries",
                       series="EQ", lot_size=1, asm_gsm_flag="N"),
    UniverseInstrument(isin="INE467B01029", security_id="11536", exchange_pref="NSE", exchange_segment="NSE_EQ",
                       nse_symbol="TCS", bse_scrip_code="532540", symbol_name="Tata Consultancy Services",
                       series="EQ", lot_size=1, asm_gsm_flag="N"),
]
R = InstrumentResolver(UNI)

BSE = json.dumps({"Table": [
    {"SCRIP_CD": 500325, "SLONGNAME": "Reliance Industries Ltd", "CATEGORYNAME": "Company Update",
     "SUBCATNAME": "Award of Order / Receipt of Order", "HEADLINE": "Reliance bags Rs 5000 cr EPC order",
     "NEWS_DT": "2026-07-13T15:00:00", "NEWSID": "b1"},
    {"SCRIP_CD": 532540, "SLONGNAME": "Tata Consultancy Services Ltd", "CATEGORYNAME": "Result",
     "SUBCATNAME": "Financial Results", "HEADLINE": "TCS Q1 net profit up 12 percent",
     "NEWS_DT": "2026-07-13T14:00:00", "NEWSID": "b2"},
], "Table1": [{"ROWCNT": 2}]})


_EMPTY = json.dumps({"Table": [], "Table1": [{"ROWCNT": 0}]})


def fake_get(body=BSE, status=200, ct="application/json"):
    def _get(url, headers=None, params=None):
        page = str((params or {}).get("pageno", "1"))
        return FetchResult(status, ct, body if page == "1" else _EMPTY)  # page-aware so pagination stops
    return _get


def test_deterministic_backbone_enrols_tier_a_defers_rest():
    s = FakeStore()
    res = capture_news(TD, adapters=[BseAdapter()], http_get=fake_get(), resolver=R, store=s,
                       is_trading_day=True, log_only_count=True)
    assert res.tier_a == 1 and res.new_events == 1     # the order win enrolled deterministically
    assert res.llm_deferred == 1                       # the result deferred (no LLM)
    assert len(s.news_events) == 1
    ev = next(iter(s.news_events.values()))
    assert ev["catalyst_tag"] == "ORDER_WIN" and ev["isin"] == "INE002A01018"


def test_llm_closes_result_as_results_positive():
    s = FakeStore()

    def llm(reps):
        return [("", "results", "positive") for _ in reps]

    res = capture_news(TD, adapters=[BseAdapter()], http_get=fake_get(), resolver=R, store=s,
                       is_trading_day=True, llm_classify=llm, log_only_count=True)
    assert res.tier_a == 1 and res.llm_classified == 1
    tags = {e["catalyst_tag"] for e in s.news_events.values()}
    assert tags == {"ORDER_WIN", "RESULTS_POSITIVE"}


def test_llm_drops_negative_result():
    s = FakeStore()

    def llm(reps):
        return [("", "results", "negative") for _ in reps]  # bad numbers -> not enrolled

    res = capture_news(TD, adapters=[BseAdapter()], http_get=fake_get(), resolver=R, store=s,
                       is_trading_day=True, llm_classify=llm, log_only_count=True)
    assert res.dropped_non_positive == 1
    assert {e["catalyst_tag"] for e in s.news_events.values()} == {"ORDER_WIN"}


RSS_XML = (
    '<?xml version="1.0"?><rss version="2.0"><channel>'
    "<item><title>Reliance Industries bags Rs 10000 cr highway order from NHAI</title>"
    "<link>https://news.google.com/rss/articles/abc123</link>"
    "<pubDate>Mon, 13 Jul 2026 10:00:00 GMT</pubDate></item>"
    "</channel></rss>"
)


def test_rss_headline_resolved_via_llm_extracted_company():
    """An RSS headline (no clean company field) is resolved via the company name the LLM extracts."""
    s = FakeStore()

    def http_get(url, headers=None, params=None):
        if "bseindia" in url:  # BSE returns nothing this run -> only the RSS item flows
            return FetchResult(200, "application/json", json.dumps({"Table": [], "Table1": [{"ROWCNT": 0}]}))
        return FetchResult(200, "application/xml", RSS_XML)

    def llm(reps):
        # the model extracts the company from the free-text headline + judges it positive
        return [("Reliance Industries", "order_win", "positive") for _ in reps]

    res = capture_news(
        TD,
        adapters=[BseAdapter(), RssAdapter(feeds=[("RSS_GNEWS", "https://news.google.com/rss/search?q=x")])],
        http_get=http_get, resolver=R, store=s, is_trading_day=True, llm_classify=llm, log_only_count=True,
    )
    assert res.llm_classified == 1 and res.resolved == 1
    ev = next(iter(s.news_events.values()))
    assert ev["catalyst_tag"] == "ORDER_WIN" and ev["isin"] == "INE002A01018"  # resolved to Reliance


def test_capture_is_idempotent_across_reruns():
    s = FakeStore()
    capture_news(TD, adapters=[BseAdapter()], http_get=fake_get(), resolver=R, store=s, log_only_count=True)
    res2 = capture_news(TD, adapters=[BseAdapter()], http_get=fake_get(), resolver=R, store=s, log_only_count=True)
    assert res2.new_events == 0 and res2.duplicate_sources >= 1
    assert len(s.news_events) == 1  # no duplicate event on re-run
