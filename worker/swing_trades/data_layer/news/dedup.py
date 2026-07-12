"""Stage-A dedup (pre-LLM): collapse the SAME story arriving from several sources into one
cluster, so only one representative headline is sent to the LLM (saves quota) and all the source
ids can later attach to a single event.

Safety: items are grouped by (normalized company name, event date) FIRST, so two DIFFERENT
companies can never be merged; headline similarity (rapidfuzz token_set_ratio) only collapses
within that group. This is an optimization — the authoritative dedup is Stage B (by resolved
ISIN x catalyst_tag x window), so a Stage-A miss just costs one extra LLM item, never a wrong merge."""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from rapidfuzz import fuzz

from .models import RawNewsItem
from .resolver import normalize_name
from .tagger import classify_catalyst

FUZZY_HEADLINE_THRESHOLD = 90


def dedup_by_source_uid(items: Sequence[RawNewsItem]) -> list[RawNewsItem]:
    """Drop exact re-ingests of the same source (idempotency); keep first occurrence."""
    seen: set[str] = set()
    out: list[RawNewsItem] = []
    for it in items:
        if it.source_uid in seen:
            continue
        seen.add(it.source_uid)
        out.append(it)
    return out


def _union_find(n: int, edges: list[tuple[int, int]]) -> list[int]:
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return [find(i) for i in range(n)]


def cluster_near_duplicates(
    items: Sequence[RawNewsItem], threshold: int = FUZZY_HEADLINE_THRESHOLD
) -> list[list[RawNewsItem]]:
    """Group items into clusters of the same event. Each cluster is a list of RawNewsItem."""
    items = dedup_by_source_uid(items)
    groups: dict[tuple[str, object], list[RawNewsItem]] = defaultdict(list)
    for it in items:
        norm = normalize_name(it.company_name) if it.company_name else ""
        # Items with no company name (RSS headlines) can't be grouped by company — give each its own
        # singleton group so they never wrongly cluster together; Stage-B dedups them by resolved ISIN.
        key = (norm, it.event_date) if norm else ("\x00" + it.source_uid, it.event_date)
        groups[key].append(it)

    clusters: list[list[RawNewsItem]] = []
    for group in groups.values():
        if len(group) == 1:
            clusters.append(group)
            continue
        edges: list[tuple[int, int]] = []
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                hi = (group[i].headline or "").lower()
                hj = (group[j].headline or "").lower()
                if hi and hj and fuzz.token_set_ratio(hi, hj) >= threshold:
                    edges.append((i, j))
        roots = _union_find(len(group), edges)
        by_root: dict[int, list[RawNewsItem]] = defaultdict(list)
        for i, r in enumerate(roots):
            by_root[r].append(group[i])
        clusters.extend(by_root.values())
    return clusters


def representative(cluster: Sequence[RawNewsItem]) -> RawNewsItem:
    """Pick the item to classify + carry forward. Priority: an exchange filing (authoritative) over
    RSS, then a member whose category is DETERMINISTICALLY classifiable (so a co-clustered Tier-A
    filing never loses its tag to a longer non-Tier-A sibling), then the longest headline."""
    def rank(it: RawNewsItem):
        deterministic = classify_catalyst(it.category, it.subcategory).is_deterministic
        return (0 if it.source in ("BSE", "NSE") else 1, 0 if deterministic else 1, -len(it.headline or ""))

    return sorted(cluster, key=rank)[0]
