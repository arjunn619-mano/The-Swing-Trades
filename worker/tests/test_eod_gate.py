import datetime as dt
from zoneinfo import ZoneInfo

from swing_trades.pipeline.catchup import eod_ready, last_settled_session

IST = ZoneInfo("Asia/Kolkata")


def test_ready_after_settle():
    assert eod_ready(dt.datetime(2026, 6, 16, 17, 0, tzinfo=IST)) is True   # 5 PM cron
    assert eod_ready(dt.datetime(2026, 6, 16, 16, 0, tzinfo=IST)) is True   # exactly the threshold


def test_not_ready_before_settle():
    assert eod_ready(dt.datetime(2026, 6, 16, 2, 15, tzinfo=IST)) is False  # the 2:15 AM stale run
    assert eod_ready(dt.datetime(2026, 6, 16, 15, 0, tzinfo=IST)) is False  # mid-session
    assert eod_ready(dt.datetime(2026, 6, 16, 15, 59, tzinfo=IST)) is False


def test_last_settled_session():
    # Jun 19 2026 = Fri, Jun 20 = Sat, Jun 21 = Sun (all verified trading-calendar)
    assert last_settled_session(dt.datetime(2026, 6, 21, 5, 0, tzinfo=IST)) == dt.date(2026, 6, 19)   # Sun -> Fri
    assert last_settled_session(dt.datetime(2026, 6, 20, 10, 0, tzinfo=IST)) == dt.date(2026, 6, 19)  # Sat -> Fri
    assert last_settled_session(dt.datetime(2026, 6, 19, 17, 0, tzinfo=IST)) == dt.date(2026, 6, 19)  # Fri post-close -> Fri
    assert last_settled_session(dt.datetime(2026, 6, 19, 14, 0, tzinfo=IST)) == dt.date(2026, 6, 18)  # Fri pre-close -> Thu
