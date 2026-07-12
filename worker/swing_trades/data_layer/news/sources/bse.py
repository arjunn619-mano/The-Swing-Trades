"""BSE corporate-announcements adapter — the durable Layer-1 primary.

Stateless JSON GET (browser User-Agent + Referer, no cookie/token/CAPTCHA). Covers all ~5,900
BSE-listed companies PLUS every dual-listed NSE name (SEBI Reg-30 mandatory dual-filing), so it
reaches ~all of the liquid universe. Undocumented, so wrapped behind this adapter: raw body is
logged before parsing and any schema change trips the health gauntlet.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Callable, Optional

from ..models import RawNewsItem
from .base import FetchResult, HealthStatus, ParseResult, SourceHealth, evaluate_health, sha1

BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
# A real desktop browser UA is required (BSE 403s python-requests). Kept here (not hard-coded deep
# in the call) so it can be rotated from config when it ages out and starts drawing 403s.
BSE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
BSE_HEADERS = {
    "User-Agent": BSE_UA,
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json, text/plain, */*",
}


def _parse_date(val) -> Optional[_dt.date]:
    s = str(val or "").strip().replace("T", " ")
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])  # handles '2026-07-12 15:30:00' and '2026-07-12'
    except ValueError:
        pass
    for fmt in ("%d %b %Y %H:%M:%S", "%d %b %Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_bse(body: str, trade_date: _dt.date) -> ParseResult:
    """Map the BSE AnnSubCategoryGetData JSON to RawNewsItem. Required fields: SCRIP_CD, a headline
    (HEADLINE|NEWSSUB), CATEGORYNAME, SLONGNAME — a row missing any is a parse_failure (schema drift)."""
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return ParseResult([], 0, 0)  # not JSON — the content_type health check reports this
    rows = payload.get("Table") or []
    items: list[RawNewsItem] = []
    failures = 0
    for r in rows:
        scrip = str(r.get("SCRIP_CD") or "").strip()
        headline = (r.get("HEADLINE") or r.get("NEWSSUB") or "").strip()
        category = (r.get("CATEGORYNAME") or "").strip()
        name = (r.get("SLONGNAME") or "").strip()
        if not scrip or not headline or not category or not name:
            failures += 1
            continue
        newsid = str(r.get("NEWSID") or "").strip()
        uid = "bse:" + (newsid or sha1(scrip, r.get("NEWS_DT", ""), headline))
        items.append(
            RawNewsItem(
                source="BSE",
                source_uid=uid,
                company_name=name,
                headline=headline,
                event_date=_parse_date(r.get("NEWS_DT")) or trade_date,
                category=category,
                subcategory=(str(r.get("SUBCATNAME") or "").strip() or None),
                isin=None,  # BSE feed carries scrip, not ISIN — resolver maps scrip -> ISIN
                bse_scrip_code=scrip,
                url=(str(r.get("NSURL") or "").strip() or None),
            )
        )
    return ParseResult(items, raw_rows=len(rows), parse_failures=failures)


def fetch_bse(trade_date: _dt.date, http_get: Callable, page: int = 1) -> FetchResult:
    """http_get(url, headers, params) -> FetchResult. Injected so this is testable + can run from
    the Oracle VM IP unchanged. Queries the single trade date (BSE takes YYYYMMDD), one page at a time."""
    ymd = trade_date.strftime("%Y%m%d")
    params = {
        "strCat": "-1", "strPrevDate": ymd, "strToDate": ymd,
        "strScrip": "", "strSearch": "P", "strType": "C", "pageno": str(page),
    }
    return http_get(BSE_URL, headers=BSE_HEADERS, params=params)


class BseAdapter:
    source = "BSE"

    def collect(
        self,
        trade_date: _dt.date,
        *,
        http_get: Callable,
        is_trading_day: bool = True,
        soft_min: int = 50,
        log_only_count: bool = False,
        today: Optional[_dt.date] = None,
        max_pages: int = 60,
    ) -> tuple[list[RawNewsItem], SourceHealth]:
        # Page 1 drives the transport/content-type health checks; then walk pages until one comes
        # back empty (or the safety cap), deduping by source_uid so page overlap is harmless. The
        # BSE feed paginates ~45 rows/page and a busy day is hundreds of filings, so a single page
        # would miss the bulk of the day's catalysts.
        try:
            fetch1 = fetch_bse(trade_date, http_get, page=1)
        except Exception as e:  # transport blew up — never raise into the scan
            fetch1 = FetchResult(0, "", "", error=str(e))
        parsed = parse_bse(fetch1.body, trade_date) if not fetch1.error else ParseResult([], 0, 0)

        all_items: list[RawNewsItem] = list(parsed.items)
        raw_rows, failures = parsed.raw_rows, parsed.parse_failures
        if not fetch1.error and parsed.raw_rows > 0:
            seen = {it.source_uid for it in all_items}
            page = 2
            while page <= max_pages:
                try:
                    fp = fetch_bse(trade_date, http_get, page=page)
                except Exception:
                    break
                if fp.error:
                    break
                pp = parse_bse(fp.body, trade_date)
                if pp.raw_rows == 0:
                    break  # no more pages
                for it in pp.items:
                    if it.source_uid not in seen:
                        seen.add(it.source_uid)
                        all_items.append(it)
                raw_rows += pp.raw_rows
                failures += pp.parse_failures
                page += 1

        combined = ParseResult(all_items, raw_rows, failures)
        latest = max((it.event_date for it in all_items), default=None)
        health = evaluate_health(
            "BSE", fetch1, combined, is_trading_day=is_trading_day, soft_min=soft_min,
            expect_json=True, latest_date=latest, today=today or trade_date,
            log_only_count=log_only_count,
        )
        items = all_items if health.status != HealthStatus.CRITICAL else []
        return items, health
