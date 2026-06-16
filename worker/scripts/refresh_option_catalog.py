"""Download the Dhan instrument master and upsert the option catalog (OPTIDX + OPTSTK).
Applies the schema first (idempotent), so it also creates the option tables on first run.
Cheap; run daily before the option scan. Requires DATABASE_URL.

    python scripts/refresh_option_catalog.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from swing_trades.config import load_settings  # noqa: E402
from swing_trades.data_layer.instruments import INSTRUMENT_CSV_URL, parse_instrument_csv  # noqa: E402
from swing_trades.data_layer.options import parse_option_contracts  # noqa: E402
from swing_trades.db.auto_init import apply_schema  # noqa: E402
from swing_trades.db.connection import connection  # noqa: E402
from swing_trades.db.writes import upsert_option_contracts  # noqa: E402


def main() -> None:
    import requests

    settings = load_settings()

    print("Downloading instrument master...", flush=True)
    csv_text = requests.get(INSTRUMENT_CSV_URL, timeout=180).text
    contracts = parse_option_contracts(parse_instrument_csv(csv_text))
    if not contracts:
        raise RuntimeError("instrument master parsed to zero option contracts — refusing to write")
    print(f"Parsed {len(contracts):,} option contracts; writing to DB (batched)...", flush=True)

    with connection(settings.require_database_url()) as conn:
        apply_schema(conn)  # idempotent; ensures option_* tables exist
        upsert_option_contracts(conn, contracts)

    print(f"Option catalog refreshed: {len(contracts):,} contracts.", flush=True)


if __name__ == "__main__":
    main()
