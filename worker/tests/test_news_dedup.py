"""Stage-A dedup: source_uid idempotency, near-duplicate collapse, no cross-company merge,
and representative selection (exchange filing preferred)."""
import datetime as dt

from swing_trades.data_layer.news.dedup import (
    cluster_near_duplicates,
    dedup_by_source_uid,
    representative,
)
from swing_trades.data_layer.news.models import RawNewsItem

D = dt.date(2026, 7, 12)


def mk(uid, company, headline, source="RSS_GNEWS", day=D):
    return RawNewsItem(
        source=source, source_uid=uid, company_name=company, headline=headline, event_date=day
    )


def test_dedup_by_source_uid_drops_exact_reingest():
    items = [mk("rss:1", "Reliance Industries", "X"), mk("rss:1", "Reliance Industries", "X")]
    assert len(dedup_by_source_uid(items)) == 1


def test_collapses_syndicated_repost():
    # Stage A collapses near-IDENTICAL syndicated copies (same wording, minor outlet suffix).
    # Genuinely-reworded headlines (different verbs) are left for Stage B to merge by ISIN+tag+window.
    items = [
        mk("g:1", "Tata Motors", "Tata Motors bags large order from Indian Railways"),
        mk("e:1", "Tata Motors Ltd", "Tata Motors bags large order from Indian Railways - ET Markets", source="RSS_ET"),
    ]
    clusters = cluster_near_duplicates(items)
    assert len(clusters) == 1  # same company + day + near-identical headline -> one event


def test_does_not_merge_different_companies():
    items = [
        mk("g:1", "Tata Motors", "wins order from Indian Railways"),
        mk("g:2", "Infosys", "wins order from Indian Railways"),  # identical headline, DIFFERENT company
    ]
    clusters = cluster_near_duplicates(items)
    assert len(clusters) == 2  # grouped by company first -> never merged


def test_keeps_distinct_events_same_company_same_day():
    items = [
        mk("g:1", "HDFC Bank", "HDFC Bank board approves buyback of shares"),
        mk("g:2", "HDFC Bank", "HDFC Bank opens 50 new rural branches"),
    ]
    assert len(cluster_near_duplicates(items)) == 2  # different stories -> not collapsed


def test_representative_prefers_exchange_filing():
    cluster = [
        mk("g:1", "Reliance", "short", source="RSS_GNEWS"),
        mk("b:1", "Reliance", "a much longer official filing headline", source="BSE"),
    ]
    assert representative(cluster).source == "BSE"


def test_representative_prefers_deterministic_tier_a_over_longer_headline():
    # Two co-clustered BSE filings: a Tier-A order-win (short headline) and a non-Tier-A "Company
    # Update" (longer headline). The deterministic member must win the rep slot so its tag survives.
    a = RawNewsItem(source="BSE", source_uid="b1", company_name="Tata Motors", headline="order",
                    event_date=D, category="Company Update", subcategory="Award of Order / Receipt of Order")
    b = RawNewsItem(source="BSE", source_uid="b2", company_name="Tata Motors",
                    headline="a much longer company update headline about the same matter",
                    event_date=D, category="Company Update", subcategory="General Announcement")
    assert representative([a, b]).source_uid == "b1"
