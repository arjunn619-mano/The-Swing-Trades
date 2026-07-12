"""Daily news capture — runs 7 days/week (unlike the trading-day scan). Fetches corporate news,
resolves to Dhan instruments (reject-if-ambiguous), tags the catalyst, dedups, and writes the
news_events ledger. The EOD scan later prices + enrols pending events into the news_positive tracker
(entry = the next trading day's close). Deterministic Tier-A catalysts (order wins / buybacks /
acquisitions) need no LLM; Tier-B/C are handled by Gemini when GEMINI_API_KEY is set.

    python scripts/capture_news.py
"""
from __future__ import annotations

import functools
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_trades.config import load_settings, load_strategy_configs  # noqa: E402
from swing_trades.data_layer.instruments import INSTRUMENT_CSV_URL  # noqa: E402
from swing_trades.data_layer.news.capture import capture_news  # noqa: E402
from swing_trades.data_layer.news.http import requests_get  # noqa: E402
from swing_trades.data_layer.news.resolver import build_resolver_from_master  # noqa: E402
from swing_trades.data_layer.news.sources.base import HealthStatus  # noqa: E402
from swing_trades.data_layer.news.sources.bse import BseAdapter  # noqa: E402
from swing_trades.data_layer.news.sources.rss import RssAdapter  # noqa: E402
from swing_trades.db.connection import connection  # noqa: E402
from swing_trades.pipeline.store import PostgresStore  # noqa: E402
from swing_trades.utils import timeutils  # noqa: E402
from swing_trades.utils.alerts import send_telegram_alert  # noqa: E402
from swing_trades.utils.logging_setup import setup_logging  # noqa: E402


def _build_llm_classify(params):
    """Return a Gemini-backed llm_classify callable if GEMINI_API_KEY is set, else None (the
    deterministic Tier-A backbone still runs). Wired lazily so no key -> no dependency needed."""
    if not os.getenv("GEMINI_API_KEY"):
        return None
    from swing_trades.data_layer.news.llm_client import build_llm_classify  # lazy import

    return build_llm_classify(params.get("llm", {}) or {})


def main() -> None:
    import requests

    settings = load_settings()
    logger = setup_logging("logs")
    cfg = next((c for c in load_strategy_configs() if c.key == "news_positive"), None)
    if cfg is None or not cfg.active:
        print(json.dumps({"status": "news_positive inactive; skipping"}))
        return
    params = cfg.params or {}
    health_cfg = params.get("health", {}) or {}

    today = timeutils.today_ist()
    is_td = timeutils.is_trading_day(today)
    alert = functools.partial(
        send_telegram_alert,
        bot_token=settings.alert_telegram_bot_token,
        chat_id=settings.alert_telegram_chat_id,
    )

    logger.info("downloading instrument master for the news resolver...")
    master = requests.get(INSTRUMENT_CSV_URL, timeout=180).text
    resolver = build_resolver_from_master(master)

    llm_classify = _build_llm_classify(params)
    # BSE (deterministic backbone) always; the RSS narrative layer only when the LLM is available
    # (RSS items are all Tier-C — they need the LLM to extract the company + judge sentiment).
    adapters = [BseAdapter()]
    if llm_classify is not None:
        adapters.append(RssAdapter())

    with connection(settings.require_database_url()) as conn:
        result = capture_news(
            today, adapters=adapters, http_get=requests_get, resolver=resolver, store=PostgresStore(conn),
            is_trading_day=is_td, llm_classify=llm_classify,
            window_days=int(params.get("dedup_window_days", 2)),
            log_only_count=bool(health_cfg.get("log_only_count", True)),
            today=today,
        )

    # Alert on any non-OK source (hard failures always alarm; low-count deferred by log_only_count).
    for h in result.health:
        if h.status != HealthStatus.OK:
            alert(
                f"[The Swing Trades] news source {h.source} {h.status.value}: "
                f"{h.failed_check or '-'} — {h.detail}\nsample: {(h.sample or '')[:180]}"
            )
    logger.info(f"news capture complete: {result.to_dict()}")
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
