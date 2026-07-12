"""RSS / narrative news adapter — Google News, Economic Times, Livemint, PR wires. Datacenter-
tolerant (runs from GitHub Actions). Headlines carry no clean company field or exchange category,
so every RSS item is Tier-C: the LLM extracts the company + judges sentiment, then the resolver maps
the name deterministically. Best-effort per feed — one bad feed never kills the others.

Moneycontrol / Business Standard are deliberately NOT here — they 403 datacenter IPs (Phase 2b,
Oracle VM)."""
from __future__ import annotations

import datetime as _dt
from typing import Optional
from urllib.parse import quote_plus

from ..models import RawNewsItem
from .base import HealthStatus, SourceHealth, sha1

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


def _gnews(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"


# (source_label, feed_url). Google News query feeds act as a meta-aggregator across all Indian
# outlets; the topical feeds add native coverage. 'when:1d' keeps Google News to the last day.
DEFAULT_FEEDS: list[tuple[str, str]] = [
    ("RSS_GNEWS", _gnews("Indian company bags order OR wins contract when:1d")),
    ("RSS_GNEWS", _gnews("Indian company buyback OR acquisition OR acquires stake when:1d")),
    ("RSS_GNEWS", _gnews("Indian company partnership OR joint venture OR new product launch when:1d")),
    ("RSS_GNEWS", _gnews("Indian company record profit OR results beat OR revenue jumps when:1d")),
    ("RSS_GNEWS", _gnews("Indian company rating upgrade OR capacity expansion OR QIP fund raising when:1d")),
    ("RSS_ET", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("RSS_LIVEMINT", "https://www.livemint.com/rss/companies"),
    ("RSS_PRWIRE", "https://www.prnewswire.com/rss/news-releases-list.rss"),
]


def _entry_date(entry, trade_date: _dt.date) -> _dt.date:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return _dt.date(t.tm_year, t.tm_mon, t.tm_mday)
            except (ValueError, TypeError):
                pass
    return trade_date


def parse_rss(body: str, source: str, trade_date: _dt.date) -> list[RawNewsItem]:
    import feedparser

    feed = feedparser.parse(body or "")
    items: list[RawNewsItem] = []
    for e in feed.entries:
        title = (getattr(e, "title", "") or "").strip()
        if not title:
            continue
        link = (getattr(e, "link", "") or "").strip()
        items.append(
            RawNewsItem(
                source=source,
                source_uid="rss:" + sha1(source, link or title),
                company_name=None,  # no clean company field — the LLM extracts it
                headline=title,
                event_date=_entry_date(e, trade_date),
                category=None,
                subcategory=None,
                isin=None,
                bse_scrip_code=None,
                url=(link or None),
            )
        )
    return items


class RssAdapter:
    source = "RSS"

    def __init__(self, feeds: Optional[list[tuple[str, str]]] = None):
        self.feeds = feeds if feeds is not None else DEFAULT_FEEDS

    def collect(
        self,
        trade_date: _dt.date,
        *,
        http_get,
        is_trading_day: bool = True,
        soft_min: int = 5,
        log_only_count: bool = False,
        today: Optional[_dt.date] = None,
    ) -> tuple[list[RawNewsItem], SourceHealth]:
        all_items: list[RawNewsItem] = []
        seen: set[str] = set()
        feeds_ok = 0
        last_error = ""
        sample = ""
        for label, url in self.feeds:
            try:
                fetch = http_get(url, headers=RSS_HEADERS)
            except Exception as e:  # one feed failing must not sink the rest
                last_error = str(e)
                continue
            if fetch.error or not (200 <= fetch.status_code < 300):
                last_error = f"HTTP {fetch.status_code} {fetch.error or ''}".strip()
                if not sample:
                    sample = (fetch.body or "")[:300]
                continue
            feeds_ok += 1
            for it in parse_rss(fetch.body, label, trade_date):
                if it.source_uid not in seen:
                    seen.add(it.source_uid)
                    all_items.append(it)

        n = len(all_items)
        if feeds_ok == 0:  # every feed was unreachable/blocked — degrade to nothing + alarm
            return [], SourceHealth("RSS", HealthStatus.CRITICAL, count=0, checks_run=["feeds"],
                                    failed_check="all_feeds_down", detail=last_error, sample=sample)
        if is_trading_day and not log_only_count and n < soft_min:
            return all_items, SourceHealth("RSS", HealthStatus.DEGRADED, count=n, checks_run=["feeds", "count"],
                                           failed_check="count", detail=f"{n} items < soft_min {soft_min}")
        return all_items, SourceHealth("RSS", HealthStatus.OK, count=n, checks_run=["feeds", "count"])
