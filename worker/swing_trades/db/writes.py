"""Bulk, idempotent upserts for the universe and price history (Guardrail 4).

Writes are batched with executemany (one pipelined round-trip per batch) rather than row by
row — essential against Neon's free-tier compute, where per-row round-trips crawl (a full
backfill is ~800k rows). Exercised by the CI Postgres integration test."""
from __future__ import annotations

from typing import Iterable

from ..data_layer.models import OptionContract, PriceBar, UniverseInstrument


def upsert_instruments(
    conn,
    universe: Iterable[UniverseInstrument],
    deactivate_missing: bool = False,
) -> int:
    """Bulk-upsert instruments keyed on ISIN. With deactivate_missing=True, first marks every
    active row inactive (one cheap UPDATE) so only the current universe ends up active — this
    avoids a giant `isin <> ALL(array)` scan and keeps delisted rows (Rule M6). One transaction.
    """
    rows = [
        (
            inst.isin, inst.security_id, inst.nse_symbol, inst.bse_scrip_code,
            inst.exchange_pref, inst.symbol_name, inst.series, inst.lot_size, inst.asm_gsm_flag,
        )
        for inst in universe
    ]
    with conn.cursor() as cur:
        if deactivate_missing:
            cur.execute("UPDATE instruments SET active = FALSE WHERE active = TRUE")
        if rows:
            cur.executemany(
                """
                INSERT INTO instruments
                    (isin, security_id, nse_symbol, bse_scrip_code, exchange_pref,
                     segment, symbol_name, series, lot_size, asm_gsm_flag, active, updated_at)
                VALUES (%s, %s, %s, %s, %s, 'E', %s, %s, %s, %s, TRUE, now())
                ON CONFLICT (isin) DO UPDATE SET
                    security_id    = EXCLUDED.security_id,
                    nse_symbol     = EXCLUDED.nse_symbol,
                    bse_scrip_code = EXCLUDED.bse_scrip_code,
                    exchange_pref  = EXCLUDED.exchange_pref,
                    symbol_name    = EXCLUDED.symbol_name,
                    series         = EXCLUDED.series,
                    lot_size       = EXCLUDED.lot_size,
                    asm_gsm_flag   = EXCLUDED.asm_gsm_flag,
                    active         = TRUE,
                    updated_at     = now()
                """,
                rows,
            )
    conn.commit()
    return len(rows)


def record_new_listings(conn, max_bars: int = 45) -> int:
    """Idempotently record genuinely-new MAINBOARD listings into ipo_watch: an active EQ/BE/A/B
    instrument seen with < max_bars of stored history enters once and STAYS forever (the permanent
    IPO page). The backfilled starter universe already has full history so it never qualifies, and
    widened BSE X/XT/T are the wrong series. ON CONFLICT keeps the original first_seen_date.
    Returns the number of new listings recorded this run."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ipo_watch (instrument_id, first_seen_date)
            SELECT i.id, min(p.trade_date)
            FROM instruments i
            JOIN price_history p ON p.instrument_id = i.id
            WHERE i.active = TRUE AND i.series IN ('EQ', 'BE', 'A', 'B')
            GROUP BY i.id
            HAVING count(p.id) < %s
            ON CONFLICT (instrument_id) DO NOTHING
            """,
            (max_bars,),
        )
        n = cur.rowcount or 0
    conn.commit()
    return n


def upsert_price_history(conn, instrument_id: int, bars: Iterable[PriceBar]) -> int:
    """Bulk-upsert daily bars for one instrument. Idempotent on (instrument_id, trade_date)."""
    rows = [
        (instrument_id, b.trade_date, b.open, b.high, b.low, b.close, b.volume) for b in bars
    ]
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO price_history (instrument_id, trade_date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (instrument_id, trade_date) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def upsert_option_contracts(conn, contracts: Iterable[OptionContract]) -> int:
    """Bulk-upsert the option catalog keyed on security_id (Planning Pack 11, Phase O1).
    Idempotent; refreshes the mutable fields (lot_size/display_name) on conflict."""
    rows = [
        (
            c.security_id, c.underlying_symbol, c.underlying_security_id, c.exchange,
            c.instrument_type, c.expiry_date, c.strike, c.option_type, c.lot_size, c.display_name,
        )
        for c in contracts
    ]
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO option_contracts
                (security_id, underlying_symbol, underlying_security_id, exchange,
                 instrument_type, expiry_date, strike, option_type, lot_size, display_name,
                 active, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, now())
            ON CONFLICT (security_id) DO UPDATE SET
                underlying_symbol      = EXCLUDED.underlying_symbol,
                underlying_security_id = EXCLUDED.underlying_security_id,
                exchange               = EXCLUDED.exchange,
                instrument_type        = EXCLUDED.instrument_type,
                expiry_date            = EXCLUDED.expiry_date,
                strike                 = EXCLUDED.strike,
                option_type            = EXCLUDED.option_type,
                lot_size               = EXCLUDED.lot_size,
                display_name           = EXCLUDED.display_name,
                active                 = TRUE,
                updated_at             = now()
            """,
            rows,
        )
    conn.commit()
    return len(rows)
