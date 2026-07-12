"""BSE adapter parsing + the shared health gauntlet (HTTP, JSON-not-HTML, schema-drift, canary
count, freshness), including graceful degradation (CRITICAL returns no items, never raises)."""
import datetime as dt
import json

from swing_trades.data_layer.news.sources.base import FetchResult, HealthStatus
from swing_trades.data_layer.news.sources.bse import BseAdapter, parse_bse

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


def fake_get(status=200, ct="application/json", body=""):
    def _get(url, headers=None, params=None):
        return FetchResult(status, ct, body)
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
