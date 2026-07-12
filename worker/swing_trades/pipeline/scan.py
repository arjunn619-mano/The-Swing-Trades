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
import time
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


# Step 0b turnover gate: only the newly-widened BSE groups (Step 0a) are subject to the
# per-name turnover floor. Curated liquid groups (NSE EQ/BE, BSE A/B), any unknown/blank
# series, and any already-tracked instrument are NEVER gated — the floor can only ever cull a
# newly-widened, never-tracked, sub-floor name, so it can't drop an existing or tracked stock.
_GATED_SERIES = frozenset({"X", "XT", "T"})


@dataclass
class ScanSummary:
    trade_date: str
    status: str = "pending"  # success | failed | skipped_non_trading_day
    error: Optional[str] = None
    instruments: int = 0
    features: int = 0
    gated_illiquid: int = 0  # widened-group names skipped by the turnover floor (Step 0b)
    per_strategy: dict = field(default_factory=dict)
    skipped_strategies: list = field(default_factory=list)
    news: dict = field(default_factory=dict)  # news_positive enrolment counts (Step 8)

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


def _enrol_news_events(store, trade_date, close_by_instrument, horizon_days):
    """Price + enrol unenrolled news_events into the news_positive tracker: entry = today's EOD
    close (permanent, Rule 3), grows forward, no history backfill. Reuses the standard tracker
    mechanics. A stock already news-tracked from a distinct earlier catalyst gets appearance_count++
    instead of a new row; a just-activated instrument not yet quoted is skipped (next session prices
    it). Also observes every active news_positive entry + completes elapsed windows + refreshes
    metrics. Caller wraps this so it can never break the systematic scan."""
    strat_id = store.get_strategy_id("news_positive")  # raises if not registered -> caller guards
    active_ids = {e.instrument_id for e in store.get_active_tracker(strat_id)}
    created = incremented = no_price = 0
    for ev in store.get_unenrolled_news_events():
        if ev.instrument_id is None:
            continue
        close = close_by_instrument.get(ev.instrument_id)
        if close is None:
            no_price += 1
            continue
        if ev.instrument_id in active_ids:
            store.increment_tracker_entry(ev.instrument_id, strat_id, trade_date)
            incremented += 1
        else:
            store.create_tracker_entry(
                ev.instrument_id, strat_id, trade_date, close, horizon_days,
                catalyst_tag=ev.catalyst_tag, catalyst_headline=ev.headline,
            )
            active_ids.add(ev.instrument_id)
            created += 1
        store.mark_news_event_enrolled(ev.id)

    for e in store.get_active_tracker(strat_id):
        c = close_by_instrument.get(e.instrument_id)
        if c is None:
            continue
        n = timeutils.trading_days_between(e.first_seen_date, trade_date)
        rvc = (c / e.entry_close - 1.0) if e.entry_close else None
        rvo = (c / e.entry_next_open - 1.0) if e.entry_next_open else None
        store.record_observation(e.instrument_id, strat_id, trade_date, n, c, rvc, rvo)
    to_complete = [
        e.instrument_id for e in store.get_active_tracker(strat_id)
        if timeutils.trading_days_between(e.first_seen_date, trade_date) >= horizon_days
    ]
    if to_complete:
        store.complete_tracker_entries(strat_id, to_complete)
    metrics = compute_strategy_metrics(
        store.latest_entry_returns(strat_id),
        base_returns=store.universe_window_returns(trade_date, horizon_days),
        horizon_days=horizon_days,
    )
    store.upsert_strategy_metrics(strat_id, metrics)
    return {"created": created, "incremented": incremented, "no_price": no_price}


def run_scan(
    trade_date: _dt.date,
    *,
    store: ScanStore,
    dhan_client,
    strategy_configs: Sequence[StrategyConfig],
    horizon_days: int = 100,
    rsi_period: int = 14,
    volume_lookback: int = 14,
    ema_fast: int = 9,
    ema_mid: int = 15,
    ema_long: int = 200,
    quote_interval: float = 1.1,   # Dhan Quote API limit is 1 req/sec — space the batches
    turnover_floor: float = 0.0,   # Step 0b: min close*volume for a widened BSE X/XT/T name; 0 disables
    enable_news: bool = False,     # Step 8: price+enrol pending news_events into news_positive
    sleep: Callable[[float], None] = time.sleep,
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

        # 1. Fetch today's OHLCV (bulk quote, <=1000 ids/call). Dhan's Quote API is capped at
        #    1 request/second, so space the batches out (firing them back-to-back tripped 429/805).
        quotes = {}
        for i, batch in enumerate(_batches_from_refs(instruments)):
            if i and quote_interval and sleep:
                sleep(quote_interval)
            quotes.update(parse_quote_response(dhan_client.quote(batch), trade_date))

        # 2. Freshness gate: never write an empty/garbage day.
        if not quotes:
            raise ScanError("empty quote response — refusing to write (freshness gate)")

        # 3. Store today's bars (idempotent) and remember opens/closes.
        #    Turnover gate (Step 0b): keep genuinely-dead widened-group shells (BSE X/XT/T) out
        #    of the stored/tracked set to bound storage. It NEVER touches curated groups
        #    (NSE EQ/BE, BSE A/B) or any already-tracked instrument, so it can't drop an existing
        #    name or corrupt an in-flight 100-day tracker window. floor <= 0 disables it.
        by_secid = {str(r.security_id): r for r in instruments}
        # Protect from the turnover gate: actively-tracked names AND (under option B) any name with a
        # PENDING news_event — otherwise an illiquid news pick would be gated forever and never priced
        # to enrol (it isn't "tracked" until it's enrolled, and it can't enrol without a price).
        tracked_ids = store.get_tracked_instrument_ids() if turnover_floor > 0 else set()
        if turnover_floor > 0 and enable_news:
            tracked_ids = tracked_ids | store.get_pending_news_instrument_ids()
        opens_by_instrument: dict[int, float] = {}
        close_by_instrument: dict[int, float] = {}
        gated_illiquid = 0
        for secid, bar in quotes.items():
            ref = by_secid.get(secid)
            if ref is None:
                continue
            if (
                turnover_floor > 0
                and (ref.series or "").upper() in _GATED_SERIES
                and ref.id not in tracked_ids
                and (bar.close * bar.volume) < turnover_floor
            ):
                gated_illiquid += 1
                continue
            store.upsert_price_bars(ref.id, [bar])
            opens_by_instrument[ref.id] = bar.open
            close_by_instrument[ref.id] = bar.close
        summary.gated_illiquid = gated_illiquid
        if gated_illiquid:
            _log(f"turnover gate: skipped {gated_illiquid} widened-group names below floor {turnover_floor:,.0f}")

        # 4. Fill entry_next_open for entries first seen on the previous trading day (M3).
        prev = timeutils.previous_trading_day(trade_date)
        store.fill_pending_next_open(trade_date, prev, opens_by_instrument)

        # 5. Compute features for the latest bar. EMA periods feed the shared feature set;
        #    let the EMA Base Breakout strategy's YAML override them (e.g. long 200 -> 250).
        ema_cfg = next((c for c in strategy_configs if c.key == "ema_base_breakout"), None)
        if ema_cfg:
            ema_fast = int(ema_cfg.params.get("fast_ema_period", ema_fast))
            ema_mid = int(ema_cfg.params.get("mid_ema_period", ema_mid))
            ema_long = int(ema_cfg.params.get("long_ema_period", ema_long))
        features = []
        for ref in instruments:
            bars = store.get_trailing_prices(ref.id, trade_date)
            f = compute_features(
                ref.id, bars, rsi_period=rsi_period, volume_lookback=volume_lookback,
                ema_fast=ema_fast, ema_mid=ema_mid, ema_long=ema_long,
            )
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

            strat_cls = registry.get(cfg.key)
            if strat_cls is None:
                # Registered in YAML/DB but not implemented in code yet — skip, don't crash.
                summary.skipped_strategies.append(cfg.key)
                _log(f"strategy '{cfg.key}' is not implemented in code; skipping")
                continue

            run_id = store.start_scan_run(strat_id, trade_date)
            try:
                strategy = strat_cls(cfg.params)
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

        # news_positive: price + enrol any pending news_events. Isolated in its own try/except so a
        # news failure degrades to zero enrolments while the systematic scan still succeeds.
        if enable_news:
            try:
                summary.news = _enrol_news_events(store, trade_date, close_by_instrument, horizon_days)
                _log(f"news_positive: {summary.news}")
            except Exception as err:
                summary.news = {"error": str(err)}
                _log(f"news enrolment failed (non-fatal): {err}")

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
