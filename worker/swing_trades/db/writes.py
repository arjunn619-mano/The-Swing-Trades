"""Idempotent upserts for the universe and price history (Guardrail 4). Exercised by the
scan pipeline + the CI integration test in Phase 3 (needs a live/test Postgres)."""
from __future__ import annotations

from typing import Iterable

from ..data_layer.models import PriceBar, UniverseInstrument


def upsert_instruments(conn, universe: Iterable[UniverseInstrument]) -> dict[str, int]:
    """Upsert instruments keyed on ISIN. Returns {isin: instrument_id}."""
    ids: dict[str, int] = {}
    with conn.cursor() as cur:
        for inst in universe:
            cur.execute(
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
                RETURNING id
                """,
                (
                    inst.isin,
                    inst.security_id,
                    inst.nse_symbol,
                    inst.bse_scrip_code,
                    inst.exchange_pref,
                    inst.symbol_name,
                    inst.series,
                    inst.lot_size,
                    inst.asm_gsm_flag,
                ),
            )
            ids[inst.isin] = cur.fetchone()[0]
    conn.commit()
    return ids


def deactivate_missing_instruments(conn, current_isins: Iterable[str]) -> int:
    """Mark instruments not in the current universe as inactive (Rule M6: keep delisted
    rows as active=false rather than deleting, so a point-in-time universe stays reconstructable)."""
    isins = list(current_isins)
    if not isins:  # never deactivate everything on an empty/failed download
        return 0
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE instruments SET active = FALSE, updated_at = now() "
            "WHERE active = TRUE AND isin <> ALL(%s)",
            (isins,),
        )
        affected = cur.rowcount or 0
    conn.commit()
    return affected


def upsert_price_history(conn, instrument_id: int, bars: Iterable[PriceBar]) -> int:
    """Upsert daily bars for one instrument. Idempotent on (instrument_id, trade_date)."""
    count = 0
    with conn.cursor() as cur:
        for b in bars:
            cur.execute(
                """
                INSERT INTO price_history
                    (instrument_id, trade_date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (instrument_id, trade_date) DO UPDATE SET
                    open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                    close = EXCLUDED.close, volume = EXCLUDED.volume
                """,
                (instrument_id, b.trade_date, b.open, b.high, b.low, b.close, b.volume),
            )
            count += 1
    conn.commit()
    return count
