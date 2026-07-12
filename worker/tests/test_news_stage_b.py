"""Stage-B dedup: source idempotency, window merge, out-of-window new event, distinct tags,
and RSS-then-filing provenance upgrade (never re-prices)."""
import datetime as dt

from swing_trades.data_layer.models import UniverseInstrument
from swing_trades.data_layer.news.stage_b import (
    EXCHANGE_CONFIRMED,
    RSS_UNCONFIRMED,
    ResolvedCandidate,
    process_candidate,
)
from swing_trades.pipeline.store import FakeStore

RELIANCE = UniverseInstrument(
    isin="INE002A01018", security_id="2885", exchange_pref="NSE", exchange_segment="NSE_EQ",
    nse_symbol="RELIANCE", bse_scrip_code="500325", symbol_name="Reliance Industries",
    series="EQ", lot_size=1, asm_gsm_flag="N",
)
D = dt.date(2026, 7, 13)


def cand(uid, tag="ORDER_WIN", day=D, source="BSE", provenance=EXCHANGE_CONFIRMED, inst=RELIANCE):
    return ResolvedCandidate(isin=inst.isin, instrument=inst, catalyst_tag=tag, event_date=day,
                             source=source, source_uid=uid, headline="h", url=None, provenance=provenance)


def test_new_candidate_creates_event_and_instrument():
    s = FakeStore()
    assert process_candidate(s, cand("bse:1")) == "new_event"
    assert len(s.news_events) == 1
    assert any(r.isin == "INE002A01018" for r in s.instruments)  # expand-on-the-fly


def test_duplicate_source_uid_is_idempotent():
    s = FakeStore()
    process_candidate(s, cand("bse:1"))
    assert process_candidate(s, cand("bse:1")) == "duplicate_source"
    assert len(s.news_events) == 1


def test_same_isin_tag_within_window_merges():
    s = FakeStore()
    process_candidate(s, cand("bse:1", day=D))
    # NSE files the same order-win next day (within the 2-day window) -> merge, no new row
    assert process_candidate(s, cand("nse:1", day=D + dt.timedelta(days=1), source="NSE")) == "merged"
    assert len(s.news_events) == 1


def test_same_isin_tag_outside_window_is_new_event():
    s = FakeStore()
    process_candidate(s, cand("bse:1", day=D))
    later = cand("bse:2", day=D + dt.timedelta(days=10))  # a fresh order win 10 days later
    assert process_candidate(s, later) == "new_event"
    assert len(s.news_events) == 2


def test_different_tag_same_isin_is_new_event():
    s = FakeStore()
    process_candidate(s, cand("bse:1", tag="ORDER_WIN"))
    assert process_candidate(s, cand("bse:2", tag="BUYBACK")) == "new_event"
    assert len(s.news_events) == 2


def test_rss_then_filing_upgrades_provenance():
    s = FakeStore()
    # RSS reports it first (unconfirmed)
    process_candidate(s, cand("rss:1", source="RSS_GNEWS", provenance=RSS_UNCONFIRMED))
    ev_id = next(iter(s.news_events))
    assert s.news_events[ev_id]["provenance"] == RSS_UNCONFIRMED
    # the official BSE filing lands within the window -> merges + upgrades provenance
    assert process_candidate(s, cand("bse:1", day=D + dt.timedelta(days=1))) == "merged"
    assert s.news_events[ev_id]["provenance"] == EXCHANGE_CONFIRMED
    assert len(s.news_events) == 1  # never re-rows / re-prices
