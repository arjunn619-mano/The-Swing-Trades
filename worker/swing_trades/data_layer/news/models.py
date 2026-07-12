"""Shared dataclasses + the frozen catalyst taxonomy for the news pipeline.

Flow: adapters emit RawNewsItem -> (deterministic tagger OR LLM) assign a catalyst -> resolver
maps to a Dhan instrument -> dedup -> NewsCandidate ready for enrolment."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional

# The single source of truth for the 10-value catalyst enum (mirrors the DB CHECK constraint in
# schema.sql). OTHER_POSITIVE is the mandatory catch-all so a positive item is never dropped for
# lack of a specific box; it is never NULL on a news_positive row.
CATALYST_TAGS: frozenset[str] = frozenset(
    {
        "RESULTS_POSITIVE",
        "ORDER_WIN",
        "ACQUISITION",
        "BUYBACK",
        "PARTNERSHIP",
        "NEW_PRODUCT",
        "EXPANSION_CAPEX",
        "RATING_UPGRADE",
        "FUND_RAISING",
        "OTHER_POSITIVE",
    }
)

# Decision tiers: how a catalyst_tag was assigned.
#   DETERMINISTIC — from the exchange category alone, no LLM (Tier A).
#   SEMI_LLM      — the category proposes the tag; the LLM must confirm sentiment/direction (Tier B).
#   LLM_ONLY      — the category is neutral/free-text; the LLM decides event_type + sentiment (Tier C).
DETERMINISTIC = "DETERMINISTIC"
SEMI_LLM = "SEMI_LLM"
LLM_ONLY = "LLM_ONLY"


@dataclass(frozen=True)
class RawNewsItem:
    """One fetched news/announcement item, before tagging + resolution."""

    source: str                         # BSE | NSE | RSS_GNEWS | RSS_ET | RSS_LIVEMINT | RSS_PRWIRE | RSS_MC
    source_uid: str                     # deterministic dedup id, e.g. 'bse:'+NEWSID
    company_name: str                   # long/legal name as reported
    headline: str                       # subject / headline free text
    event_date: _dt.date                # announcement / publish date (IST)
    category: Optional[str] = None      # BSE CATEGORYNAME / NSE high-level subject
    subcategory: Optional[str] = None   # BSE SUBCATNAME
    isin: Optional[str] = None          # NSE gives sm_isin; BSE feed does not
    bse_scrip_code: Optional[str] = None
    url: Optional[str] = None           # NSURL / PDF / attachment / article link
