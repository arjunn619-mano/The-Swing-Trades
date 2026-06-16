import datetime as dt
from zoneinfo import ZoneInfo

from swing_trades.pipeline.catchup import eod_ready

IST = ZoneInfo("Asia/Kolkata")


def test_ready_after_settle():
    assert eod_ready(dt.datetime(2026, 6, 16, 17, 0, tzinfo=IST)) is True   # 5 PM cron
    assert eod_ready(dt.datetime(2026, 6, 16, 16, 0, tzinfo=IST)) is True   # exactly the threshold


def test_not_ready_before_settle():
    assert eod_ready(dt.datetime(2026, 6, 16, 2, 15, tzinfo=IST)) is False  # the 2:15 AM stale run
    assert eod_ready(dt.datetime(2026, 6, 16, 15, 0, tzinfo=IST)) is False  # mid-session
    assert eod_ready(dt.datetime(2026, 6, 16, 15, 59, tzinfo=IST)) is False
