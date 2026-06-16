"""Persistence boundary for the option scan (Planning Pack 11, Phase O3).

`OptionScanStore` is the interface. `FakeOptionStore` is the in-memory implementation used by
tests (same delete-on-expiry semantics, no DB). `PostgresOptionStore` is Neon-backed."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional, Sequence

from ..tracker.option_lifecycle import OptionTrackerState


@dataclass(frozen=True)
class OptionContractRef:
    id: int
    security_id: str
    underlying_symbol: str
    underlying_security_id: Optional[str]
    exchange: str
    instrument_type: str           # OPTIDX | OPTSTK
    expiry_date: _dt.date
    strike: float
    option_type: str               # CE | PE
    lot_size: Optional[int] = None


class OptionScanStore:
    """Interface. See FakeOptionStore for the canonical in-memory semantics."""

    def get_option_contracts(self) -> list[OptionContractRef]: raise NotImplementedError
    def get_tracked_options(self) -> list[OptionTrackerState]: raise NotImplementedError
    def enroll_option(self, contract_id: int, first_seen_date: _dt.date, entry_ltp: float,
                      entry_iv: Optional[float], entry_oi: Optional[int], expiry_date: _dt.date) -> None:
        raise NotImplementedError
    def record_option_observation(self, contract_id: int, trade_date: _dt.date, *, ltp: float,
                                  volume: int, oi: int, oi_change_pct: Optional[float],
                                  iv: Optional[float], delta: Optional[float], theta: Optional[float],
                                  gamma: Optional[float], vega: Optional[float],
                                  days_to_expiry: int, return_vs_entry: Optional[float]) -> None:
        raise NotImplementedError
    def expire_options(self, contract_ids: Sequence[int]) -> None: raise NotImplementedError


class FakeOptionStore(OptionScanStore):
    def __init__(self) -> None:
        self.contracts: list[OptionContractRef] = []
        self.tracker: dict[int, dict] = {}                         # contract_id -> entry
        self.observations: dict[tuple[int, _dt.date], dict] = {}   # (contract_id, date) -> obs

    # --- setup helpers ---
    def add_contract(self, ref: OptionContractRef) -> None:
        self.contracts.append(ref)

    # --- reads ---
    def get_option_contracts(self) -> list[OptionContractRef]:
        return list(self.contracts)

    def get_tracked_options(self) -> list[OptionTrackerState]:
        return [
            OptionTrackerState(cid, e["first_seen_date"], e["entry_ltp"], e["expiry_date"])
            for cid, e in self.tracker.items()
            if e["status"] == "active"
        ]

    # --- writes ---
    def enroll_option(self, contract_id, first_seen_date, entry_ltp, entry_iv, entry_oi, expiry_date) -> None:
        if contract_id in self.tracker:  # unique (contract) — never double-enroll
            return
        self.tracker[contract_id] = {
            "first_seen_date": first_seen_date,
            "entry_ltp": entry_ltp,
            "entry_iv": entry_iv,
            "entry_oi": entry_oi,
            "expiry_date": expiry_date,
            "status": "active",
        }

    def record_option_observation(self, contract_id, trade_date, *, ltp, volume, oi, oi_change_pct,
                                  iv, delta, theta, gamma, vega, days_to_expiry, return_vs_entry) -> None:
        if contract_id not in self.tracker:
            return
        self.observations[(contract_id, trade_date)] = {
            "ltp": ltp, "volume": volume, "oi": oi, "oi_change_pct": oi_change_pct, "iv": iv,
            "delta": delta, "theta": theta, "gamma": gamma, "vega": vega,
            "days_to_expiry": days_to_expiry, "return_vs_entry": return_vs_entry,
        }

    def expire_options(self, contract_ids) -> None:
        for cid in contract_ids:
            self.tracker.pop(cid, None)
            for key in [k for k in self.observations if k[0] == cid]:
                self.observations.pop(key, None)

    # --- test convenience ---
    def count_tracked(self) -> int:
        return len(self.tracker)

    def count_observations(self) -> int:
        return len(self.observations)


class PostgresOptionStore(OptionScanStore):
    """Neon-backed implementation. Delete-on-expiry keeps the DB lean (Planning Pack 11)."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def _cur(self):
        return self.conn.cursor()

    def get_option_contracts(self) -> list[OptionContractRef]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, security_id, underlying_symbol, underlying_security_id, exchange, "
                "instrument_type, expiry_date, strike, option_type, lot_size "
                "FROM option_contracts WHERE active = TRUE"
            )
            return [
                OptionContractRef(
                    id=r[0], security_id=str(r[1]), underlying_symbol=r[2], underlying_security_id=r[3],
                    exchange=r[4], instrument_type=r[5], expiry_date=r[6], strike=float(r[7]),
                    option_type=r[8], lot_size=r[9],
                )
                for r in cur.fetchall()
            ]

    def get_tracked_options(self) -> list[OptionTrackerState]:
        with self._cur() as cur:
            cur.execute(
                "SELECT contract_id, first_seen_date, entry_ltp, expiry_date "
                "FROM option_tracker WHERE status = 'active'"
            )
            return [OptionTrackerState(r[0], r[1], float(r[2]), r[3]) for r in cur.fetchall()]

    def enroll_option(self, contract_id, first_seen_date, entry_ltp, entry_iv, entry_oi, expiry_date) -> None:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO option_tracker (contract_id, first_seen_date, entry_ltp, entry_iv, "
                "entry_oi, expiry_date, status) VALUES (%s,%s,%s,%s,%s,%s,'active') "
                "ON CONFLICT (contract_id) DO NOTHING",
                (contract_id, first_seen_date, entry_ltp, entry_iv, entry_oi, expiry_date),
            )
        self.conn.commit()

    def record_option_observation(self, contract_id, trade_date, *, ltp, volume, oi, oi_change_pct,
                                  iv, delta, theta, gamma, vega, days_to_expiry, return_vs_entry) -> None:
        with self._cur() as cur:
            cur.execute("SELECT id FROM option_tracker WHERE contract_id = %s", (contract_id,))
            row = cur.fetchone()
            if not row:
                return
            cur.execute(
                "INSERT INTO option_observations (tracker_id, trade_date, ltp, volume, oi, "
                "oi_change_pct, iv, delta, theta, gamma, vega, days_to_expiry, return_vs_entry) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (tracker_id, trade_date) DO UPDATE SET "
                "ltp=EXCLUDED.ltp, volume=EXCLUDED.volume, oi=EXCLUDED.oi, "
                "oi_change_pct=EXCLUDED.oi_change_pct, iv=EXCLUDED.iv, delta=EXCLUDED.delta, "
                "theta=EXCLUDED.theta, gamma=EXCLUDED.gamma, vega=EXCLUDED.vega, "
                "days_to_expiry=EXCLUDED.days_to_expiry, return_vs_entry=EXCLUDED.return_vs_entry",
                (row[0], trade_date, ltp, volume, oi, oi_change_pct, iv, delta, theta, gamma, vega,
                 days_to_expiry, return_vs_entry),
            )
        self.conn.commit()

    def expire_options(self, contract_ids) -> None:
        ids = list(contract_ids)
        if not ids:
            return
        with self._cur() as cur:  # observations cascade-delete with the tracker row
            cur.execute("DELETE FROM option_tracker WHERE contract_id = ANY(%s)", (ids,))
        self.conn.commit()
