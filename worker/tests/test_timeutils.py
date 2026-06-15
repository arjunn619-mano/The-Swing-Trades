import datetime as dt

from swing_trades.utils import timeutils as tu


def test_weekend_not_trading():
    assert not tu.is_trading_day(dt.date(2025, 8, 16))  # Saturday
    assert not tu.is_trading_day(dt.date(2025, 8, 17))  # Sunday


def test_fixed_national_holidays():
    assert not tu.is_trading_day(dt.date(2025, 8, 15))   # Independence Day (Fri)
    assert not tu.is_trading_day(dt.date(2025, 10, 2))   # Gandhi Jayanti (Thu)
    assert not tu.is_trading_day(dt.date(2026, 1, 26))   # Republic Day (Mon)


def test_normal_weekday_is_trading():
    assert tu.is_trading_day(dt.date(2025, 8, 18))  # Monday, not a holiday


def test_next_trading_day_skips_weekend():
    assert tu.next_trading_day(dt.date(2025, 8, 8)) == dt.date(2025, 8, 11)


def test_next_trading_day_skips_holiday_and_weekend():
    # Thu 14 Aug -> Fri 15 holiday, Sat/Sun -> Mon 18
    assert tu.next_trading_day(dt.date(2025, 8, 14)) == dt.date(2025, 8, 18)


def test_previous_trading_day_skips_holiday_and_weekend():
    assert tu.previous_trading_day(dt.date(2025, 8, 18)) == dt.date(2025, 8, 14)


def test_add_trading_days_roundtrip():
    start = dt.date(2025, 8, 18)
    end = tu.add_trading_days(start, 5)
    assert tu.trading_days_between(start, end) == 5
    assert tu.add_trading_days(end, -5) == start


def test_add_zero_returns_same():
    d = dt.date(2025, 8, 18)
    assert tu.add_trading_days(d, 0) == d


def test_window_end_counts_100_trading_days():
    start = dt.date(2025, 1, 1)
    end = tu.window_end_date(start, 100)
    assert tu.trading_days_between(start, end) == 100


def test_trading_days_between_symmetry():
    a = dt.date(2025, 8, 18)
    b = dt.date(2025, 9, 18)
    assert tu.trading_days_between(a, b) == -tu.trading_days_between(b, a)
