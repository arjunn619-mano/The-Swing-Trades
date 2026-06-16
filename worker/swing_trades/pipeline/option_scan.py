"""The nightly OPTION scan (Planning Pack 11, Phase O3), run after the equity scan.

trading-day check -> read the option catalog -> per (underlying, nearest expiries) fetch the
chain (throttled 1 req/3s) -> map each strike back to a catalog contract -> ENROLL any contract
whose volume > 1L -> OBSERVE every active tracked contract (premium return from add-date, OI,
IV, Greeks) -> EXPIRE (delete) contracts past expiry. The full per-strike snapshot is handed to
an optional sink (Phase O4 Parquet archive). Freshness-gated; always emits a health artifact.

Everything external (store, Dhan client, sink, alert, sleep) is injected so the whole flow runs
offline in CI against a FakeOptionStore with a canned chain client."""
from __future__ import annotations

import datetime as _dt
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..data_layer.option_chain import parse_option_chain, underlying_ref
from ..tracker.option_lifecycle import decide_option_actions
from ..utils import timeutils
from .option_store import OptionContractRef, OptionScanStore

VOLUME_THRESHOLD = 100_000  # 1 lakh; a contract enrolls the day its volume clears this (Planning Pack 11)


class OptionScanError(RuntimeError):
    pass


@dataclass
class OptionScanSummary:
    trade_date: str
    status: str = "pending"  # success | failed | skipped_non_trading_day
    error: Optional[str] = None
    catalog: int = 0
    chains_fetched: int = 0
    contracts_seen: int = 0
    qualifying: int = 0
    enrolled: int = 0
    observed: int = 0
    expired: int = 0
    snapshot_rows: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _group_catalog(catalog):
    """{(underlying_security_id, instrument_type, exchange): {expiry: {(strike, type): ref}}}."""
    groups: dict = {}
    for ref in catalog:
        key = (ref.underlying_security_id, ref.instrument_type, ref.exchange)
        by_expiry = groups.setdefault(key, {})
        strike_index = by_expiry.setdefault(ref.expiry_date, {})
        strike_index[(round(ref.strike, 2), ref.option_type)] = ref
    return groups


def _emit_artifact(artifact_dir: Optional[str], summary: OptionScanSummary) -> None:
    if not artifact_dir:
        return
    d = Path(artifact_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"option_scan_{summary.trade_date}.json").write_text(
        json.dumps(summary.to_dict(), indent=2), encoding="utf-8"
    )


def run_option_scan(
    trade_date: _dt.date,
    *,
    store: OptionScanStore,
    dhan_client,
    volume_threshold: int = VOLUME_THRESHOLD,
    max_expiries_per_underlying: int = 4,
    request_interval: float = 3.0,
    sleep: Callable[[float], None] = time.sleep,
    snapshot_sink: Optional[Callable[[list, _dt.date], None]] = None,
    artifact_dir: Optional[str] = None,
    alert: Optional[Callable[[str], bool]] = None,
    logger=None,
) -> OptionScanSummary:
    summary = OptionScanSummary(trade_date=trade_date.isoformat())

    def _log(msg: str) -> None:
        if logger:
            logger.info(msg)

    if not timeutils.is_trading_day(trade_date):
        summary.status = "skipped_non_trading_day"
        _log(f"{trade_date} is not a trading day; option scan skipped.")
        _emit_artifact(artifact_dir, summary)
        return summary

    try:
        catalog = store.get_option_contracts()
        summary.catalog = len(catalog)
        if not catalog:
            raise OptionScanError("no option contracts in catalog — run the catalog refresh first")

        groups = _group_catalog(catalog)
        tracked = store.get_tracked_options()
        tracked_ids = {t.contract_id for t in tracked}
        entry_ltp_by_cid = {t.contract_id: t.entry_ltp for t in tracked}

        today: dict[int, dict] = {}
        snapshot_rows: list[dict] = []

        # 1. Fetch the chain for each underlying's nearest active expiries (throttled).
        for (_usid, _instr, _exch), by_expiry in groups.items():
            rep = next(iter(next(iter(by_expiry.values())).values()))
            scrip, seg = underlying_ref(rep)
            if not scrip:
                continue  # underlying without a numeric security id — skip (can't fetch)
            expiries = sorted(e for e in by_expiry if e >= trade_date)[:max_expiries_per_underlying]
            for exp in expiries:
                strike_index = by_expiry[exp]
                raw = dhan_client.option_chain(scrip, seg, exp.isoformat())
                snap = parse_option_chain(raw, exp.isoformat(), underlying_scrip=scrip, underlying_seg=seg)
                summary.chains_fetched += 1
                for q in snap.quotes:
                    ref: Optional[OptionContractRef] = strike_index.get((round(q.strike, 2), q.option_type))
                    if ref is None:
                        continue
                    dte = (ref.expiry_date - trade_date).days
                    snapshot_rows.append({
                        "trade_date": trade_date.isoformat(),
                        "security_id": ref.security_id,
                        "underlying_symbol": ref.underlying_symbol,
                        "instrument_type": ref.instrument_type,
                        "exchange": ref.exchange,
                        "expiry_date": ref.expiry_date.isoformat(),
                        "strike": ref.strike,
                        "option_type": ref.option_type,
                        "lot_size": ref.lot_size,
                        "ltp": q.last_price, "volume": q.volume, "oi": q.oi,
                        "previous_oi": q.previous_oi, "oi_change_pct": q.oi_change_pct,
                        "iv": q.implied_volatility, "delta": q.delta, "theta": q.theta,
                        "gamma": q.gamma, "vega": q.vega,
                        "underlying_last": snap.underlying_last_price, "days_to_expiry": dte,
                    })
                    today[ref.id] = {
                        "ltp": q.last_price, "volume": q.volume, "oi": q.oi,
                        "oi_change_pct": q.oi_change_pct, "iv": q.implied_volatility,
                        "delta": q.delta, "theta": q.theta, "gamma": q.gamma, "vega": q.vega,
                        "expiry_date": ref.expiry_date, "dte": dte,
                    }
                if request_interval and sleep:
                    sleep(request_interval)

        # 2. Freshness gate: never enroll/observe/expire off an empty snapshot.
        summary.contracts_seen = len(today)
        if not today:
            raise OptionScanError("empty option snapshot — refusing to write (freshness gate)")

        # 3. Enroll contracts whose volume cleared the threshold today.
        qualifying = [cid for cid, d in today.items() if d["volume"] > volume_threshold]
        summary.qualifying = len(qualifying)
        actions = decide_option_actions(trade_date, qualifying, tracked)
        for cid in actions.to_enroll:
            d = today[cid]
            store.enroll_option(cid, trade_date, d["ltp"], d["iv"], d["oi"], d["expiry_date"])
            entry_ltp_by_cid[cid] = d["ltp"]
        summary.enrolled = len(actions.to_enroll)

        # 4. Observe every active tracked contract that traded today (incl. those just enrolled).
        active_ids = (tracked_ids | set(actions.to_enroll)) - set(actions.to_expire)
        observed = 0
        for cid in active_ids:
            d = today.get(cid)
            if d is None:
                continue
            entry = entry_ltp_by_cid.get(cid)
            rve = (d["ltp"] / entry - 1.0) if entry else None
            store.record_option_observation(
                cid, trade_date, ltp=d["ltp"], volume=d["volume"], oi=d["oi"],
                oi_change_pct=d["oi_change_pct"], iv=d["iv"], delta=d["delta"], theta=d["theta"],
                gamma=d["gamma"], vega=d["vega"], days_to_expiry=d["dte"], return_vs_entry=rve,
            )
            observed += 1
        summary.observed = observed

        # 5. Expire (delete) contracts past expiry — full history is in the archive.
        if actions.to_expire:
            store.expire_options(actions.to_expire)
        summary.expired = len(actions.to_expire)
        summary.snapshot_rows = len(snapshot_rows)

        # 6. Hand the full per-strike snapshot to the archive sink (Phase O4), if wired.
        if snapshot_sink is not None:
            snapshot_sink(snapshot_rows, trade_date)

        summary.status = "success"
        _log(f"options: {summary.chains_fetched} chains, +{summary.enrolled} enrolled, "
             f"{summary.observed} observed, -{summary.expired} expired")
        _emit_artifact(artifact_dir, summary)
        return summary

    except Exception as err:  # loud failure, always an artifact + alert
        summary.status = "failed"
        summary.error = str(err)
        _emit_artifact(artifact_dir, summary)
        if alert:
            alert(f"[The Swing Trades] OPTION scan FAILED for {trade_date}: {err}")
        if logger:
            logger.exception("option scan failed")
        raise
