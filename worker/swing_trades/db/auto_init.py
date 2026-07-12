"""Idempotent schema application. Run on every worker startup so the DB is always in sync
without a manual migration step (v1 lesson)."""
from __future__ import annotations

from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Tables the schema must define — used by tests and as a self-check.
EXPECTED_TABLES = (
    "instruments",
    "strategies",
    "price_history",
    "scan_runs",
    "scan_signals",
    "tracker_entries",
    "tracker_observations",
    "strategy_metrics",
    "trading_calendar",
    "option_contracts",
    "option_tracker",
    "option_observations",
    "news_events",
    "news_event_sources",
)


def schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def apply_schema(conn) -> None:
    """Apply the schema using an open DB-API connection (e.g. psycopg). Idempotent."""
    with conn.cursor() as cur:
        cur.execute(schema_sql())
    conn.commit()
