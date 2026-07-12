"""The persistence boundary the scan pipeline writes through.

`ScanStore` is the interface. `FakeStore` is an in-memory implementation that enforces the
same uniqueness rules (so tests prove idempotency without a database). `PostgresStore` is the
real Neon-backed implementation. Keeping the pipeline behind this interface is what lets the
'rows actually written' integration test run in CI without external services.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional, Sequence

from ..data_layer.models import PriceBar
from ..strategies.base import SignalRow
from ..tracker.lifecycle import TrackerEntryState
from .features import InstrumentFeatures  # noqa: F401  (re-exported convenience)


@dataclass(frozen=True)
class InstrumentRef:
    id: int
    isin: str
    security_id: str
    exchange_segment: str
    series: Optional[str] = None  # BSE group / NSE series — drives the Step 0b turnover gate


@dataclass(frozen=True)
class NewsEventRow:
    """One row of the news_events ledger (the canonical isin x catalyst_tag x window event)."""

    id: int
    isin: str
    instrument_id: Optional[int]
    catalyst_tag: str
    event_date: _dt.date
    provenance: str
    headline: Optional[str]
    enrolled: bool


class ScanStore:
    """Interface. See FakeStore for the canonical in-memory semantics."""

    def get_active_instruments(self) -> list[InstrumentRef]: raise NotImplementedError
    def get_tracked_instrument_ids(self) -> set[int]: raise NotImplementedError
    def upsert_price_bars(self, instrument_id: int, bars: Sequence[PriceBar]) -> int: raise NotImplementedError
    def get_trailing_prices(self, instrument_id: int, up_to: _dt.date) -> list[PriceBar]: raise NotImplementedError
    def get_strategy_id(self, key: str) -> int: raise NotImplementedError
    def scan_run_done(self, strategy_id: int, trade_date: _dt.date) -> bool: raise NotImplementedError
    def last_successful_scan_date(self) -> Optional[_dt.date]: raise NotImplementedError
    def start_scan_run(self, strategy_id: int, trade_date: _dt.date) -> int: raise NotImplementedError
    def finish_scan_run(self, run_id: int, status: str, qualified_count: int, error: Optional[str] = None) -> None: raise NotImplementedError
    def insert_signals(self, run_id: int, strategy_id: int, trade_date: _dt.date, signals: Sequence[SignalRow]) -> int: raise NotImplementedError
    def get_active_tracker(self, strategy_id: int) -> list[TrackerEntryState]: raise NotImplementedError
    def create_tracker_entry(self, instrument_id: int, strategy_id: int, first_seen_date: _dt.date, entry_close: float, horizon_days: int, *, catalyst_tag: Optional[str] = None, catalyst_source: Optional[str] = None, catalyst_headline: Optional[str] = None, catalyst_url: Optional[str] = None, catalyst_decision: Optional[str] = None) -> None: raise NotImplementedError
    def increment_tracker_entry(self, instrument_id: int, strategy_id: int, last_seen_date: _dt.date) -> None: raise NotImplementedError
    def complete_tracker_entries(self, strategy_id: int, instrument_ids: Sequence[int]) -> None: raise NotImplementedError
    def fill_pending_next_open(self, trade_date: _dt.date, prev_trading_day: _dt.date, opens_by_instrument: dict[int, float]) -> int: raise NotImplementedError
    def record_observation(self, instrument_id: int, strategy_id: int, trade_date: _dt.date, trading_day_n: int, close: float, return_vs_close: float, return_vs_open: Optional[float]) -> None: raise NotImplementedError
    def latest_entry_returns(self, strategy_id: int) -> list[float]: raise NotImplementedError
    def universe_window_returns(self, trade_date: _dt.date, lookback: int) -> list[float]: raise NotImplementedError
    def upsert_strategy_metrics(self, strategy_id: int, metrics) -> None: raise NotImplementedError
    # --- news_positive: instrument expand-on-the-fly + news_events ledger (Stage-B dedup) ---
    def ensure_instrument(self, instrument) -> int: raise NotImplementedError
    def news_source_exists(self, source_uid: str) -> bool: raise NotImplementedError
    def find_open_news_event(self, isin: str, catalyst_tag: str, min_date: _dt.date, max_date: _dt.date): raise NotImplementedError
    def create_news_event(self, isin, instrument_id, catalyst_tag, event_date, window_end_date, provenance, headline) -> int: raise NotImplementedError
    def attach_news_source(self, event_id: int, source_uid: str, source: str, url: Optional[str]) -> None: raise NotImplementedError
    def set_news_event_provenance(self, event_id: int, provenance: str) -> None: raise NotImplementedError
    def get_unenrolled_news_events(self) -> list: raise NotImplementedError
    def mark_news_event_enrolled(self, event_id: int) -> None: raise NotImplementedError


class FakeStore(ScanStore):
    def __init__(self) -> None:
        self.instruments: list[InstrumentRef] = []
        self.strategy_ids: dict[str, int] = {}
        self.prices: dict[tuple[int, _dt.date], PriceBar] = {}
        self.scan_runs: dict[tuple[int, _dt.date], dict] = {}
        self.signals: list[dict] = []
        self.tracker: dict[tuple[int, int], dict] = {}
        self.observations: dict[tuple[int, int, _dt.date], dict] = {}
        self.metrics: dict[tuple[int, int], object] = {}
        self._run_seq = 0
        self.news_events: dict[int, dict] = {}
        self.news_source_uids: set[str] = set()
        self._news_seq = 0

    # --- setup helpers (test convenience) ---
    def add_instrument(self, ref: InstrumentRef) -> None:
        self.instruments.append(ref)

    def register_strategy(self, key: str, strategy_id: int) -> None:
        self.strategy_ids[key] = strategy_id

    # --- instruments / prices ---
    def get_active_instruments(self) -> list[InstrumentRef]:
        return list(self.instruments)

    def get_tracked_instrument_ids(self) -> set[int]:
        return {iid for (iid, _sid), e in self.tracker.items() if e["status"] == "active"}

    def upsert_price_bars(self, instrument_id: int, bars: Sequence[PriceBar]) -> int:
        for b in bars:
            self.prices[(instrument_id, b.trade_date)] = b  # idempotent on (instrument, date)
        return len(bars)

    def get_trailing_prices(self, instrument_id: int, up_to: _dt.date) -> list[PriceBar]:
        bars = [b for (iid, d), b in self.prices.items() if iid == instrument_id and d <= up_to]
        return sorted(bars, key=lambda b: b.trade_date)

    # --- strategies / scan runs ---
    def get_strategy_id(self, key: str) -> int:
        return self.strategy_ids[key]

    def scan_run_done(self, strategy_id: int, trade_date: _dt.date) -> bool:
        run = self.scan_runs.get((strategy_id, trade_date))
        return bool(run and run["status"] == "success")

    def last_successful_scan_date(self) -> Optional[_dt.date]:
        dates = [d for (_sid, d), run in self.scan_runs.items() if run["status"] == "success"]
        return max(dates) if dates else None

    def start_scan_run(self, strategy_id: int, trade_date: _dt.date) -> int:
        key = (strategy_id, trade_date)
        if key in self.scan_runs:
            self.scan_runs[key]["status"] = "running"
            return self.scan_runs[key]["id"]
        self._run_seq += 1
        self.scan_runs[key] = {"id": self._run_seq, "status": "running", "qualified_count": 0, "error": None}
        return self._run_seq

    def finish_scan_run(self, run_id: int, status: str, qualified_count: int, error: Optional[str] = None) -> None:
        for run in self.scan_runs.values():
            if run["id"] == run_id:
                run.update(status=status, qualified_count=qualified_count, error=error)
                return

    def insert_signals(self, run_id: int, strategy_id: int, trade_date: _dt.date, signals: Sequence[SignalRow]) -> int:
        for s in signals:
            self.signals.append(
                {
                    "scan_run_id": run_id,
                    "strategy_id": strategy_id,
                    "instrument_id": s.instrument_id,
                    "trade_date": trade_date,
                    "close": s.close,
                    "rsi": s.rsi,
                    "volume_ratio": s.volume_ratio,
                    "candle_type": s.candle_type,
                }
            )
        return len(signals)

    # --- tracker ---
    def get_active_tracker(self, strategy_id: int) -> list[TrackerEntryState]:
        out = []
        for (iid, sid), e in self.tracker.items():
            if sid == strategy_id and e["status"] == "active":
                out.append(
                    TrackerEntryState(
                        instrument_id=iid,
                        strategy_id=sid,
                        first_seen_date=e["first_seen_date"],
                        status=e["status"],
                        appearance_count=e["appearance_count"],
                        entry_close=e["entry_close"],
                        entry_next_open=e["entry_next_open"],
                        horizon_days=e["horizon_days"],
                    )
                )
        return out

    def create_tracker_entry(self, instrument_id, strategy_id, first_seen_date, entry_close, horizon_days,
                             *, catalyst_tag=None, catalyst_source=None, catalyst_headline=None,
                             catalyst_url=None, catalyst_decision=None) -> None:
        key = (instrument_id, strategy_id)
        if key in self.tracker:  # unique (instrument, strategy) — never double-create
            return
        self.tracker[key] = {
            "first_seen_date": first_seen_date,
            "entry_close": entry_close,
            "entry_next_open": None,
            "appearance_count": 1,
            "last_seen_date": first_seen_date,
            "status": "active",
            "horizon_days": horizon_days,
            "catalyst_tag": catalyst_tag,
        }

    def increment_tracker_entry(self, instrument_id, strategy_id, last_seen_date) -> None:
        e = self.tracker.get((instrument_id, strategy_id))
        if e:
            e["appearance_count"] += 1
            e["last_seen_date"] = last_seen_date  # entry_close NEVER changes (Rule 3)

    def complete_tracker_entries(self, strategy_id, instrument_ids) -> None:
        for iid in instrument_ids:
            e = self.tracker.get((iid, strategy_id))
            if e:
                e["status"] = "completed"

    def fill_pending_next_open(self, trade_date, prev_trading_day, opens_by_instrument) -> int:
        filled = 0
        for (iid, _sid), e in self.tracker.items():
            if e["entry_next_open"] is None and e["first_seen_date"] == prev_trading_day:
                if iid in opens_by_instrument:
                    e["entry_next_open"] = opens_by_instrument[iid]
                    filled += 1
        return filled

    # --- observations / metrics ---
    def record_observation(self, instrument_id, strategy_id, trade_date, trading_day_n, close, return_vs_close, return_vs_open) -> None:
        self.observations[(instrument_id, strategy_id, trade_date)] = {
            "trading_day_n": trading_day_n,
            "close": close,
            "return_vs_close": return_vs_close,
            "return_vs_open": return_vs_open,
        }

    def latest_entry_returns(self, strategy_id: int) -> list[float]:
        latest: dict[int, tuple[_dt.date, float]] = {}
        for (iid, sid, d), obs in self.observations.items():
            if sid != strategy_id:
                continue
            if iid not in latest or d > latest[iid][0]:
                latest[iid] = (d, obs["return_vs_close"])
        return [r for _d, r in latest.values()]

    def universe_window_returns(self, trade_date: _dt.date, lookback: int) -> list[float]:
        returns: list[float] = []
        for ref in self.instruments:
            bars = self.get_trailing_prices(ref.id, trade_date)
            if len(bars) < 2:
                continue
            then = bars[-1 - lookback] if len(bars) > lookback else bars[0]
            if then.close:
                returns.append(bars[-1].close / then.close - 1.0)
        return returns

    def upsert_strategy_metrics(self, strategy_id: int, metrics) -> None:
        self.metrics[(strategy_id, getattr(metrics, "horizon_days", 0))] = metrics

    # --- news_positive ---
    def ensure_instrument(self, instrument) -> int:
        for ref in self.instruments:
            if ref.isin == instrument.isin:
                return ref.id
        new_id = max((r.id for r in self.instruments), default=0) + 1
        seg = getattr(instrument, "exchange_segment", None) or f"{instrument.exchange_pref}_EQ"
        self.instruments.append(
            InstrumentRef(id=new_id, isin=instrument.isin, security_id=instrument.security_id,
                          exchange_segment=seg, series=instrument.series)
        )
        return new_id

    def news_source_exists(self, source_uid: str) -> bool:
        return source_uid in self.news_source_uids

    def _news_row(self, e: dict) -> NewsEventRow:
        return NewsEventRow(id=e["id"], isin=e["isin"], instrument_id=e["instrument_id"],
                            catalyst_tag=e["catalyst_tag"], event_date=e["event_date"],
                            provenance=e["provenance"], headline=e["headline"], enrolled=e["enrolled"])

    def find_open_news_event(self, isin, catalyst_tag, min_date, max_date):
        best = None
        for e in self.news_events.values():
            if e["isin"] == isin and e["catalyst_tag"] == catalyst_tag and min_date <= e["event_date"] <= max_date:
                if best is None or e["event_date"] > best["event_date"]:
                    best = e
        return self._news_row(best) if best else None

    def create_news_event(self, isin, instrument_id, catalyst_tag, event_date, window_end_date, provenance, headline) -> int:
        self._news_seq += 1
        self.news_events[self._news_seq] = {
            "id": self._news_seq, "isin": isin, "instrument_id": instrument_id,
            "catalyst_tag": catalyst_tag, "event_date": event_date, "window_end_date": window_end_date,
            "provenance": provenance, "headline": headline, "enrolled": False,
        }
        return self._news_seq

    def attach_news_source(self, event_id, source_uid, source, url) -> None:
        self.news_source_uids.add(source_uid)  # UNIQUE(source_uid) in Postgres; idempotency here

    def set_news_event_provenance(self, event_id, provenance) -> None:
        if event_id in self.news_events:
            self.news_events[event_id]["provenance"] = provenance

    def get_unenrolled_news_events(self) -> list:
        return [self._news_row(e) for e in self.news_events.values() if not e["enrolled"]]

    def mark_news_event_enrolled(self, event_id) -> None:
        if event_id in self.news_events:
            self.news_events[event_id]["enrolled"] = True

    # --- test convenience counts ---
    def count_signals(self) -> int:
        return len(self.signals)

    def count_tracker_entries(self) -> int:
        return len(self.tracker)


class PostgresStore(ScanStore):
    """Neon-backed implementation. Exercised against a real Postgres in CI (the integration
    test gated on DATABASE_URL); the in-memory FakeStore covers local/unit runs."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def _cur(self):
        return self.conn.cursor()

    def get_active_instruments(self) -> list[InstrumentRef]:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, isin, security_id, "
                "CASE WHEN exchange_pref='BSE' THEN 'BSE_EQ' ELSE 'NSE_EQ' END, series "
                "FROM instruments WHERE active = TRUE"
            )
            return [InstrumentRef(*row) for row in cur.fetchall()]

    def get_tracked_instrument_ids(self) -> set[int]:
        with self._cur() as cur:
            cur.execute("SELECT DISTINCT instrument_id FROM tracker_entries WHERE status = 'active'")
            return {row[0] for row in cur.fetchall()}

    def upsert_price_bars(self, instrument_id: int, bars: Sequence[PriceBar]) -> int:
        from ..db.writes import upsert_price_history

        return upsert_price_history(self.conn, instrument_id, bars)

    def get_trailing_prices(self, instrument_id: int, up_to: _dt.date) -> list[PriceBar]:
        with self._cur() as cur:
            cur.execute(
                "SELECT trade_date, open, high, low, close, volume FROM price_history "
                "WHERE instrument_id = %s AND trade_date <= %s ORDER BY trade_date",
                (instrument_id, up_to),
            )
            return [
                PriceBar(d, float(o), float(h), float(low), float(c), int(v))
                for d, o, h, low, c, v in cur.fetchall()
            ]

    def get_strategy_id(self, key: str) -> int:
        with self._cur() as cur:
            cur.execute("SELECT id FROM strategies WHERE key = %s", (key,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"strategy not registered: {key}")
            return row[0]

    def scan_run_done(self, strategy_id: int, trade_date: _dt.date) -> bool:
        with self._cur() as cur:
            cur.execute(
                "SELECT 1 FROM scan_runs WHERE strategy_id=%s AND trade_date=%s AND status='success'",
                (strategy_id, trade_date),
            )
            return cur.fetchone() is not None

    def last_successful_scan_date(self) -> Optional[_dt.date]:
        with self._cur() as cur:
            cur.execute("SELECT max(trade_date) FROM scan_runs WHERE status='success'")
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None

    def start_scan_run(self, strategy_id: int, trade_date: _dt.date) -> int:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO scan_runs (strategy_id, trade_date, status) VALUES (%s,%s,'running') "
                "ON CONFLICT (strategy_id, trade_date) DO UPDATE SET status='running', "
                "started_at=now(), finished_at=NULL, error=NULL RETURNING id",
                (strategy_id, trade_date),
            )
            run_id = cur.fetchone()[0]
        self.conn.commit()
        return run_id

    def finish_scan_run(self, run_id: int, status: str, qualified_count: int, error: Optional[str] = None) -> None:
        with self._cur() as cur:
            cur.execute(
                "UPDATE scan_runs SET status=%s, qualified_count=%s, error=%s, finished_at=now() WHERE id=%s",
                (status, qualified_count, error, run_id),
            )
        self.conn.commit()

    def insert_signals(self, run_id, strategy_id, trade_date, signals) -> int:
        with self._cur() as cur:
            for s in signals:
                cur.execute(
                    "INSERT INTO scan_signals (scan_run_id, instrument_id, strategy_id, trade_date, "
                    "close, rsi, volume_ratio, candle_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (run_id, s.instrument_id, strategy_id, trade_date, s.close, s.rsi, s.volume_ratio, s.candle_type),
                )
        self.conn.commit()
        return len(list(signals))

    def get_active_tracker(self, strategy_id: int) -> list[TrackerEntryState]:
        with self._cur() as cur:
            cur.execute(
                "SELECT instrument_id, first_seen_date, appearance_count, entry_close, entry_next_open, "
                "tracking_horizon_days FROM tracker_entries WHERE strategy_id=%s AND status='active'",
                (strategy_id,),
            )
            return [
                TrackerEntryState(
                    instrument_id=iid, strategy_id=strategy_id, first_seen_date=fsd, status="active",
                    appearance_count=ac, entry_close=float(ec),
                    entry_next_open=(float(eno) if eno is not None else None), horizon_days=hz,
                )
                for iid, fsd, ac, ec, eno, hz in cur.fetchall()
            ]

    def create_tracker_entry(self, instrument_id, strategy_id, first_seen_date, entry_close, horizon_days,
                             *, catalyst_tag=None, catalyst_source=None, catalyst_headline=None,
                             catalyst_url=None, catalyst_decision=None) -> None:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO tracker_entries (instrument_id, strategy_id, first_seen_date, entry_close, "
                "appearance_count, last_seen_date, tracking_horizon_days, status, "
                "catalyst_tag, catalyst_source, catalyst_headline, catalyst_url, catalyst_decision) "
                "VALUES (%s,%s,%s,%s,1,%s,%s,'active',%s,%s,%s,%s,%s) "
                "ON CONFLICT (instrument_id, strategy_id) DO NOTHING",
                (instrument_id, strategy_id, first_seen_date, entry_close, first_seen_date, horizon_days,
                 catalyst_tag, catalyst_source, catalyst_headline, catalyst_url, catalyst_decision),
            )
        self.conn.commit()

    def increment_tracker_entry(self, instrument_id, strategy_id, last_seen_date) -> None:
        with self._cur() as cur:
            cur.execute(
                "UPDATE tracker_entries SET appearance_count=appearance_count+1, last_seen_date=%s "
                "WHERE instrument_id=%s AND strategy_id=%s",
                (last_seen_date, instrument_id, strategy_id),
            )
        self.conn.commit()

    def complete_tracker_entries(self, strategy_id, instrument_ids) -> None:
        ids = list(instrument_ids)
        if not ids:
            return
        with self._cur() as cur:
            cur.execute(
                "UPDATE tracker_entries SET status='completed' WHERE strategy_id=%s AND instrument_id = ANY(%s)",
                (strategy_id, ids),
            )
        self.conn.commit()

    def fill_pending_next_open(self, trade_date, prev_trading_day, opens_by_instrument) -> int:
        if not opens_by_instrument:
            return 0
        filled = 0
        with self._cur() as cur:
            for iid, open_px in opens_by_instrument.items():
                cur.execute(
                    "UPDATE tracker_entries SET entry_next_open=%s WHERE instrument_id=%s "
                    "AND entry_next_open IS NULL AND first_seen_date=%s",
                    (open_px, iid, prev_trading_day),
                )
                filled += cur.rowcount or 0
        self.conn.commit()
        return filled

    def record_observation(self, instrument_id, strategy_id, trade_date, trading_day_n, close, return_vs_close, return_vs_open) -> None:
        with self._cur() as cur:
            cur.execute(
                "SELECT id FROM tracker_entries WHERE instrument_id=%s AND strategy_id=%s",
                (instrument_id, strategy_id),
            )
            row = cur.fetchone()
            if not row:
                return
            cur.execute(
                "INSERT INTO tracker_observations (tracker_entry_id, trade_date, trading_day_n, close, "
                "return_vs_close, return_vs_open) VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (tracker_entry_id, trade_date) DO UPDATE SET "
                "trading_day_n=EXCLUDED.trading_day_n, close=EXCLUDED.close, "
                "return_vs_close=EXCLUDED.return_vs_close, return_vs_open=EXCLUDED.return_vs_open",
                (row[0], trade_date, trading_day_n, close, return_vs_close, return_vs_open),
            )
        self.conn.commit()

    def latest_entry_returns(self, strategy_id: int) -> list[float]:
        with self._cur() as cur:
            cur.execute(
                "SELECT DISTINCT ON (o.tracker_entry_id) o.return_vs_close FROM tracker_observations o "
                "JOIN tracker_entries t ON t.id = o.tracker_entry_id WHERE t.strategy_id=%s "
                "ORDER BY o.tracker_entry_id, o.trade_date DESC",
                (strategy_id,),
            )
            return [float(r[0]) for r in cur.fetchall() if r[0] is not None]

    def universe_window_returns(self, trade_date: _dt.date, lookback: int) -> list[float]:
        # Computed in Python in FakeStore; for Postgres this is a heavier query deferred to
        # the metrics-broadening step. Return [] here so excess is simply not reported yet.
        return []

    def upsert_strategy_metrics(self, strategy_id: int, metrics) -> None:
        m = metrics
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO strategy_metrics (strategy_id, horizon_days, sample_size, hit_rate, base_rate, "
                "excess_hit_rate, avg_win, avg_loss, expectancy, median_return, hit_rate_at_5pct, hit_rate_at_10pct) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (strategy_id, horizon_days) DO UPDATE SET computed_at=now(), "
                "sample_size=EXCLUDED.sample_size, hit_rate=EXCLUDED.hit_rate, base_rate=EXCLUDED.base_rate, "
                "excess_hit_rate=EXCLUDED.excess_hit_rate, avg_win=EXCLUDED.avg_win, avg_loss=EXCLUDED.avg_loss, "
                "expectancy=EXCLUDED.expectancy, median_return=EXCLUDED.median_return, "
                "hit_rate_at_5pct=EXCLUDED.hit_rate_at_5pct, hit_rate_at_10pct=EXCLUDED.hit_rate_at_10pct",
                (strategy_id, m.horizon_days, m.sample_size, m.hit_rate, m.base_rate, m.excess_hit_rate,
                 m.avg_win, m.avg_loss, m.expectancy, m.median_return, m.hit_rate_at_5pct, m.hit_rate_at_10pct),
            )
        self.conn.commit()

    # --- news_positive ---
    def ensure_instrument(self, instrument) -> int:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO instruments (isin, security_id, nse_symbol, bse_scrip_code, exchange_pref, "
                "segment, symbol_name, series, lot_size, asm_gsm_flag, active, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,'E',%s,%s,%s,%s,TRUE,now()) "
                "ON CONFLICT (isin) DO UPDATE SET active=TRUE, updated_at=now() RETURNING id",
                (instrument.isin, instrument.security_id, instrument.nse_symbol, instrument.bse_scrip_code,
                 instrument.exchange_pref, instrument.symbol_name, instrument.series,
                 instrument.lot_size, instrument.asm_gsm_flag),
            )
            iid = cur.fetchone()[0]
        self.conn.commit()
        return iid

    def news_source_exists(self, source_uid: str) -> bool:
        with self._cur() as cur:
            cur.execute("SELECT 1 FROM news_event_sources WHERE source_uid=%s", (source_uid,))
            return cur.fetchone() is not None

    def find_open_news_event(self, isin, catalyst_tag, min_date, max_date):
        with self._cur() as cur:
            cur.execute(
                "SELECT id, isin, instrument_id, catalyst_tag, event_date, provenance, headline, enrolled "
                "FROM news_events WHERE isin=%s AND catalyst_tag=%s AND event_date BETWEEN %s AND %s "
                "ORDER BY event_date DESC LIMIT 1",
                (isin, catalyst_tag, min_date, max_date),
            )
            row = cur.fetchone()
        if not row:
            return None
        return NewsEventRow(id=row[0], isin=row[1], instrument_id=row[2], catalyst_tag=row[3],
                            event_date=row[4], provenance=row[5], headline=row[6], enrolled=row[7])

    def create_news_event(self, isin, instrument_id, catalyst_tag, event_date, window_end_date, provenance, headline) -> int:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO news_events (isin, instrument_id, catalyst_tag, event_date, window_end_date, "
                "provenance, headline) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (isin, instrument_id, catalyst_tag, event_date, window_end_date, provenance, headline),
            )
            eid = cur.fetchone()[0]
        self.conn.commit()
        return eid

    def attach_news_source(self, event_id, source_uid, source, url) -> None:
        with self._cur() as cur:
            cur.execute(
                "INSERT INTO news_event_sources (event_id, source_uid, source, url) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (source_uid) DO NOTHING",
                (event_id, source_uid, source, url),
            )
        self.conn.commit()

    def set_news_event_provenance(self, event_id, provenance) -> None:
        with self._cur() as cur:
            cur.execute("UPDATE news_events SET provenance=%s, updated_at=now() WHERE id=%s", (provenance, event_id))
        self.conn.commit()

    def get_unenrolled_news_events(self) -> list:
        with self._cur() as cur:
            cur.execute(
                "SELECT id, isin, instrument_id, catalyst_tag, event_date, provenance, headline, enrolled "
                "FROM news_events WHERE enrolled = FALSE ORDER BY event_date"
            )
            rows = cur.fetchall()
        return [NewsEventRow(id=r[0], isin=r[1], instrument_id=r[2], catalyst_tag=r[3], event_date=r[4],
                             provenance=r[5], headline=r[6], enrolled=r[7]) for r in rows]

    def mark_news_event_enrolled(self, event_id) -> None:
        with self._cur() as cur:
            cur.execute("UPDATE news_events SET enrolled=TRUE, updated_at=now() WHERE id=%s", (event_id,))
        self.conn.commit()
