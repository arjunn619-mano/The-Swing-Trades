"""LLM client orchestration: id-aligned parsing, batching, pacing, the Haiku fallback trip-wire,
and the never-emit-a-ticker prompt. No live API — the two HTTP calls are injected as fakes."""
import datetime as dt

from swing_trades.data_layer.news.llm_client import (
    LlmConfig,
    QuotaExhausted,
    build_prompt,
    classify_batches,
    parse_verdicts,
)
from swing_trades.data_layer.news.models import RawNewsItem

CFG = LlmConfig(batch_size=2, min_call_spacing_s=0)


def item(name, headline):
    return RawNewsItem(source="RSS_GNEWS", source_uid="x", company_name=name, headline=headline,
                       event_date=dt.date(2026, 7, 13))


def test_parse_verdicts_aligns_by_id_regardless_of_order():
    text = '[{"id":1,"event_type":"results","sentiment":"positive"},{"id":0,"event_type":"order_win","sentiment":"positive"}]'
    v = parse_verdicts(text, 2)
    assert v[0] == ("order_win", "positive") and v[1] == ("results", "positive")


def test_parse_verdicts_defaults_on_garbage_and_unknown_values():
    assert parse_verdicts("not json at all", 2) == [("other", "neutral"), ("other", "neutral")]
    assert parse_verdicts('[{"id":0,"event_type":"weird","sentiment":"meh"}]', 1) == [("other", "neutral")]


def test_classify_batches_happy_path():
    items = [item("A", "x"), item("B", "y")]
    out = classify_batches(items, primary_call=lambda b: [("results", "positive")] * len(b),
                           config=CFG, sleep=lambda s: None)
    assert out == [("results", "positive"), ("results", "positive")]


def test_classify_batches_splits_by_batch_size():
    items = [item(str(i), "h") for i in range(5)]  # batch_size 2 -> [2,2,1]
    seen = []
    classify_batches(items, primary_call=lambda b: (seen.append(len(b)) or [("other", "neutral")] * len(b)),
                     config=CFG, sleep=lambda s: None)
    assert seen == [2, 2, 1]


def test_fallback_fires_on_quota_exhausted():
    fired = []

    def primary(_b):
        raise QuotaExhausted("PerDay limit")

    out = classify_batches([item("A", "x")], primary_call=primary,
                           fallback_call=lambda b: [("order_win", "positive")] * len(b),
                           config=CFG, sleep=lambda s: None, on_fallback=lambda n: fired.append(n))
    assert out == [("order_win", "positive")] and fired == [1]


def test_quota_with_no_fallback_defaults_neutral():
    def primary(_b):
        raise QuotaExhausted("PerDay")

    out = classify_batches([item("A", "x")], primary_call=primary, fallback_call=None,
                           config=CFG, sleep=lambda s: None)
    assert out == [("other", "neutral")]  # nothing enrolled (neutral -> dropped downstream)


def test_short_reply_is_padded_to_preserve_alignment():
    items = [item("A", "x"), item("B", "y")]
    out = classify_batches(items, primary_call=lambda b: [("results", "positive")],  # only 1 for a 2-item batch
                           config=CFG, sleep=lambda s: None)
    assert len(out) == 2 and out[1] == ("other", "neutral")


def test_transient_error_retries_then_defaults():
    calls = {"n": 0}

    def flaky(_b):
        calls["n"] += 1
        raise ConnectionError("blip")

    out = classify_batches([item("A", "x")], primary_call=flaky, config=CFG, sleep=lambda s: None)
    assert calls["n"] == CFG.max_retries and out == [("other", "neutral")]


def test_prompt_forbids_tickers_and_includes_the_company():
    p = build_prompt([item("Reliance Industries", "bags large order")])
    assert "NEVER output a stock ticker" in p and "Reliance Industries" in p
