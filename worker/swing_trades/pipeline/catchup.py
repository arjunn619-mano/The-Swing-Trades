"""Pure decisions for the catchup-aware runner (so the cron is idempotent and notices gaps).

The daily scan uses a *live* quote snapshot, so it can only produce today's bar. Filling
genuinely missed past days needs the historical API (scripts/backfill.py) — here we just
decide whether to run today and surface how many trading days were skipped."""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from ..utils.timeutils import is_trading_day, trading_days_between


def should_run_today(today: _dt.date, already_done_today: bool) -> bool:
    return is_trading_day(today) and not already_done_today


def trading_gap(last_successful: Optional[_dt.date], today: _dt.date) -> int:
    """How many trading days were skipped between the last successful scan and today
    (0 if the last success was the previous trading day, or if there's no prior run)."""
    if last_successful is None:
        return 0
    return max(trading_days_between(last_successful, today) - 1, 0)
