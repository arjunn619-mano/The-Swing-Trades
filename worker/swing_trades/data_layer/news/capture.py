"""Daily news capture orchestration (runs 7 days/week): fetch every source -> Stage-A cluster
near-duplicates -> tag the catalyst -> resolve to a Dhan instrument (reject-if-ambiguous) ->
Stage-B upsert into the news_events ledger. Pricing/enrolment happens later in the EOD scan.

The LLM is OPTIONAL: with no llm_classify injected (no API key yet), Tier-A deterministic catalysts
(ORDER_WIN / BUYBACK / ACQUISITION from exchange filings) still enrol — the durable backbone —
while Tier-B/C (sentiment-ambiguous / RSS free-text) items are DEFERRED, never guessed."""
from __future__ import annotations

import datetime as _dt
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from .dedup import cluster_near_duplicates, representative
from .resolver import InstrumentResolver
from .stage_b import EXCHANGE_CONFIRMED, RSS_UNCONFIRMED, ResolvedCandidate, process_candidate
from .tagger import classify_catalyst, finalize_llm_catalyst

_EXCHANGE_SOURCES = ("BSE", "NSE")


@dataclass
class CaptureResult:
    trade_date: str
    health: list = field(default_factory=list)          # list[SourceHealth]
    fetched: int = 0
    clusters: int = 0
    tier_a: int = 0            # deterministically tagged (no LLM)
    llm_classified: int = 0    # tagged via the LLM
    llm_deferred: int = 0      # Tier B/C skipped because no LLM was available
    resolved: int = 0
    rejected: int = 0          # reject-if-ambiguous
    new_events: int = 0
    merged: int = 0
    duplicate_sources: int = 0
    dropped_non_positive: int = 0   # LLM said not positive

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["health"] = [h.to_dict() for h in self.health]
        return d


def _provenance(source: str) -> str:
    return EXCHANGE_CONFIRMED if source in _EXCHANGE_SOURCES else RSS_UNCONFIRMED


def capture_news(
    trade_date: _dt.date,
    *,
    adapters: Sequence,
    http_get: Callable,
    resolver: InstrumentResolver,
    store,
    is_trading_day: bool = True,
    llm_classify: Optional[Callable] = None,   # (list[RawNewsItem]) -> list[(event_type, sentiment)]
    window_days: int = 2,
    log_only_count: bool = False,
    today: Optional[_dt.date] = None,
) -> CaptureResult:
    res = CaptureResult(trade_date=trade_date.isoformat())

    # 1. fetch all sources (each returns items + a health verdict; never raises)
    items = []
    for ad in adapters:
        got, health = ad.collect(
            trade_date, http_get=http_get, is_trading_day=is_trading_day,
            log_only_count=log_only_count, today=today,
        )
        res.health.append(health)
        items.extend(got)
    res.fetched = len(items)

    # 2. Stage-A: collapse near-duplicate reposts into clusters (one representative each)
    clusters = cluster_near_duplicates(items)
    res.clusters = len(clusters)

    # 3. classify + resolve + Stage-B, per cluster
    for cluster in clusters:
        rep = representative(cluster)
        cls = classify_catalyst(rep.category, rep.subcategory)

        if cls.is_deterministic:
            tag = cls.tag
            res.tier_a += 1
        else:
            if llm_classify is None:
                res.llm_deferred += 1
                continue  # no LLM yet — Tier B/C waits (never guess a tag)
            event_type, sentiment = llm_classify([rep])[0]
            tag = finalize_llm_catalyst(cls.tag, event_type, sentiment)
            if tag is None:
                res.dropped_non_positive += 1
                continue
            res.llm_classified += 1

        r = resolver.resolve(isin=rep.isin, bse_scrip=rep.bse_scrip_code, name=rep.company_name)
        if not r.ok:
            res.rejected += 1
            continue
        res.resolved += 1

        # process every source in the cluster so all source_uids attach to one event
        for member in cluster:
            c = ResolvedCandidate(
                isin=r.instrument.isin, instrument=r.instrument, catalyst_tag=tag,
                event_date=member.event_date, source=member.source, source_uid=member.source_uid,
                headline=member.headline, url=member.url, provenance=_provenance(member.source),
            )
            decision = process_candidate(store, c, window_days=window_days)
            if decision == "new_event":
                res.new_events += 1
            elif decision == "merged":
                res.merged += 1
            else:
                res.duplicate_sources += 1

    return res
