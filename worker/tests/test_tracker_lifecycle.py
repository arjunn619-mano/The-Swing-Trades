import datetime as dt

from swing_trades.tracker.lifecycle import TrackerEntryState, decide_tracker_actions
from swing_trades.utils.timeutils import add_trading_days


def _entry(iid, first_seen, sid=1, status="active", count=1):
    return TrackerEntryState(iid, sid, first_seen, status, count, entry_close=100.0)


def test_new_signals_become_creates():
    a = decide_tracker_actions(dt.date(2025, 8, 18), [10, 11], [], horizon_days=100)
    assert set(a.to_create) == {10, 11}
    assert a.to_increment == []


def test_existing_signal_increments():
    existing = [_entry(10, dt.date(2025, 8, 11))]
    a = decide_tracker_actions(dt.date(2025, 8, 18), [10], existing, 100)
    assert a.to_increment == [10] and a.to_create == []


def test_completes_at_horizon():
    first = dt.date(2025, 1, 1)
    later = add_trading_days(first, 5)
    a = decide_tracker_actions(later, [], [_entry(10, first)], horizon_days=5)
    assert 10 in a.to_complete


def test_not_complete_before_horizon():
    first = dt.date(2025, 8, 18)
    later = add_trading_days(first, 3)
    a = decide_tracker_actions(later, [], [_entry(10, first)], horizon_days=5)
    assert a.to_complete == []


def test_signals_deduplicated():
    a = decide_tracker_actions(dt.date(2025, 8, 18), [10, 10, 11], [], 100)
    assert a.to_create == [10, 11]
