"""IST-everywhere time helpers and the trading-day calendar (Rules 7 & 8).

A "trading day" is a weekday that is not an NSE holiday. The 100-day tracking window
counts *trading* days, never calendar days.
"""
from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

from . import holidays

IST = ZoneInfo("Asia/Kolkata")
_SATURDAY = 5
_SUNDAY = 6


def now_ist() -> _dt.datetime:
    return _dt.datetime.now(tz=IST)


def today_ist() -> _dt.date:
    return now_ist().date()


def is_weekend(d: _dt.date) -> bool:
    return d.weekday() in (_SATURDAY, _SUNDAY)


def is_trading_day(d: _dt.date) -> bool:
    return not is_weekend(d) and not holidays.is_holiday(d)


def next_trading_day(d: _dt.date) -> _dt.date:
    """The first trading day strictly after `d`."""
    nxt = d + _dt.timedelta(days=1)
    while not is_trading_day(nxt):
        nxt += _dt.timedelta(days=1)
    return nxt


def previous_trading_day(d: _dt.date) -> _dt.date:
    """The first trading day strictly before `d`."""
    prev = d - _dt.timedelta(days=1)
    while not is_trading_day(prev):
        prev -= _dt.timedelta(days=1)
    return prev


def add_trading_days(d: _dt.date, n: int) -> _dt.date:
    """The date `n` trading days after `d` (n may be negative). n == 0 returns `d`."""
    if n == 0:
        return d
    step = next_trading_day if n > 0 else previous_trading_day
    out = d
    for _ in range(abs(n)):
        out = step(out)
    return out


def trading_days_between(start: _dt.date, end: _dt.date) -> int:
    """Count of trading days strictly after `start` up to and including `end`
    (i.e. how many trading days `end` is past `start`). Negative if end < start."""
    if end == start:
        return 0
    sign = 1 if end > start else -1
    lo, hi = (start, end) if sign == 1 else (end, start)
    count = 0
    cur = lo
    while cur < hi:
        cur += _dt.timedelta(days=1)
        if is_trading_day(cur):
            count += 1
    return sign * count


def window_end_date(first_seen: _dt.date, horizon_trading_days: int) -> _dt.date:
    """The calendar date on which a `horizon_trading_days` window from `first_seen` closes."""
    return add_trading_days(first_seen, horizon_trading_days)


def epoch_to_ist_date(epoch_seconds: int | float) -> _dt.date:
    """Convert a Dhan candle epoch (Unix seconds, set to IST midnight) to its trade date.
    Guards against the documented 1980-vs-1970 epoch ambiguity by sanity-checking the year."""
    moment = _dt.datetime.fromtimestamp(int(epoch_seconds), tz=IST)
    if not (1990 <= moment.year <= 2100):
        raise ValueError(f"Implausible candle epoch {epoch_seconds!r} -> {moment.isoformat()}")
    return moment.date()
