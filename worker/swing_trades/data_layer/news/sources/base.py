"""Adapter contract + the shared health gauntlet.

Undocumented exchange APIs break silently (BSE 403s non-browser clients; NSE serves Akamai HTML
challenge pages with a 200 status; either can return an empty/frozen list). So every fetch runs an
ordered gauntlet that NEVER raises into the scan — it returns a typed SourceHealth the aggregator
uses for graceful degradation. HTTP transport is injected (http_get) so parsing/health are testable
offline and the whole thing can move to the Oracle VM's IP without code change."""
from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class HealthStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"   # works, but suspiciously thin — WARN
    CRITICAL = "CRITICAL"   # broken — ALARM (and degrade to another source)


@dataclass
class FetchResult:
    """What the injected http_get returns (already read to text)."""

    status_code: int
    content_type: str
    body: str
    error: Optional[str] = None      # transport-level failure (timeout / blocked), body may be empty


@dataclass
class ParseResult:
    items: list           # list[RawNewsItem]
    raw_rows: int = 0     # rows seen in the payload (for schema-drift detection)
    parse_failures: int = 0  # rows that lacked a required field


@dataclass
class SourceHealth:
    source: str
    status: HealthStatus
    count: int = 0
    checks_run: list[str] = field(default_factory=list)
    failed_check: Optional[str] = None
    detail: str = ""
    sample: str = ""       # first 300 chars of the raw body, for one-glance diagnosis

    @property
    def ok(self) -> bool:
        return self.status == HealthStatus.OK

    def to_dict(self) -> dict:
        return {
            "source": self.source, "status": self.status.value, "count": self.count,
            "failed_check": self.failed_check, "detail": self.detail,
        }


def sha1(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8", "replace")).hexdigest()


# Fraction of rows that may fail required-field validation before we call it schema drift.
SCHEMA_DRIFT_FRACTION = 0.10


def evaluate_health(
    source: str,
    fetch: FetchResult,
    parsed: ParseResult,
    *,
    is_trading_day: bool,
    soft_min: int,
    expect_json: bool = True,
    latest_date: Optional[_dt.date] = None,
    today: Optional[_dt.date] = None,
    freshness_grace_days: int = 3,
    log_only_count: bool = False,
) -> SourceHealth:
    """Ordered 5-check gauntlet; short-circuits on the first CRITICAL. Count/freshness checks are
    gated on is_trading_day (weekends/holidays never false-alarm). log_only_count defers ONLY the
    count/low-count alarm (week-1 calibration); hard failures (http/html/schema/stale) always alarm."""
    checks: list[str] = []
    sample = (fetch.body or "")[:300]

    # 1. transport / HTTP status
    checks.append("http")
    if fetch.error or not (200 <= fetch.status_code < 300):
        return SourceHealth(source, HealthStatus.CRITICAL, checks_run=checks, failed_check="http",
                            detail=f"HTTP {fetch.status_code} {fetch.error or ''}".strip(), sample=sample)

    # 2. JSON-not-HTML (catches Akamai/Cloudflare 200-status challenge pages)
    checks.append("content_type")
    body_lstrip = (fetch.body or "").lstrip()
    looks_html = body_lstrip[:1] == "<"
    ct = (fetch.content_type or "").lower()
    if expect_json and (looks_html or ("json" not in ct and body_lstrip[:1] not in "[{")):
        return SourceHealth(source, HealthStatus.CRITICAL, checks_run=checks, failed_check="content_type",
                            detail="expected JSON, got HTML/challenge page", sample=sample)

    # 3. schema drift — too many rows failing required-field validation
    checks.append("schema")
    if parsed.raw_rows and parsed.parse_failures / parsed.raw_rows > SCHEMA_DRIFT_FRACTION:
        return SourceHealth(source, HealthStatus.CRITICAL, count=len(parsed.items), checks_run=checks,
                            failed_check="schema",
                            detail=f"{parsed.parse_failures}/{parsed.raw_rows} rows failed field validation",
                            sample=sample)

    n = len(parsed.items)

    # 4. canary count (trading days only; low-count alarm deferred in log-only mode)
    checks.append("count")
    if is_trading_day and not log_only_count:
        if n == 0:
            return SourceHealth(source, HealthStatus.CRITICAL, count=0, checks_run=checks,
                                failed_check="count", detail="0 items on a trading day", sample=sample)
        if n < soft_min:
            return SourceHealth(source, HealthStatus.DEGRADED, count=n, checks_run=checks,
                                failed_check="count", detail=f"{n} items < soft_min {soft_min}", sample=sample)

    # 5. freshness — a frozen feed serving stale cached data. Lenient (grace in DAYS) so weekend/
    #    holiday/last-settled-session gaps never false-alarm; only a clearly-stuck feed trips it.
    checks.append("freshness")
    if is_trading_day and not log_only_count and latest_date is not None and today is not None:
        if latest_date < today - _dt.timedelta(days=freshness_grace_days):
            return SourceHealth(source, HealthStatus.CRITICAL, count=n, checks_run=checks,
                                failed_check="freshness",
                                detail=f"newest item {latest_date} vs today {today} (frozen feed?)", sample=sample)

    return SourceHealth(source, HealthStatus.OK, count=n, checks_run=checks)
