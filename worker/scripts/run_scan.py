"""Run the end-of-day scan for today (IST). Wires the real Postgres store + Dhan client.
Requires DATABASE_URL + Dhan secrets in the environment.

    python scripts/run_scan.py
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
from swing_trades.pipeline.scan import run_scan  # noqa: E402
from swing_trades.pipeline.store import PostgresStore  # noqa: E402
from swing_trades.utils import timeutils  # noqa: E402
from swing_trades.utils.alerts import send_telegram_alert  # noqa: E402
from swing_trades.utils.logging_setup import setup_logging  # noqa: E402


def main() -> None:
    settings = load_settings()
    logger = setup_logging("logs")

    client_id, pin, totp_secret = settings.require_dhan()
    token = generate_access_token(client_id, pin, totp_secret)
    client = DhanDataClient(token.access_token, client_id)

    alert = functools.partial(
        send_telegram_alert,
        bot_token=settings.alert_telegram_bot_token,
        chat_id=settings.alert_telegram_chat_id,
    )

    trade_date = timeutils.today_ist()
    with connection(settings.require_database_url()) as conn:
        summary = run_scan(
            trade_date,
            store=PostgresStore(conn),
            dhan_client=client,
            strategy_configs=load_strategy_configs(),
            horizon_days=load_tracking_horizon_days(),
            turnover_floor=load_turnover_floor(),
            artifact_dir="artifacts",
            alert=lambda msg: bool(alert(msg)),
            logger=logger,
        )
    print(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":
    main()
