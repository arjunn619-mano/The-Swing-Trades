"""Layer-2 LLM classifier for the sentiment-ambiguous (Tier-B/C) news the deterministic tagger
can't judge. Primary: Google Gemini Flash-Lite FREE tier (one batched JSON-mode call/night ≈ 1/1000
of the daily quota). Break-glass: Anthropic Haiku 4.5 (~Rs.150/mo), flipped only when Gemini's daily
quota is exhausted — a one-config swap, never sticky across runs.

The model emits ONLY {id, event_type, sentiment} — NEVER a ticker/symbol (those hallucinate; the
resolver maps deterministically). The orchestration (batching, id-alignment, retry/backoff, fallback
trip-wire) is pure + unit-tested; the two HTTP calls are thin and validated live once a key is set."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

# The event_type vocabulary the model must choose from (mapped to catalyst tags in tagger.py).
EVENT_TYPES = (
    "order_win", "acquisition", "buyback", "partnership", "product_launch",
    "capacity_expansion", "fundraise", "rating_upgrade", "results", "regulatory_approval", "other",
)
SENTIMENTS = ("positive", "neutral", "negative")


class QuotaExhausted(Exception):
    """A model call hit its per-DAY quota (RPD) — retrying today is futile, flip to the fallback."""


@dataclass(frozen=True)
class LlmConfig:
    model_primary: str = "gemini-flash-lite-latest"
    model_fallback: str = "claude-haiku-4-5"
    batch_size: int = 50
    min_call_spacing_s: float = 5.0
    max_retries: int = 3

    @classmethod
    def from_dict(cls, d: dict) -> "LlmConfig":
        d = d or {}
        return cls(
            model_primary=d.get("model_primary", cls.model_primary),
            model_fallback=d.get("model_fallback", cls.model_fallback),
            batch_size=int(d.get("batch_size", cls.batch_size)),
            min_call_spacing_s=float(d.get("min_call_spacing_s", cls.min_call_spacing_s)),
            max_retries=int(d.get("max_retries", cls.max_retries)),
        )


def _batches(items, n):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _call_with_retries(call, batch, config: LlmConfig, sleep):
    delays = (2, 8, 30)
    last: Optional[Exception] = None
    for attempt in range(config.max_retries):
        try:
            return call(batch)
        except QuotaExhausted:
            raise
        except Exception as e:  # transient (network/5xx/rate-limit) — backoff + retry
            last = e
            if attempt < config.max_retries - 1:
                sleep(delays[min(attempt, len(delays) - 1)])
    raise last or RuntimeError("model call failed")


def classify_batches(
    items: Sequence,
    *,
    primary_call: Callable,
    fallback_call: Optional[Callable] = None,
    config: LlmConfig,
    sleep: Callable = time.sleep,
    on_fallback: Optional[Callable[[int], None]] = None,
) -> list:
    """Run items through the model in batches; return a list aligned to `items` of
    (event_type, sentiment). primary_call(batch) -> list aligned to the batch. On QuotaExhausted,
    flip to fallback_call for the REST of the run (once), firing on_fallback(remaining)."""
    out: list = []
    using_fallback = False
    first = True
    for batch in _batches(list(items), config.batch_size):
        if not first and config.min_call_spacing_s:
            sleep(config.min_call_spacing_s)
        first = False
        verdicts = None
        try:
            verdicts = _call_with_retries(fallback_call if using_fallback else primary_call, batch, config, sleep)
        except QuotaExhausted:
            if fallback_call is not None and not using_fallback:
                using_fallback = True
                if on_fallback:
                    on_fallback(len(items) - len(out))
                try:
                    verdicts = _call_with_retries(fallback_call, batch, config, sleep)
                except Exception:
                    verdicts = None  # even the fallback flip-batch failed -> degrade, NEVER propagate
        except Exception:
            verdicts = None
        if verdicts is None:
            verdicts = [("other", "neutral")] * len(batch)  # degrade -> neutral (dropped, not enrolled)
        elif len(verdicts) != len(batch):  # never let a short/long reply desync the alignment
            verdicts = (list(verdicts) + [("other", "neutral")] * len(batch))[: len(batch)]
        out.extend(verdicts)
    return out


# ---- prompt + response parsing (shared by both providers) ----

_INSTRUCTION = (
    "You classify Indian-listed-company corporate news. For EACH item return its event_type (one of: "
    + ", ".join(EVENT_TYPES)
    + ") and sentiment (positive, neutral, negative) for the SHARE PRICE. Positive = a genuine growth/"
    "earnings/order/expansion catalyst; a weak or declining result is negative; routine/procedural is "
    "neutral. Return ONLY a JSON array of objects {\"id\": <int>, \"event_type\": <string>, "
    "\"sentiment\": <string>}. NEVER output a stock ticker, symbol, ISIN or exchange code."
)


def build_prompt(batch) -> str:
    payload = [{"id": i, "text": f"{it.company_name} — {it.headline}"} for i, it in enumerate(batch)]
    return _INSTRUCTION + "\n\nITEMS:\n" + json.dumps(payload, ensure_ascii=False)


def parse_verdicts(text: str, n: int) -> list:
    """Parse the model's JSON array back into a list aligned to the batch by id. Missing/garbled
    entries default to ('other','neutral') so nothing desyncs or is wrongly enrolled."""
    out = [("other", "neutral")] * n
    try:
        arr = json.loads(text)
    except (ValueError, TypeError):
        return out
    if not isinstance(arr, list):
        return out
    for obj in arr:
        if not isinstance(obj, dict):
            continue
        try:
            i = int(obj.get("id"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < n:
            ev = str(obj.get("event_type", "other")).strip().lower()
            se = str(obj.get("sentiment", "neutral")).strip().lower()
            out[i] = (ev if ev in EVENT_TYPES else "other", se if se in SENTIMENTS else "neutral")
    return out


# ---- real provider calls (thin; validated live once a key is present) ----

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _gemini_call_factory(model: str, api_key: str) -> Callable:
    def call(batch):
        import requests

        body = {
            "contents": [{"parts": [{"text": build_prompt(batch)}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        r = requests.post(_GEMINI_URL.format(model=model), params={"key": api_key}, json=body, timeout=60)
        if r.status_code == 429:
            # per-day quota exhaustion -> flip to fallback; per-minute -> transient (retry)
            if "PerDay" in r.text or "per day" in r.text.lower():
                raise QuotaExhausted(r.text[:200])
            raise RuntimeError(f"gemini 429: {r.text[:200]}")
        r.raise_for_status()
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return parse_verdicts(text, len(batch))

    return call


def _haiku_call_factory(model: str, api_key: str) -> Callable:
    def call(batch):
        import requests

        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 4096,
                  "messages": [{"role": "user", "content": build_prompt(batch) + "\n\nReturn only the JSON array."}]},
            timeout=60,
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []))
        return parse_verdicts(text, len(batch))

    return call


def build_llm_classify(llm_cfg: dict) -> Optional[Callable]:
    """Wire the real Gemini (primary) + Haiku (fallback) calls into a classify(items) callable, or
    return None if no GEMINI_API_KEY. Fallback is used only if the Gemini daily quota is exhausted."""
    import os

    gkey = os.getenv("GEMINI_API_KEY")
    if not gkey:
        return None
    config = LlmConfig.from_dict(llm_cfg)
    primary = _gemini_call_factory(config.model_primary, gkey)
    akey = os.getenv("ANTHROPIC_API_KEY")
    fallback = _haiku_call_factory(config.model_fallback, akey) if akey else None

    def classify(items):
        return classify_batches(items, primary_call=primary, fallback_call=fallback, config=config)

    return classify
