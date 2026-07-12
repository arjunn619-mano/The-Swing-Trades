"""Stage-B dedup (authoritative, post-resolution): collapse the same corporate event — arriving
via BSE filing, NSE filing, and/or several RSS reposts — onto ONE news_events ledger row keyed by
(resolved ISIN, catalyst_tag, day-window). Idempotent on source_uid.

An exchange filing is authoritative; RSS enrols on its own (the earliness edge) tagged
rss_unconfirmed and is upgraded to exchange_confirmed when the filing later lands — WITHOUT
re-pricing (Rule 3: the tracker entry's entry_close was fixed on first-seen day). Whether a new
event becomes a NEW tracker entry or an appearance_count++ is decided at ENROLMENT (in the EOD
scan), not here."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional

from ..models import UniverseInstrument

NEWS_DEDUP_WINDOW_DAYS = 2  # calendar days either side of the event's first-seen date

EXCHANGE_CONFIRMED = "exchange_confirmed"
RSS_UNCONFIRMED = "rss_unconfirmed"


@dataclass(frozen=True)
class ResolvedCandidate:
    isin: str
    instrument: UniverseInstrument
    catalyst_tag: str
    event_date: _dt.date
    source: str                      # BSE | NSE | RSS_GNEWS | ...
    source_uid: str
    headline: Optional[str] = None
    url: Optional[str] = None
    provenance: str = EXCHANGE_CONFIRMED   # exchange feeds confirmed; RSS -> RSS_UNCONFIRMED


def process_candidate(store, c: ResolvedCandidate, window_days: int = NEWS_DEDUP_WINDOW_DAYS) -> str:
    """Idempotent source dedup + window-lookup upsert. Returns 'duplicate_source' | 'merged' | 'new_event'."""
    if store.news_source_exists(c.source_uid):
        return "duplicate_source"  # exact re-ingest of a source already attached to some event

    instrument_id = store.ensure_instrument(c.instrument)  # expand-on-the-fly if not yet in the DB
    lo = c.event_date - _dt.timedelta(days=window_days)
    hi = c.event_date + _dt.timedelta(days=window_days)

    open_ev = store.find_open_news_event(c.isin, c.catalyst_tag, lo, hi)
    if open_ev is not None:
        store.attach_news_source(open_ev.id, c.source_uid, c.source, c.url)
        # A filing confirming an earlier RSS-only event upgrades provenance (never re-prices).
        if c.provenance == EXCHANGE_CONFIRMED and open_ev.provenance != EXCHANGE_CONFIRMED:
            store.set_news_event_provenance(open_ev.id, EXCHANGE_CONFIRMED)
        return "merged"

    eid = store.create_news_event(
        c.isin, instrument_id, c.catalyst_tag, c.event_date,
        c.event_date + _dt.timedelta(days=window_days), c.provenance, c.headline,
    )
    store.attach_news_source(eid, c.source_uid, c.source, c.url)
    return "new_event"
