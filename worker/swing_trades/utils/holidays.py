"""Static NSE trading-holiday list (Rule 7). Weekends are handled separately in timeutils.

REVIEW ANNUALLY: the exchange publishes the next year's holiday calendar each December.
Fixed national holidays (Republic Day 26 Jan, Independence Day 15 Aug, Gandhi Jayanti 2 Oct,
Christmas 25 Dec) are reliable; festival dates shift each year and are best-effort here.
"""
from __future__ import annotations

import datetime as _dt

_HOLIDAY_STRINGS: dict[int, list[str]] = {
    2024: [
        "2024-01-26",  # Republic Day
        "2024-03-08",  # Mahashivratri
        "2024-03-25",  # Holi
        "2024-03-29",  # Good Friday
        "2024-04-11",  # Id-Ul-Fitr
        "2024-04-17",  # Ram Navami
        "2024-05-01",  # Maharashtra Day
        "2024-08-15",  # Independence Day
        "2024-10-02",  # Gandhi Jayanti
        "2024-11-01",  # Diwali Laxmi Pujan
        "2024-11-15",  # Guru Nanak Jayanti
        "2024-12-25",  # Christmas
    ],
    2025: [
        "2025-02-26",  # Mahashivratri
        "2025-03-14",  # Holi
        "2025-03-31",  # Id-Ul-Fitr
        "2025-04-10",  # Mahavir Jayanti
        "2025-04-14",  # Dr. Ambedkar Jayanti
        "2025-04-18",  # Good Friday
        "2025-05-01",  # Maharashtra Day
        "2025-08-15",  # Independence Day
        "2025-08-27",  # Ganesh Chaturthi
        "2025-10-02",  # Gandhi Jayanti / Dussehra
        "2025-10-21",  # Diwali Laxmi Pujan
        "2025-10-22",  # Diwali Balipratipada
        "2025-11-05",  # Guru Nanak Jayanti
        "2025-12-25",  # Christmas
    ],
    2026: [
        "2026-01-26",  # Republic Day
        "2026-03-04",  # Holi (best-effort)
        "2026-04-03",  # Good Friday
        "2026-05-01",  # Maharashtra Day
        "2026-08-15",  # Independence Day (Sat)
        "2026-10-02",  # Gandhi Jayanti
        "2026-11-09",  # Diwali (best-effort)
        "2026-12-25",  # Christmas
    ],
}


def _parse(s: str) -> _dt.date:
    return _dt.date.fromisoformat(s)


NSE_HOLIDAYS: frozenset[_dt.date] = frozenset(
    _parse(s) for year in _HOLIDAY_STRINGS.values() for s in year
)


def is_holiday(d: _dt.date) -> bool:
    return d in NSE_HOLIDAYS
