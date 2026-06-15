"""Initialize the Postgres schema and register strategies from strategies.yaml.
Idempotent — safe to re-run. Requires DATABASE_URL to be set.

    python scripts/init_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # put worker/ on sys.path

from swing_trades.config import load_settings, load_strategy_configs  # noqa: E402
from swing_trades.db.auto_init import apply_schema  # noqa: E402
from swing_trades.db.connection import connection  # noqa: E402


def register_strategies(conn, configs) -> None:
    with conn.cursor() as cur:
        for c in configs:
            cur.execute(
                """
                INSERT INTO strategies (key, display_name, description, active)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    description  = EXCLUDED.description,
                    active       = EXCLUDED.active
                """,
                (c.key, c.display_name, c.description, c.active),
            )
    conn.commit()


def main() -> None:
    settings = load_settings()
    url = settings.require_database_url()
    configs = load_strategy_configs()
    with connection(url) as conn:
        apply_schema(conn)
        register_strategies(conn, configs)
    print(f"Schema applied; {len(configs)} strategies registered.")


if __name__ == "__main__":
    main()
