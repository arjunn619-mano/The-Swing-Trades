"""BSE adapter parsing + the shared health gauntlet (HTTP, JSON-not-HTML, schema-drift, canary
count, freshness), including graceful degradation (CRITICAL returns no items, never raises)."""
import datetime as dt
import json

from swing_trades.data_layer.news.sources.base import FetchResult, HealthStatus
from swing_trades.data_layer.news.sources.bse import BseAdapter, parse_bse
from swing_trades.data_layer.news.sources.rss import RssAdapter, parse_rss

TD = dt.date(2026, 7, 13)  # a Monday

BSE_OK = json.dumps({
    "Table": [
        {"SCRIP_CD": 500325, "SLONGNAME": "Reliance Industries Ltd", "CATEGORYNAME": "Company Update",
         "SUBCATNAME": "Award of Order / Receipt of Order", "HEADLINE": "Reliance bags large EPC order",
         "NEWS_DT": "2026-07-13T15:30:00", "NSURL": "https://bse/x", "NEWSID": "abc123"},
        {"SCRIP_CD": 532540, "SLONGNAME": "Tata Consultancy Services Ltd", "CATEGORYNAME": "Board Meeting",
         "NEWSSUB": "Outcome of Board Meeting - Results", "NEWS_DT": "2026-07-13 14:00:00", "NEWSID": "def456"},
    ],
    "Table1": [{"ROWCNT": 2}],
})
EMPTY = json.dumps({"Table": [], "Table1": [{"ROWCNT": 0}]})


def fake_get(status=200, ct="application/json", body="", pages=None):
    # Page-aware: `body` on page 1 and EMPTY on page >= 2 (so pagination terminates), unless `pages`
    # gives explicit per-page bodies.
    def _get(url, headers=None, params=None):
        page = str((params or {}).get("pageno", "1"))
        if pages is not None:
            return FetchResult(status, ct, pages.get(page, EMPTY))
        return FetchResult(status, ct, body if page == "1" else EMPTY)
    return _get


def test_parse_bse_maps_rows():
    pr = parse_bse(BSE_OK, TD)
    assert pr.raw_rows == 2 and pr.parse_failures == 0 and len(pr.items) == 2
    it = pr.items[0]
    assert it.source == "BSE" and it.bse_scrip_code == "500325" and it.isin is None
    assert it.source_uid == "bse:abc123"
    assert it.subcategory == "Award of Order / Receipt of Order"
    assert it.event_date == dt.date(2026, 7, 13)
    assert pr.items[1].headline == "Outcome of Board Meeting - Results"  # NEWSSUB fallback


def test_collect_healthy_ok():
    items, h = BseAdapter().collect(TD, http_get=fake_get(body=BSE_OK), is_trading_day=True, soft_min=1)
    assert h.status == HealthStatus.OK and len(items) == 2


def test_collect_http_403_critical_no_items():
    items, h = BseAdapter().collect(TD, http_get=fake_get(status=403, body="Forbidden"), is_trading_day=True)
    assert h.status == HealthStatus.CRITICAL and h.failed_check == "http" and items == []


def test_collect_html_challenge_critical():
    items, h = BseAdapter().collect(TD, http_get=fake_get(ct="text/html", body="<html>bot check</html>"), is_trading_day=True)
    assert h.status == HealthStatus.CRITICAL and h.failed_check == "content_type" and items == []


def test_collect_schema_drift_critical():
    body = json.dumps({"Table": [{"FOO": 1}, {"BAR": 2}, {"BAZ": 3}], "Table1": [{"ROWCNT": 3}]})
    items, h = BseAdapter().collect(TD, http_get=fake_get(body=body), is_trading_day=True)
    assert h.status == HealthStatus.CRITICAL and h.failed_check == "schema"


def test_collect_empty_on_trading_day_critical():
    items, h = BseAdapter().collect(TD, http_get=fake_get(body=EMPTY), is_trading_day=True, soft_min=50)
    assert h.status == HealthStatus.CRITICAL and h.failed_check == "count"


def test_collect_low_count_degraded_still_returns_items():
    items, h = BseAdapter().collect(TD, http_get=fake_get(body=BSE_OK), is_trading_day=True, soft_min=50)
    assert h.status == HealthStatus.DEGRADED and len(items) == 2  # DEGRADED keeps the items


def test_collect_empty_log_only_defers_count_alarm():
    items, h = BseAdapter().collect(TD, http_get=fake_get(body=EMPTY), is_trading_day=True, soft_min=50, log_only_count=True)
    assert h.status == HealthStatus.OK  # week-1 calibration: low/empty count does not alarm yet


def test_collect_non_trading_day_empty_ok():
    items, h = BseAdapter().collect(TD, http_get=fake_get(body=EMPTY), is_trading_day=False, soft_min=50)
    assert h.status == HealthStatus.OK  # count/freshness gated on trading days


def test_collect_frozen_feed_freshness_critical():
    stale = json.dumps({"Table": [
        {"SCRIP_CD": 1, "SLONGNAME": "Old Co Ltd", "CATEGORYNAME": "X", "HEADLINE": "old news",
         "NEWS_DT": "2026-07-01T10:00:00", "NEWSID": "old1"}], "Table1": [{"ROWCNT": 1}]})
    items, h = BseAdapter().collect(TD, http_get=fake_get(body=stale), is_trading_day=True, soft_min=1, today=TD)
    assert h.status == HealthStatus.CRITICAL and h.failed_check == "freshness"


def test_collect_transport_error_critical_never_raises():
    def boom(url, headers=None, params=None):
        raise ConnectionError("blocked by firewall")
    items, h = BseAdapter().collect(TD, http_get=boom, is_trading_day=True)
    assert h.status == HealthStatus.CRITICAL and h.failed_check == "http" and items == []


RSS = (
    '<?xml version="1.0"?><rss version="2.0"><channel>'
    "<item><title>Tata Motors bags large order</title><link>http://x/1</link>"
    "<pubDate>Mon, 13 Jul 2026 10:00:00 GMT</pubDate></item>"
    "<item><title>Infosys wins new contract</title><link>http://x/2</link>"
    "<pubDate>Mon, 13 Jul 2026 09:00:00 GMT</pubDate></item>"
    "</channel></rss>"
)


def test_parse_rss_maps_entries():
    items = parse_rss(RSS, "RSS_GNEWS", TD)
    assert len(items) == 2
    it = items[0]
    assert it.source == "RSS_GNEWS" and it.company_name is None  # no clean company -> LLM extracts it
    assert it.headline == "Tata Motors bags large order" and it.event_date == dt.date(2026, 7, 13)
    assert it.source_uid.startswith("rss:")


def test_rss_collect_ok():
    def get(url, headers=None, params=None):
        return FetchResult(200, "application/xml", RSS)
    items, h = RssAdapter(feeds=[("RSS_GNEWS", "u1")]).collect(TD, http_get=get, is_trading_day=True, soft_min=1)
    assert h.status == HealthStatus.OK and len(items) == 2


def test_rss_collect_all_feeds_down_is_critical():
    def get(url, headers=None, params=None):
        return FetchResult(403, "text/html", "blocked")
    items, h = RssAdapter(feeds=[("RSS_GNEWS", "u1")]).collect(TD, http_get=get, is_trading_day=True)
    assert h.status == HealthStatus.CRITICAL and h.failed_check == "all_feeds_down" and items == []


def test_rss_collect_is_best_effort_across_feeds():
    def get(url, headers=None, params=None):
        return FetchResult(200, "application/xml", RSS) if url == "good" else FetchResult(500, "", "")
    items, h = RssAdapter(feeds=[("RSS_ET", "bad"), ("RSS_GNEWS", "good")]).collect(
        TD, http_get=get, is_trading_day=True, soft_min=1)
    assert h.status == HealthStatus.OK and len(items) == 2  # one feed down, the other still delivers


def test_rss_folds_in_the_feed_summary():
    xml = ('<?xml version="1.0"?><rss version="2.0"><channel><item>'
           "<title>Tata Motors update</title>"
           "<description>&lt;p&gt;The board approved a Rs 5000 cr order win from Indian Railways&lt;/p&gt;</description>"
           "<link>http://x/1</link><pubDate>Mon, 13 Jul 2026 10:00:00 GMT</pubDate></item></channel></rss>")
    it = parse_rss(xml, "RSS_ET", TD)[0]
    assert it.headline.startswith("Tata Motors update — ")   # title + cleaned (de-HTML'd) summary
    assert "order win from Indian Railways" in it.headline


def test_rss_collect_survives_parse_failure(monkeypatch):
    # A parse/import failure (e.g. feedparser missing) must degrade the feed to a skip, never raise
    # into the scan — so the already-fetched BSE backbone is never silently dropped.
    from swing_trades.data_layer.news.sources import rss as rssmod

    def boom(body, source, td):
        raise ImportError("feedparser missing")

    monkeypatch.setattr(rssmod, "parse_rss", boom)

    def get(url, headers=None, params=None):
        return FetchResult(200, "application/xml", RSS)

    items, h = rssmod.RssAdapter(feeds=[("RSS_GNEWS", "u1")]).collect(TD, http_get=get, is_trading_day=True)
    assert h.status == HealthStatus.CRITICAL and h.failed_check == "all_feeds_down" and items == []


def test_collect_paginates_until_empty_page():
    p1 = json.dumps({"Table": [{"SCRIP_CD": 1, "SLONGNAME": "A Ltd", "CATEGORYNAME": "X",
                                 "HEADLINE": "h1", "NEWS_DT": "2026-07-13T10:00:00", "NEWSID": "a1"}],
                     "Table1": [{"ROWCNT": 1}]})
    p2 = json.dumps({"Table": [{"SCRIP_CD": 2, "SLONGNAME": "B Ltd", "CATEGORYNAME": "X",
                                 "HEADLINE": "h2", "NEWS_DT": "2026-07-13T09:00:00", "NEWSID": "b1"}],
                     "Table1": [{"ROWCNT": 1}]})
    get = fake_get(pages={"1": p1, "2": p2})  # page 3 -> EMPTY -> stop
    items, h = BseAdapter().collect(TD, http_get=get, is_trading_day=True, soft_min=1)
    assert h.status == HealthStatus.OK
    assert {it.source_uid for it in items} == {"bse:a1", "bse:b1"}  # both pages combined
