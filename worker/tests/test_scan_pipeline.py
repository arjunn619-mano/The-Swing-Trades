import datetime as dt

from swing_trades.config.strategies_loader import StrategyConfig
from swing_trades.data_layer.models import PriceBar
from swing_trades.pipeline.scan import run_scan
from swing_trades.pipeline.store import FakeStore, InstrumentRef
from swing_trades.utils import timeutils

CFG = StrategyConfig(
    key="bullish_vol_rsi_candle",
    display_name="Bottom Breakout",
    description="",
    active=True,
    params={
        "volume_ratio_min": 1.5,
        "volume_min_absolute": 50000,
        "rsi_max": 50,
        "require_candle_pattern": True,
        "min_candle_score": 1,
    },
)


class FakeClient:
    """Returns canned quote snapshots for requested security ids."""

    def __init__(self, quotes_by_secid):
        self.q = quotes_by_secid

    def quote(self, batch):
        data = {}
        for segment, ids in batch.items():
            data.setdefault(segment, {})
            for sid in ids:
                key = str(sid)
                if key in self.q:
                    data[segment][key] = self.q[key]
        return {"data": data, "status": "success"}


def _seed_history(store, ref, prior_closes, prior_volume, trade_date):
    d = trade_date
    dates = []
    for _ in range(len(prior_closes)):
        d = timeutils.previous_trading_day(d)
        dates.append(d)
    for dd, c in zip(reversed(dates), prior_closes):
        store.upsert_price_bars(ref.id, [PriceBar(dd, c + 0.5, c + 1, c - 1, c, prior_volume)])


def _store_with_universe(trade_date):
    store = FakeStore()
    store.register_strategy("bullish_vol_rsi_candle", 1)
    a = InstrumentRef(id=1, isin="A", security_id="100", exchange_segment="NSE_EQ")
    b = InstrumentRef(id=2, isin="B", security_id="200", exchange_segment="NSE_EQ")
    store.add_instrument(a)
    store.add_instrument(b)
    _seed_history(store, a, [120 - i for i in range(14)], 100_000, trade_date)  # declining -> low RSI
    _seed_history(store, b, [100 + i * 0.1 for i in range(14)], 100_000, trade_date)
    return store


def test_scan_writes_rows_and_reruns_are_idempotent():
    trade_date = dt.date(2025, 8, 18)  # Monday, a trading day
    store = _store_with_universe(trade_date)
    client = FakeClient(
        {
            "100": {"ohlc": {"open": 107, "high": 110, "low": 106.9, "close": 109.5}, "volume": 250_000},
            "200": {"ohlc": {"open": 101, "high": 101.5, "low": 100.5, "close": 101.2}, "volume": 100_000},
        }
    )

    summary = run_scan(trade_date, store=store, dhan_client=client, strategy_configs=[CFG], horizon_days=100)

    assert summary.status == "success"
    assert store.count_signals() >= 1            # the v1 "0-byte DB" guardrail, in test form
    assert store.count_tracker_entries() >= 1
    assert (1, 1) in store.tracker               # A qualified and is tracked
    assert (2, 1) not in store.tracker           # B (no volume surge) did not

    signals_after_first = store.count_signals()

    # Re-running the same date must not double-insert (scan_run already succeeded).
    summary2 = run_scan(trade_date, store=store, dhan_client=client, strategy_configs=[CFG], horizon_days=100)
    assert "bullish_vol_rsi_candle" in summary2.skipped_strategies
    assert store.count_signals() == signals_after_first


def test_entry_close_is_permanent_and_observation_recorded():
    trade_date = dt.date(2025, 8, 18)
    store = _store_with_universe(trade_date)
    client = FakeClient(
        {"100": {"ohlc": {"open": 107, "high": 110, "low": 106.9, "close": 109.5}, "volume": 250_000}}
    )
    run_scan(trade_date, store=store, dhan_client=client, strategy_configs=[CFG], horizon_days=100)
    entry = store.tracker[(1, 1)]
    assert entry["entry_close"] == 109.5          # set to first-seen close (Rule 3)
    assert entry["appearance_count"] == 1
    # an observation exists for the entry on the scan date
    assert (1, 1, trade_date) in store.observations


def test_non_trading_day_writes_nothing():
    sunday = dt.date(2025, 8, 17)
    store = _store_with_universe(dt.date(2025, 8, 18))
    summary = run_scan(sunday, store=store, dhan_client=FakeClient({}), strategy_configs=[CFG])
    assert summary.status == "skipped_non_trading_day"
    assert store.count_signals() == 0
    assert store.count_tracker_entries() == 0
