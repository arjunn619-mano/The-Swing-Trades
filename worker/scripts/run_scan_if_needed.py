"""Catchup-aware daily scan (used by the cron). Runs today's scan unless it's already done
or today isn't a trading day. Notices and reports missed trading days. Idempotent.

    python scripts/run_scan_if_needed.py
"""
from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_trades.config import load_settings, load_strategy_configs  # noqa: E402
from swing_trades.config.strategies_loader import load_tracking_horizon_days  # noqa: E402
from swing_trades.data_layer.dhan_auth import generate_access_token  # noqa: E402
from swing_trades.data_layer.dhan_client import DhanDataClient  # noqa: E402
from swing_trades.db.connection import connection  # noqa: E402
from swing_trades.pipeline.catchup import eod_ready, should_run_today, trading_gap  # noqa: E402
from swing_trades.pipeline.scan import run_scan  # noqa: E402
from swing_trades.pipeline.store import PostgresStore  # noqa: E402
from swing_trades.utils import timeutils  # noqa: E402
from swing_trades.utils.alerts import send_telegram_alert  # noqa: E402
from swing_trades.utils.logging_setup import setup_logging  # noqa: E402


def main() -> None:
    settings = load_settings()
    logger = setup_logging("logs")
    now = timeutils.now_ist()
    trade_date = now.date()

    if not timeutils.is_trading_day(trade_date):
        logger.info(f"{trade_date} is not a trading day; nothing to do.")
        print(json.dumps({"trade_date": trade_date.isoformat(), "status": "skipped_non_trading_day"}))
        return

    if not eod_ready(now):
        # Before the EOD-settle time, a 'today' scan would store stale pre-/intraday prices and
        # mark the day complete (blocking the real post-close scan). Skip; the 5 PM cron handles it.
        logger.info(f"{trade_date}: EOD not settled (now {now:%H:%M} IST, need >= 16:00); skipping.")
        print(json.dumps({"trade_date": trade_date.isoformat(), "status": "before_market_close"}))
        return

    configs = load_strategy_configs()
    alert = functools.partial(
        send_telegram_alert,
        bot_token=settings.alert_telegram_bot_token,
        chat_id=settings.alert_telegram_chat_id,
    )

    with connection(settings.require_database_url()) as conn:
        store = PostgresStore(conn)
        active = [c for c in configs if c.active]
        done = all(store.scan_run_done(store.get_strategy_id(c.key), trade_date) for c in active)
        if not should_run_today(trade_date, done):
            logger.info(f"scan for {trade_date} already complete; skipping.")
            print(json.dumps({"trade_date": trade_date.isoformat(), "status": "already_complete"}))
            return

        gap = trading_gap(store.last_successful_scan_date(), trade_date)
        if gap > 0:
            msg = f"[The Swing Trades] {gap} missed trading day(s) before {trade_date}; run scripts/backfill.py."
            logger.warning(msg)
            alert(msg)

        token = generate_access_token(*settings.require_dhan())
        client = DhanDataClient(token.access_token, settings.dhan_client_id)
        summary = run_scan(
            trade_date,
            store=store,
            dhan_client=client,
            strategy_configs=configs,
            horizon_days=load_tracking_horizon_days(),
            artifact_dir="artifacts",
            alert=lambda m: bool(alert(m)),
            logger=logger,
        )
    print(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":
    main()
