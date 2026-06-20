"""Pure decisions for the catchup-aware runner (so the cron is idempotent and notices gaps).

The daily scan uses a *live* quote snapshot, so it can only produce today's bar. Filling
genuinely missed past days needs the historical API (scripts/backfill.py) — here we just
decide whether to run today and surface how many trading days were skipped."""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from ..utils.timeutils import is_trading_day, previous_trading_day, trading_days_between


MARKET_SETTLE_IST = _dt.time(16, 0)  # NSE closes 15:30 IST; allow ~30 min for EOD data to settle


def eod_ready(now: _dt.datetime) -> bool:
    """True once today's EOD data should be settled (now >= 16:00 IST). Before that, scanning
    'today' would capture pre-/intraday (stale) prices and wrongly mark the day complete, so the
    daily runner skips it. `now` is an IST-aware datetime (timeutils.now_ist())."""
    return now.time() >= MARKET_SETTLE_IST


def should_run_today(today: _dt.date, already_done_today: bool) -> bool:
    return is_trading_day(today) and not already_done_today


def last_settled_session(now: _dt.datetime) -> _dt.date:
    """The most recent trading day whose EOD data is settled, as of `now` (IST): today if it's
    a trading day past the 16:00 settle, else the previous trading day. The live quote reflects
    exactly this session's close, so scanning it is accurate even when run on a weekend/holiday
    (e.g. run on Sunday -> pulls Friday)."""
    today = now.date()
    if is_trading_day(today) and eod_ready(now):
        return today
    return previous_trading_day(today)


def trading_gap(last_successful: Optional[_dt.date], today: _dt.date) -> int:
    """How many trading days were skipped between the last successful scan and today
    (0 if the last success was the previous trading day, or if there's no prior run)."""
    if last_successful is None:
        return 0
    return max(trading_days_between(last_successful, today) - 1, 0)
