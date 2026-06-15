"""Pure tracker-lifecycle decisions (Rules 2, 3, 8). No DB here — the store applies the
actions. One entry per (instrument x strategy); entry price permanent; window = horizon
TRADING days from first_seen, reappearance does not extend it."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from ..utils.timeutils import trading_days_between


@dataclass(frozen=True)
class TrackerEntryState:
    instrument_id: int
    strategy_id: int
    first_seen_date: _dt.date
    status: str  # active | completed
    appearance_count: int
    entry_close: float
    entry_next_open: Optional[float] = None
    horizon_days: int = 100


@dataclass(frozen=True)
class TrackerActions:
    to_create: list[int]      # instrument_ids newly qualifying (no active entry yet)
    to_increment: list[int]   # instrument_ids re-qualifying (active entry exists)
    to_complete: list[int]    # instrument_ids whose window has elapsed


def decide_tracker_actions(
    trade_date: _dt.date,
    signaled_instrument_ids: Iterable[int],
    existing_active: Sequence[TrackerEntryState],
    horizon_days: int,
) -> TrackerActions:
    active_ids = {e.instrument_id for e in existing_active}
    signaled = list(dict.fromkeys(signaled_instrument_ids))  # de-dup, keep order

    to_create = [iid for iid in signaled if iid not in active_ids]
    to_increment = [iid for iid in signaled if iid in active_ids]
    to_complete = [
        e.instrument_id
        for e in existing_active
        if trading_days_between(e.first_seen_date, trade_date) >= horizon_days
    ]
    return TrackerActions(to_create=to_create, to_increment=to_increment, to_complete=to_complete)
