"""Real-Postgres integration test (the 'rows actually written to a DB' guardrail and the
'schema applies to a fresh DB' gate). Skipped unless RUN_DB_TESTS=1 and DATABASE_URL are set
— CI provides a throwaway Postgres service; it will not touch your real database by accident.
"""
import datetime as dt
import os

import pytest

RUN = bool(os.getenv("RUN_DB_TESTS")) and bool(os.getenv("DATABASE_URL"))
pytestmark = pytest.mark.skipif(not RUN, reason="set RUN_DB_TESTS=1 and DATABASE_URL to run")

ISIN = "TESTISIN_P4"
KEY = "bullish_vol_rsi_candle"
TRADE_DATE = dt.date(2025, 8, 18)


class _FakeClient:
    def __init__(self, quotes):
        self.q = quotes

    def quote(self, batch):
        data = {}
        for seg, ids in batch.items():
            data.setdefault(seg, {})
            for sid in ids:
                k = str(sid)
                if k in self.q:
                    data[seg][k] = self.q[k]
        return {"data": data, "status": "success"}


def _cleanup(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM instruments WHERE isin = %s", (ISIN,))  # cascades to children
        cur.execute("DELETE FROM scan_runs WHERE trade_date = %s", (TRADE_DATE,))
    conn.commit()


def test_schema_applies_and_scan_writes_to_postgres():
    import psycopg

    from swing_trades.config.strategies_loader import StrategyConfig
    from swing_trades.data_layer.models import PriceBar, UniverseInstrument
    from swing_trades.db.auto_init import apply_schema
    from swing_trades.db.writes import upsert_instruments
    from swing_trades.pipeline.scan import run_scan
    from swing_trades.pipeline.store import PostgresStore
    from swing_trades.utils import timeutils

    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        apply_schema(conn)  # gate: schema applies cleanly (idempotent)
        _cleanup(conn)

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO strategies (key, display_name, active) VALUES (%s,'Bottom Breakout',TRUE) "
                "ON CONFLICT (key) DO UPDATE SET active=TRUE",
                (KEY,),
            )
        conn.commit()

        upsert_instruments(
            conn,
            [
                UniverseInstrument(
                    isin=ISIN, security_id="100", exchange_pref="NSE", exchange_segment="NSE_EQ",
                    nse_symbol="TESTCO", bse_scrip_code=None, symbol_name="TESTCO",
                    series="EQ", lot_size=1, asm_gsm_flag="N",
                )
            ],
        )

        store = PostgresStore(conn)
        ref = next(r for r in store.get_active_instruments() if r.isin == ISIN)

        d, dates = TRADE_DATE, []
        for _ in range(14):
            d = timeutils.previous_trading_day(d)
            dates.append(d)
        for dd, c in zip(reversed(dates), [120 - i for i in range(14)]):
            store.upsert_price_bars(ref.id, [PriceBar(dd, c + 0.5, c + 1, c - 1, c, 100_000)])

        client = _FakeClient(
            {"100": {"ohlc": {"open": 107, "high": 110, "low": 106.9, "close": 109.5}, "volume": 250_000}}
        )
        cfg = StrategyConfig(
            key=KEY, display_name="Bottom Breakout", description="", active=True,
            params={"volume_ratio_min": 1.5, "volume_min_absolute": 50000, "rsi_max": 50,
                    "require_candle_pattern": True, "min_candle_score": 1},
        )

        summary = run_scan(TRADE_DATE, store=store, dhan_client=client, strategy_configs=[cfg], horizon_days=100)
        assert summary.status == "success"

        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM scan_signals s JOIN instruments i ON i.id=s.instrument_id WHERE i.isin=%s",
                (ISIN,),
            )
            assert cur.fetchone()[0] >= 1
            cur.execute(
                "SELECT count(*) FROM tracker_entries t JOIN instruments i ON i.id=t.instrument_id WHERE i.isin=%s",
                (ISIN,),
            )
            assert cur.fetchone()[0] >= 1
    finally:
        _cleanup(conn)
        conn.close()
