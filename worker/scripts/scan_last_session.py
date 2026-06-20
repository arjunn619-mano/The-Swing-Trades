"""Scan the most-recent completed trading session using the current LIVE quote snapshot.

Use to catch up after a missed daily run, or to pull the last session on a weekend/holiday
(e.g. run on Sunday -> scans Friday). The live quote on a non-trading day / before the next
open is frozen at the last session's close, so the data is accurate. Idempotent (skips if that
session was already scanned). For OLDER missed days, use scripts/backfill.py (historical API).

    python scripts/scan_last_session.py
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
from swing_trades.pipeline.catchup import last_settled_session  # noqa: E402
from swing_trades.pipeline.scan import run_scan  # noqa: E402
from swing_trades.pipeline.store import PostgresStore  # noqa: E402
from swing_trades.utils import timeutils  # noqa: E402
from swing_trades.utils.alerts import send_telegram_alert  # noqa: E402
from swing_trades.utils.logging_setup import setup_logging  # noqa: E402


def main() -> None:
    settings = load_settings()
    logger = setup_logging("logs")
    target = last_settled_session(timeutils.now_ist())
    logger.info(f"last settled session = {target}; scanning it with the live quote.")

    alert = functools.partial(
        send_telegram_alert,
        bot_token=settings.alert_telegram_bot_token,
        chat_id=settings.alert_telegram_chat_id,
    )

    with connection(settings.require_database_url()) as conn:
        store = PostgresStore(conn)
        configs = load_strategy_configs()
        active = [c for c in configs if c.active]
        if active and all(store.scan_run_done(store.get_strategy_id(c.key), target) for c in active):
            logger.info(f"{target} already scanned; nothing to do.")
            print(json.dumps({"trade_date": target.isoformat(), "status": "already_complete"}))
            return

        token = generate_access_token(*settings.require_dhan())
        client = DhanDataClient(token.access_token, settings.dhan_client_id)
        summary = run_scan(
            target,
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
