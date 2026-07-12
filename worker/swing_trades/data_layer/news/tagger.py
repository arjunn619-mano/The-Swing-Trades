"""Catalyst tagging: assign one of the 10 CATALYST_TAGS to a news item.

Three-tier ladder (first match wins, Tier A > B > C):
  A DETERMINISTIC — from the exchange category alone, no LLM (ORDER_WIN / BUYBACK / ACQUISITION).
  B SEMI_LLM      — the category proposes a tag; the LLM must confirm sentiment=positive.
  C LLM_ONLY      — neutral/free-text (Result, Company Update): the LLM decides event_type + sentiment.

Tier A is the durable backbone that enrols WITHOUT any LLM/API key. finalize_llm_catalyst() closes
Tiers B/C once the LLM has spoken. RESULTS_POSITIVE only ever comes from the LLM (a bare 'Result'
filing is neutral until judged positive)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import DETERMINISTIC, LLM_ONLY, SEMI_LLM


@dataclass(frozen=True)
class CatalystClassification:
    tag: Optional[str]   # a CATALYST_TAGS value, or None when the LLM must decide it
    decision: str        # DETERMINISTIC | SEMI_LLM | LLM_ONLY

    @property
    def is_deterministic(self) -> bool:
        return self.decision == DETERMINISTIC


def classify_catalyst(category: Optional[str], subcategory: Optional[str] = None) -> CatalystClassification:
    """Classify from the STRUCTURED exchange category/subcategory only (not the free-text headline —
    that goes to the LLM). Returns the tier + a tag (final for Tier A, a proposal for Tier B, None for C)."""
    t = " ".join(x for x in (category, subcategory) if x).lower().strip()
    if not t:
        return CatalystClassification(None, LLM_ONLY)

    # --- Tier A: deterministic, tag is final, no LLM ---
    if "buy back" in t or "buyback" in t:
        return CatalystClassification("BUYBACK", DETERMINISTIC)
    if ("order" in t or "contract" in t) and any(
        k in t for k in ("award", "receipt", "bagging", "receiving", "won", "secured", "bag")
    ):
        return CatalystClassification("ORDER_WIN", DETERMINISTIC)
    if "acquisition" in t or "acquire" in t:
        return CatalystClassification("ACQUISITION", DETERMINISTIC)

    # --- Tier B: category proposes, LLM confirms sentiment/direction ---
    if "rating" in t:
        return CatalystClassification("RATING_UPGRADE", SEMI_LLM)
    if any(k in t for k in ("fund raising", "fund-raising", "fund raise", "raising of fund", "qip",
                            "preferential issue", "preferential allotment")):
        return CatalystClassification("FUND_RAISING", SEMI_LLM)
    if any(k in t for k in ("new product", "product launch", "launch of")):
        return CatalystClassification("NEW_PRODUCT", SEMI_LLM)
    if any(k in t for k in ("capacity", "commercial production", "commencement of", "setting up",
                            "new plant", "expansion", "capex", "capital expenditure")):
        return CatalystClassification("EXPANSION_CAPEX", SEMI_LLM)
    if any(k in t for k in ("agreement", "joint venture", "mou", "memorandum of understanding",
                            "collaboration", "alliance", "partnership", "tie-up", "tie up")):
        return CatalystClassification("PARTNERSHIP", SEMI_LLM)

    # --- Tier C: neutral/free-text -> the LLM decides ---
    return CatalystClassification(None, LLM_ONLY)


# LLM event_type -> catalyst tag (used to close Tier B/C after the model has classified).
_LLM_EVENT_TO_TAG = {
    "order_win": "ORDER_WIN", "contract": "ORDER_WIN",
    "acquisition": "ACQUISITION", "mna": "ACQUISITION",
    "buyback": "BUYBACK",
    "partnership": "PARTNERSHIP",
    "product_launch": "NEW_PRODUCT", "new_product": "NEW_PRODUCT",
    "capacity_expansion": "EXPANSION_CAPEX", "expansion": "EXPANSION_CAPEX",
    "fundraise": "FUND_RAISING", "fund_raising": "FUND_RAISING",
    "rating_upgrade": "RATING_UPGRADE",
    "results": "RESULTS_POSITIVE", "results_positive": "RESULTS_POSITIVE", "earnings_positive": "RESULTS_POSITIVE",
    "regulatory_approval": "OTHER_POSITIVE",
}


def finalize_llm_catalyst(
    proposed_tag: Optional[str], llm_event_type: Optional[str], llm_sentiment: Optional[str]
) -> Optional[str]:
    """Close Tiers B/C with the LLM's verdict. Returns the final catalyst_tag, or None to DROP.
    Enrol ONLY when sentiment is positive. A SEMI_LLM proposal is confirmed by positive sentiment;
    an LLM_ONLY item is mapped from the model's event_type (RESULTS_POSITIVE needs event=results)."""
    if (llm_sentiment or "").strip().lower() != "positive":
        return None
    if proposed_tag:
        return proposed_tag
    return _LLM_EVENT_TO_TAG.get((llm_event_type or "").strip().lower(), "OTHER_POSITIVE")
