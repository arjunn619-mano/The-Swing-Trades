"""Pure option-tracker decisions (Planning Pack 11). No DB here — the store applies them.

One row per contract. A contract is enrolled the first day its volume clears the threshold
(volume > 1L), tracked to expiry, then DELETED (its full history lives in the Parquet archive)."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class OptionTrackerState:
    contract_id: int
    first_seen_date: _dt.date
    entry_ltp: float
    expiry_date: _dt.date


@dataclass(frozen=True)
class OptionScanActions:
    to_enroll: list[int]   # contract_ids that qualified today and are not yet tracked
    to_expire: list[int]   # tracked contract_ids whose expiry has passed -> delete


def decide_option_actions(
    trade_date: _dt.date,
    qualifying_contract_ids: Iterable[int],
    tracked: Sequence[OptionTrackerState],
) -> OptionScanActions:
    """Enroll newly-qualifying contracts (volume > threshold, decided by the caller); expire
    tracked contracts whose expiry is in the past. Reappearance of an already-tracked contract
    is a no-op (it is simply observed again)."""
    tracked_ids = {t.contract_id for t in tracked}
    qualifying = list(dict.fromkeys(qualifying_contract_ids))  # de-dup, keep order

    to_enroll = [cid for cid in qualifying if cid not in tracked_ids]
    to_expire = [t.contract_id for t in tracked if t.expiry_date < trade_date]
    return OptionScanActions(to_enroll=to_enroll, to_expire=to_expire)
