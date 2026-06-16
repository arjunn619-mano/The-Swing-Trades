"""Run the EOD OPTION scan for today (IST): fetch chains, enroll vol>1L, observe, expire;
archive the full snapshot to Parquet and (if OPTION_ARCHIVE_UPLOAD is set) upload to the
rolling GitHub Release. Run scripts/refresh_option_catalog.py first. Requires DATABASE_URL +
Dhan secrets.

    python scripts/run_option_scan.py
"""
from __future__ import annotations

import functools
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_trades.archive.options_archive import make_archive_sink  # noqa: E402
from swing_trades.config import load_settings  # noqa: E402
from swing_trades.data_layer.dhan_auth import generate_access_token  # noqa: E402
from swing_trades.data_layer.dhan_client import DhanDataClient  # noqa: E402
from swing_trades.db.connection import connection  # noqa: E402
from swing_trades.pipeline.option_scan import run_option_scan  # noqa: E402
from swing_trades.pipeline.option_store import PostgresOptionStore  # noqa: E402
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

    upload = os.getenv("OPTION_ARCHIVE_UPLOAD", "").lower() in ("1", "true", "yes")
    sink = make_archive_sink("option_archive", upload=upload, logger=logger)

    trade_date = timeutils.today_ist()
    with connection(settings.require_database_url()) as conn:
        summary = run_option_scan(
            trade_date,
            store=PostgresOptionStore(conn),
            dhan_client=client,
            snapshot_sink=sink,
            artifact_dir="artifacts",
            alert=lambda msg: bool(alert(msg)),
            logger=logger,
        )
    print(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":
    main()
