"""The nightly OPTION scan (Planning Pack 11, Phase O3), run after the equity scan.

trading-day check -> read the option catalog -> BULK-QUOTE every contract (volume/OI/LTP, cheap)
-> ENROLL any contract whose volume > 1L -> enrich just the ACTIVE underlyings with IV/Greeks
via the rate-limited option chain -> OBSERVE every active tracked contract -> EXPIRE (delete)
contracts past expiry. The full per-contract snapshot is handed to an optional sink (Phase O4
Parquet archive). Freshness-gated; always emits a health artifact.

The chain endpoint is rate-limited (1 req/3s, ~140k contracts would be ~900 calls -> 429s), so
volume/OI/LTP come from /marketfeed/quote (1000 ids/call, both stock & index options), and the
chain is used ONLY for the handful of qualifying underlyings to add IV/Greeks.

Everything external (store, Dhan client, sink, alert, sleep) is injected so the whole flow runs
offline in CI against a FakeOptionStore with a canned client."""
from __future__ import annotations

import datetime as _dt
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..data_layer.option_chain import parse_option_chain, underlying_ref
from ..data_layer.quotes import batch_option_refs, parse_option_quote_response
from ..tracker.option_lifecycle import decide_option_actions
from ..utils import timeutils
from .option_store import OptionScanStore

VOLUME_THRESHOLD = 100_000  # 1 lakh; a contract enrolls the day its volume clears this (Planning Pack 11)


class OptionScanError(RuntimeError):
    pass


@dataclass
class OptionScanSummary:
    trade_date: str
    status: str = "pending"  # success | failed | skipped_non_trading_day
    error: Optional[str] = None
    catalog: int = 0
    quote_batches: int = 0
    contracts_seen: int = 0     # contracts with a quote today
    qualifying: int = 0
    enrolled: int = 0
    observed: int = 0
    expired: int = 0
    chains_fetched: int = 0     # IV/Greeks enrichment calls that succeeded
    enriched: int = 0           # contracts that got IV/Greeks
    snapshot_rows: int = 0
    errors: int = 0
    sample_errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _emit_artifact(artifact_dir: Optional[str], summary: OptionScanSummary) -> None:
    if not artifact_dir:
        return
    d = Path(artifact_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"option_scan_{summary.trade_date}.json").write_text(
        json.dumps(summary.to_dict(), indent=2), encoding="utf-8"
    )


def _note_error(summary: OptionScanSummary, label: str, err: Exception) -> None:
    summary.errors += 1
    if len(summary.sample_errors) < 5:
        summary.sample_errors.append(f"{label}: {str(err)[:300]}")


def run_option_scan(
    trade_date: _dt.date,
    *,
    store: OptionScanStore,
    dhan_client,
    volume_threshold: int = VOLUME_THRESHOLD,
    quote_interval: float = 0.5,
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

        # Only non-expired contracts are quotable; index by security_id for mapping back.
        by_secid = {ref.security_id: ref for ref in catalog if ref.expiry_date >= trade_date}

        # 1. Bulk-quote everything for volume/OI/LTP (cheap; NOT the rate-limited chain).
        quotes: dict[str, dict] = {}
        for batch in batch_option_refs(list(by_secid.values())):
            try:
                quotes.update(parse_option_quote_response(dhan_client.quote(batch)))
                summary.quote_batches += 1
            except Exception as err:
                _note_error(summary, "quote batch", err)
                _log(f"quote batch failed: {err}")
            if quote_interval and sleep:
                sleep(quote_interval)

        today: dict[int, dict] = {}
        for secid, q in quotes.items():
            ref = by_secid.get(secid)
            if ref is None:
                continue
            today[ref.id] = {
                "ref": ref, "ltp": q["ltp"], "volume": q["volume"], "oi": q["oi"],
                "oi_change_pct": None, "iv": None, "delta": None, "theta": None,
                "gamma": None, "vega": None,
                "expiry_date": ref.expiry_date, "dte": (ref.expiry_date - trade_date).days,
            }
        summary.contracts_seen = len(today)
        if not today:
            raise OptionScanError("empty option snapshot — refusing to write (freshness gate)")

        # 2. Decide enroll/expire from quoted volume.
        qualifying = [cid for cid, d in today.items() if d["volume"] > volume_threshold]
        summary.qualifying = len(qualifying)
        tracked = store.get_tracked_options()
        tracked_ids = {t.contract_id for t in tracked}
        entry_ltp_by_cid = {t.contract_id: t.entry_ltp for t in tracked}
        actions = decide_option_actions(trade_date, qualifying, tracked)
        active_ids = (tracked_ids | set(actions.to_enroll)) - set(actions.to_expire)

        # 3. IV/Greeks enrichment via the option chain — ONLY for active underlyings (few calls).
        chain_groups: dict[tuple, list] = {}
        for cid in active_ids:
            d = today.get(cid)
            if d is None:
                continue
            scrip, seg = underlying_ref(d["ref"])
            if not scrip:
                continue
            chain_groups.setdefault((scrip, seg, d["ref"].expiry_date), []).append(cid)
        for (scrip, seg, exp), cids in chain_groups.items():
            label = f"{today[cids[0]]['ref'].underlying_symbol} {seg} {exp.isoformat()}"
            try:
                raw = dhan_client.option_chain(scrip, seg, exp.isoformat())
                snap = parse_option_chain(raw, exp.isoformat(), underlying_scrip=scrip, underlying_seg=seg)
                summary.chains_fetched += 1
                by_key = {(round(q.strike, 2), q.option_type): q for q in snap.quotes}
                for cid in cids:
                    ref = today[cid]["ref"]
                    q = by_key.get((round(ref.strike, 2), ref.option_type))
                    if q is None:
                        continue
                    today[cid].update(
                        iv=q.implied_volatility, delta=q.delta, theta=q.theta,
                        gamma=q.gamma, vega=q.vega, oi_change_pct=q.oi_change_pct,
                    )
                    summary.enriched += 1
            except Exception as err:  # index id / rate hiccup — tracking still works without Greeks
                _note_error(summary, label, err)
                _log(f"chain enrich failed {scrip}/{seg}/{exp}: {err}")
            if request_interval and sleep:
                sleep(request_interval)

        # 4. Enroll (entry premium from the quote; entry IV from the chain if we got it).
        for cid in actions.to_enroll:
            d = today[cid]
            store.enroll_option(cid, trade_date, d["ltp"], d["iv"], d["oi"], d["expiry_date"])
            entry_ltp_by_cid[cid] = d["ltp"]
        summary.enrolled = len(actions.to_enroll)

        # 5. Observe every active tracked contract.
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

        # 6. Expire (delete) contracts past expiry — full history is in the archive.
        if actions.to_expire:
            store.expire_options(actions.to_expire)
        summary.expired = len(actions.to_expire)

        # 7. Archive the full per-contract snapshot (every quoted contract).
        snapshot_rows = [
            {
                "trade_date": trade_date.isoformat(), "security_id": d["ref"].security_id,
                "underlying_symbol": d["ref"].underlying_symbol, "instrument_type": d["ref"].instrument_type,
                "exchange": d["ref"].exchange, "expiry_date": d["ref"].expiry_date.isoformat(),
                "strike": d["ref"].strike, "option_type": d["ref"].option_type, "lot_size": d["ref"].lot_size,
                "ltp": d["ltp"], "volume": d["volume"], "oi": d["oi"],
                "previous_oi": None, "oi_change_pct": d["oi_change_pct"], "iv": d["iv"],
                "delta": d["delta"], "theta": d["theta"], "gamma": d["gamma"], "vega": d["vega"],
                "underlying_last": None, "days_to_expiry": d["dte"],
            }
            for d in today.values()
        ]
        summary.snapshot_rows = len(snapshot_rows)
        if snapshot_sink is not None:
            snapshot_sink(snapshot_rows, trade_date)

        summary.status = "success"
        _log(f"options: {summary.quote_batches} quote batches, {summary.qualifying} qualifying, "
             f"+{summary.enrolled} enrolled, {summary.enriched} enriched, "
             f"{summary.observed} observed, -{summary.expired} expired, {summary.errors} errors")
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
