"""Thin Neon/Postgres connection helper. psycopg is imported lazily so the rest of the
package (indicators, candles, calendar) can be unit-tested without the DB driver installed."""
from __future__ import annotations

from contextlib import contextmanager


def get_connection(database_url: str):
    import psycopg  # lazy import

    return psycopg.connect(database_url)


@contextmanager
def connection(database_url: str):
    conn = get_connection(database_url)
    try:
        yield conn
    finally:
        conn.close()
