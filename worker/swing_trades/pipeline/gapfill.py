"""Fill a price gap before the daily scan (Arjun 2026-11-22: "i also want the swing tracker to start from tomorrow").

The daily scan prices today from the live quote, but its indicators (RSI, ATR, Supertrend, volume average) read the
trailing daily bars in price_history. After missed days (the 2 -> 20 Nov 2026 pause, an outage, a holiday mix-up)
those bars have a hole, and the indicators would be computed on gappy data. So, before scanning, the scan pulls the
missing daily bars from Dhan's historical API with the SAME login (one login per run: the account is shared with the
NIFTY bots). It only runs when there is a gap, so a normal day costs nothing extra.

Not recoverable this way: the signals of the missed days themselves (the screen runs on one day's close); those days
stay missing in the tracker and are counted on the Health page as a gap, never faked.
"""
from __future__ import annotations

import datetime as _dt
import time
from typing import Callable, Optional

from ..utils.timeutils import previous_trading_day, trading_days_between

PACE_S = 0.25  # stay well under Dhan's 5 requests/second data limit (same pace as scripts/backfill.py)


def gap_window(last_success: Optional[_dt.date], target: _dt.date) -> Optional[tuple[_dt.date, _dt.date]]:
    """(from_date, to_date_exclusive) of the daily bars to fetch, or None when there is no gap.
    No prior scan at all = a fresh database: that is the one-time Bootstrap's job, not this."""
    if last_success is None or last_success >= previous_trading_day(target):
        return None
    return last_success + _dt.timedelta(days=1), target          # target's own bar comes from today's live quote


def fill_price_gap(store, client, target: _dt.date, *, logger=None, sleep: Callable[[float], None] = time.sleep) -> dict:
    last = store.last_successful_scan_date()
    w = gap_window(last, target)
    if w is None:
        return {"gap_trading_days": 0, "filled": 0, "failed": 0}
    days = max(trading_days_between(last, target) - 1, 0)
    refs = store.get_active_instruments()
    if logger:
        logger.info(f"price gap: {days} missed trading day(s) after {last}; fetching {w[0]}..{w[1]} for {len(refs)} stocks")
    ok = fail = 0
    for ref in refs:
        try:
            bars = client.historical_daily(ref.security_id, ref.exchange_segment, w[0].isoformat(), w[1].isoformat())
            store.upsert_price_bars(ref.id, [b for b in bars if b.trade_date < target])
            ok += 1
        except Exception:
            fail += 1
            if logger:
                logger.exception(f"gap fill failed for {ref.isin} ({ref.security_id})")
        sleep(PACE_S)
    if logger:
        logger.info(f"price gap filled: {ok} stocks ok, {fail} failed")
    return {"gap_trading_days": days, "filled": ok, "failed": fail, "from": w[0].isoformat()}
