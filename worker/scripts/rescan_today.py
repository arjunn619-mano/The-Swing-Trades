"""One-off repair: reset TODAY's scan data and re-run with the now-settled EOD quote.

Use when today was scanned too early (pre-close) and stored stale prices, leaving the day
marked complete so the normal runner skips it. Refuses to run before 16:00 IST (so it can't
re-pull stale data) and only ever touches today's rows. Requires DATABASE_URL + Dhan secrets.

    python scripts/rescan_today.py
"""
from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_trades.config import load_settings, load_strategy_configs, load_turnover_floor  # noqa: E402
from swing_trades.config.strategies_loader import load_tracking_horizon_days  # noqa: E402
from swing_trades.data_layer.dhan_auth import generate_access_token  # noqa: E402
from swing_trades.data_layer.dhan_client import DhanDataClient  # noqa: E402
from swing_trades.db.connection import connection  # noqa: E402
from swing_trades.pipeline.catchup import eod_ready  # noqa: E402
from swing_trades.pipeline.scan import run_scan  # noqa: E402
from swing_trades.pipeline.store import PostgresStore  # noqa: E402
from swing_trades.utils import timeutils  # noqa: E402
from swing_trades.utils.alerts import send_telegram_alert  # noqa: E402
from swing_trades.utils.logging_setup import setup_logging  # noqa: E402


def reset_date(conn, d) -> None:
    """Delete everything tied to trade date `d` so the re-scan starts clean. Scoped to `d` only;
    entries first-seen on `d` are removed (their entry price was set from the stale scan)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM scan_runs WHERE trade_date = %s", (d,))             # cascades scan_signals
        cur.execute("DELETE FROM tracker_observations WHERE trade_date = %s", (d,))
        cur.execute("DELETE FROM tracker_entries WHERE first_seen_date = %s", (d,))  # cascades their obs
        cur.execute("DELETE FROM price_history WHERE trade_date = %s", (d,))
    conn.commit()


def main() -> None:
    settings = load_settings()
    logger = setup_logging("logs")
    now = timeutils.now_ist()
    trade_date = now.date()

    if not timeutils.is_trading_day(trade_date):
        print(json.dumps({"trade_date": trade_date.isoformat(), "status": "skipped_non_trading_day"}))
        return
    if not eod_ready(now):
        logger.warning(f"refusing: before 16:00 IST settle (now {now:%H:%M}) — would re-pull stale data.")
        print(json.dumps({"trade_date": trade_date.isoformat(), "status": "refused_before_market_close"}))
        return

    token = generate_access_token(*settings.require_dhan())
    client = DhanDataClient(token.access_token, settings.dhan_client_id)
    alert = functools.partial(
        send_telegram_alert,
        bot_token=settings.alert_telegram_bot_token,
        chat_id=settings.alert_telegram_chat_id,
    )

    with connection(settings.require_database_url()) as conn:
        store = PostgresStore(conn)
        logger.info(f"resetting {trade_date} scan data for a clean re-scan")
        reset_date(conn, trade_date)
        summary = run_scan(
            trade_date,
            store=store,
            dhan_client=client,
            strategy_configs=load_strategy_configs(),
            horizon_days=load_tracking_horizon_days(),
            turnover_floor=load_turnover_floor(),
            artifact_dir="artifacts",
            alert=lambda m: bool(alert(m)),
            logger=logger,
        )
    print(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":
    main()
