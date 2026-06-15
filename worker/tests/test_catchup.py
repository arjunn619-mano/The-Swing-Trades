import datetime as dt

from swing_trades.pipeline.catchup import should_run_today, trading_gap
from swing_trades.utils.timeutils import add_trading_days, previous_trading_day


def test_runs_on_trading_day_when_not_done():
    assert should_run_today(dt.date(2025, 8, 18), already_done_today=False) is True


def test_does_not_run_when_already_done():
    assert should_run_today(dt.date(2025, 8, 18), already_done_today=True) is False


def test_does_not_run_on_weekend():
    assert should_run_today(dt.date(2025, 8, 17), already_done_today=False) is False  # Sunday


def test_gap_zero_when_last_was_previous_trading_day():
    today = dt.date(2025, 8, 18)
    assert trading_gap(previous_trading_day(today), today) == 0


def test_gap_counts_skipped_days():
    today = dt.date(2025, 8, 18)
    assert trading_gap(add_trading_days(today, -3), today) == 2


def test_gap_zero_when_no_prior_run():
    assert trading_gap(None, dt.date(2025, 8, 18)) == 0
