"""The nightly scan orchestration (Planning Pack/02_PROCESS_FLOWS Flow A).

trading-day check -> fetch today's OHLCV -> freshness gate -> store -> features -> per
strategy: signals (append-only) -> tracker (create/increment/complete) -> observations ->
metrics -> scan_run. Always emits a health artifact; alerts on failure. Idempotent: a
strategy whose scan_run already succeeded for the date is skipped (no double-insert).

Everything external (the store, the Dhan client, the alert sink) is injected, so the whole
flow runs in CI against a FakeStore with mocked Dhan responses.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

from ..config.strategies_loader import StrategyConfig
from ..data_layer.quotes import MAX_INSTRUMENTS_PER_CALL, parse_quote_response
from ..metrics.strategy_metrics import compute_strategy_metrics
from ..strategies.base import registered_strategies
from ..tracker.lifecycle import decide_tracker_actions
from ..utils import timeutils
from .context import ScanContext
from .features import compute_features
from .store import InstrumentRef, ScanStore


class ScanError(RuntimeError):
    pass


@dataclass
class ScanSummary:
    trade_date: str
    status: str = "pending"  # success | failed | skipped_non_trading_day
    error: Optional[str] = None
    instruments: int = 0
    features: int = 0
    per_strategy: dict = field(default_factory=dict)
    skipped_strategies: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _batches_from_refs(refs: Sequence[InstrumentRef], max_per_call: int = MAX_INSTRUMENTS_PER_CALL):
    batches: list[dict[str, list]] = []
    current: dict[str, list] = {}
    count = 0
    for ref in refs:
        if count >= max_per_call:
            batches.append(current)
            current, count = {}, 0
        sid = int(ref.security_id) if str(ref.security_id).isdigit() else ref.security_id
        current.setdefault(ref.exchange_segment, []).append(sid)
        count += 1
    if current:
        batches.append(current)
    return batches


def _emit_artifact(artifact_dir: Optional[str], summary: ScanSummary) -> None:
    if not artifact_dir:
        return
    d = Path(artifact_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"scan_{summary.trade_date}.json").write_text(
        json.dumps(summary.to_dict(), indent=2), encoding="utf-8"
    )


def run_scan(
    trade_date: _dt.date,
    *,
    store: ScanStore,
    dhan_client,
    strategy_configs: Sequence[StrategyConfig],
    horizon_days: int = 100,
    rsi_period: int = 14,
    volume_lookback: int = 14,
    artifact_dir: Optional[str] = None,
    alert: Optional[Callable[[str], bool]] = None,
    logger=None,
) -> ScanSummary:
    summary = ScanSummary(trade_date=trade_date.isoformat())

    def _log(msg: str) -> None:
        if logger:
            logger.info(msg)

    if not timeutils.is_trading_day(trade_date):
        summary.status = "skipped_non_trading_day"
        _log(f"{trade_date} is not a trading day; nothing written.")
        _emit_artifact(artifact_dir, summary)
        return summary

    try:
        instruments = store.get_active_instruments()
        summary.instruments = len(instruments)
        if not instruments:
            raise ScanError("no active instruments in the universe")

        # 1. Fetch today's OHLCV (bulk quote, batched <=1000/call).
        quotes = {}
        for batch in _batches_from_refs(instruments):
            quotes.update(parse_quote_response(dhan_client.quote(batch), trade_date))

        # 2. Freshness gate: never write an empty/garbage day.
        if not quotes:
            raise ScanError("empty quote response — refusing to write (freshness gate)")

        # 3. Store today's bars (idempotent) and remember opens/closes.
        by_secid = {str(r.security_id): r for r in instruments}
        opens_by_instrument: dict[int, float] = {}
        close_by_instrument: dict[int, float] = {}
        for secid, bar in quotes.items():
            ref = by_secid.get(secid)
            if ref is None:
                continue
            store.upsert_price_bars(ref.id, [bar])
            opens_by_instrument[ref.id] = bar.open
            close_by_instrument[ref.id] = bar.close

        # 4. Fill entry_next_open for entries first seen on the previous trading day (M3).
        prev = timeutils.previous_trading_day(trade_date)
        store.fill_pending_next_open(trade_date, prev, opens_by_instrument)

        # 5. Compute features for the latest bar.
        features = []
        for ref in instruments:
            bars = store.get_trailing_prices(ref.id, trade_date)
            f = compute_features(ref.id, bars, rsi_period=rsi_period, volume_lookback=volume_lookback)
            if f is not None and f.trade_date == trade_date:
                features.append(f)
        summary.features = len(features)
        ctx = ScanContext(trade_date=trade_date, features=features)

        # 6. Run each active strategy.
        registry = registered_strategies()
        for cfg in strategy_configs:
            if not cfg.active:
                continue
            strat_id = store.get_strategy_id(cfg.key)
            if store.scan_run_done(strat_id, trade_date):
                summary.skipped_strategies.append(cfg.key)  # idempotent: already done
                continue

            run_id = store.start_scan_run(strat_id, trade_date)
            try:
                strategy = registry[cfg.key](cfg.params)
                signals = list(strategy.evaluate(ctx))
                store.insert_signals(run_id, strat_id, trade_date, signals)

                signaled_ids = [s.instrument_id for s in signals]
                closes = {s.instrument_id: s.close for s in signals}
                actions = decide_tracker_actions(
                    trade_date, signaled_ids, store.get_active_tracker(strat_id), horizon_days
                )
                for iid in actions.to_increment:
                    store.increment_tracker_entry(iid, strat_id, trade_date)
                for iid in actions.to_create:
                    store.create_tracker_entry(iid, strat_id, trade_date, closes[iid], horizon_days)

                # Observations for every active entry (incl. those completing today).
                for e in store.get_active_tracker(strat_id):
                    c = close_by_instrument.get(e.instrument_id)
                    if c is None:
                        continue
                    n = timeutils.trading_days_between(e.first_seen_date, trade_date)
                    rvc = (c / e.entry_close - 1.0) if e.entry_close else None
                    rvo = (c / e.entry_next_open - 1.0) if e.entry_next_open else None
                    store.record_observation(e.instrument_id, strat_id, trade_date, n, c, rvc, rvo)

                if actions.to_complete:
                    store.complete_tracker_entries(strat_id, actions.to_complete)

                # Edge metrics (first cut): hit rate (+ excess vs universe base rate).
                metrics = compute_strategy_metrics(
                    store.latest_entry_returns(strat_id),
                    base_returns=store.universe_window_returns(trade_date, horizon_days),
                    horizon_days=horizon_days,
                )
                store.upsert_strategy_metrics(strat_id, metrics)

                store.finish_scan_run(run_id, "success", len(signals))
                summary.per_strategy[cfg.key] = {
                    "signals": len(signals),
                    "created": len(actions.to_create),
                    "incremented": len(actions.to_increment),
                    "completed": len(actions.to_complete),
                }
                _log(f"{cfg.key}: {len(signals)} signals, +{len(actions.to_create)} new entries")
            except Exception as err:
                store.finish_scan_run(run_id, "failed", 0, str(err))
                raise

        summary.status = "success"
        _emit_artifact(artifact_dir, summary)
        return summary

    except Exception as err:  # watchdog: loud failure, always an artifact + alert
        summary.status = "failed"
        summary.error = str(err)
        _emit_artifact(artifact_dir, summary)
        if alert:
            alert(f"[The Swing Trades] scan FAILED for {trade_date}: {err}")
        if logger:
            logger.exception("scan failed")
        raise
