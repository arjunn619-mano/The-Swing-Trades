"""Catalyst tagging: deterministic Tier-A, semi/LLM tiers, and the post-LLM finalizer."""
from swing_trades.data_layer.news.models import CATALYST_TAGS, DETERMINISTIC, LLM_ONLY, SEMI_LLM
from swing_trades.data_layer.news.tagger import classify_catalyst, finalize_llm_catalyst


def test_tier_a_deterministic_order_win():
    c = classify_catalyst("Company Update", "Award of Order / Receipt of Order")
    assert c.tag == "ORDER_WIN" and c.decision == DETERMINISTIC and c.is_deterministic


def test_tier_a_deterministic_buyback():
    c = classify_catalyst("Buy back", "Buy Back of Securities")
    assert c.tag == "BUYBACK" and c.decision == DETERMINISTIC


def test_tier_a_deterministic_acquisition():
    c = classify_catalyst("Acquisition", None)
    assert c.tag == "ACQUISITION" and c.decision == DETERMINISTIC


def test_tier_b_semi_llm_proposals():
    assert classify_catalyst("Credit Rating").tag == "RATING_UPGRADE"
    assert classify_catalyst("Fund Raising", "QIP").tag == "FUND_RAISING"
    assert classify_catalyst("Agreement", "Joint Venture").tag == "PARTNERSHIP"
    assert classify_catalyst("Capacity Addition").tag == "EXPANSION_CAPEX"
    for cat in ("Credit Rating", "Fund Raising", "Agreement", "Capacity Addition"):
        assert classify_catalyst(cat).decision == SEMI_LLM


def test_tier_c_result_is_llm_only():
    c = classify_catalyst("Result", "Financial Results")
    assert c.tag is None and c.decision == LLM_ONLY


def test_blank_category_is_llm_only():
    assert classify_catalyst(None, None).decision == LLM_ONLY
    assert classify_catalyst("", "").decision == LLM_ONLY


def test_all_proposed_tags_are_valid_enum_values():
    for cat in ("Award of Order", "Buy back", "Acquisition", "Credit Rating",
                "Fund Raising", "New Product", "Capacity Addition", "Agreement"):
        tag = classify_catalyst(cat, "order").tag or classify_catalyst(cat).tag
        if tag is not None:
            assert tag in CATALYST_TAGS


def test_finalize_drops_non_positive():
    assert finalize_llm_catalyst("PARTNERSHIP", None, "negative") is None
    assert finalize_llm_catalyst(None, "results", "neutral") is None


def test_finalize_confirms_semi_llm_proposal():
    assert finalize_llm_catalyst("FUND_RAISING", None, "positive") == "FUND_RAISING"


def test_finalize_results_positive_only_when_positive_result():
    assert finalize_llm_catalyst(None, "results", "positive") == "RESULTS_POSITIVE"
    assert finalize_llm_catalyst(None, "results", "negative") is None  # bad result -> not enrolled


def test_finalize_llm_only_maps_or_falls_back_to_other():
    assert finalize_llm_catalyst(None, "order_win", "positive") == "ORDER_WIN"
    assert finalize_llm_catalyst(None, "market_share_gain", "positive") == "OTHER_POSITIVE"  # catch-all
