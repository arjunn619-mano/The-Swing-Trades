"""One-time historical backfill: pull ~daily candles for every active instrument so the
indicators (RSI/ATR/Supertrend/vol-avg) have trailing history before the first scan.
Run once after refresh_universe. Requires DATABASE_URL + Dhan secrets.

    python scripts/backfill.py [lookback_days]
"""
from __future__ import annotations

import datetime as _dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_trades.config import load_settings  # noqa: E402
from swing_trades.data_layer.dhan_auth import generate_access_token  # noqa: E402
from swing_trades.data_layer.dhan_client import DhanDataClient  # noqa: E402
from swing_trades.db.connection import connection  # noqa: E402
from swing_trades.pipeline.store import PostgresStore  # noqa: E402
from swing_trades.utils import timeutils  # noqa: E402
from swing_trades.utils.logging_setup import setup_logging  # noqa: E402


def main() -> None:
    lookback_days = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    settings = load_settings()
    logger = setup_logging("logs")

    client_id, pin, totp_secret = settings.require_dhan()
    token = generate_access_token(client_id, pin, totp_secret)
    client = DhanDataClient(token.access_token, client_id)

    today = timeutils.today_ist()
    from_date = (today - _dt.timedelta(days=lookback_days)).isoformat()
    to_date = (today + _dt.timedelta(days=1)).isoformat()  # toDate is non-inclusive

    ok = fail = 0
    with connection(settings.require_database_url()) as conn:
        store = PostgresStore(conn)
        instruments = store.get_active_instruments()
        total = len(instruments)
        print(f"Backfilling {total} instruments, {from_date}..{to_date}", flush=True)
        for i, ref in enumerate(instruments, start=1):
            try:
                bars = client.historical_daily(ref.security_id, ref.exchange_segment, from_date, to_date)
                store.upsert_price_bars(ref.id, bars)
                ok += 1
            except Exception:
                fail += 1
                logger.exception(f"backfill failed for {ref.isin} ({ref.security_id})")
            if i % 200 == 0 or i == total:
                print(f"  ...{i}/{total} ({ok} ok, {fail} failed)", flush=True)
            time.sleep(0.25)  # stay well under the 5 req/s data-API limit
    print(f"Backfill complete: {ok} ok, {fail} failed.")


if __name__ == "__main__":
    main()
