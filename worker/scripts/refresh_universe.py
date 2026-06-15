"""Download the Dhan instrument master and upsert the active NSE/BSE equity universe.
Cheap; safe to run daily (picks up new listings, deactivates delisted). Requires DATABASE_URL.

    python scripts/refresh_universe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_trades.config import load_settings  # noqa: E402
from swing_trades.data_layer.instruments import (  # noqa: E402
    INSTRUMENT_CSV_URL,
    equity_rows,
    parse_instrument_csv,
    resolve_universe,
)
from swing_trades.db.connection import connection  # noqa: E402
from swing_trades.db.writes import deactivate_missing_instruments, upsert_instruments  # noqa: E402


def main() -> None:
    import requests

    settings = load_settings()
    csv_text = requests.get(INSTRUMENT_CSV_URL, timeout=120).text
    universe = resolve_universe(equity_rows(parse_instrument_csv(csv_text)))
    if not universe:
        raise RuntimeError("instrument master parsed to an empty universe — refusing to write")

    with connection(settings.require_database_url()) as conn:
        upsert_instruments(conn, universe)
        deactivated = deactivate_missing_instruments(conn, {u.isin for u in universe})
    print(f"Universe refreshed: {len(universe)} active instruments; {deactivated} deactivated.")


if __name__ == "__main__":
    main()
