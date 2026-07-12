"""Step 0b turnover gate: newly-widened BSE X/XT/T names below the daily-turnover floor are
kept out of the stored/tracked set, while curated groups and already-tracked names are never
gated. Storage is asserted directly via FakeStore.prices."""
import datetime as dt

from swing_trades.pipeline.scan import run_scan
from swing_trades.pipeline.store import FakeStore, InstrumentRef

TD = dt.date(2025, 8, 18)  # Monday, a trading day
FLOOR = 2_500_000.0        # Rs.25 lakh/day


class FakeClient:
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


def _store():
    store = FakeStore()
    # id=1 curated (NSE EQ), low turnover; id=2 widened (BSE X), low turnover; id=3 widened, high turnover
    store.add_instrument(InstrumentRef(1, "C", "100", "NSE_EQ", "EQ"))
    store.add_instrument(InstrumentRef(2, "W", "200", "BSE_EQ", "X"))
    store.add_instrument(InstrumentRef(3, "H", "300", "BSE_EQ", "X"))
    return store


def _client():
    return FakeClient(
        {
            "100": {"ohlc": {"open": 100, "high": 101, "low": 99, "close": 100}, "volume": 1_000},      # turnover 100k
            "200": {"ohlc": {"open": 50, "high": 51, "low": 49, "close": 50}, "volume": 1_000},          # turnover 50k
            "300": {"ohlc": {"open": 50, "high": 51, "low": 49, "close": 50}, "volume": 200_000},        # turnover 10M
        }
    )


def _run(store, floor):
    return run_scan(
        TD, store=store, dhan_client=_client(), strategy_configs=[], horizon_days=100, turnover_floor=floor
    )


def test_gate_off_stores_every_widened_name():
    store = _store()
    summary = _run(store, 0.0)  # floor 0 = disabled (observe mode / default in tests)
    assert (2, TD) in store.prices          # widened low-turnover name still stored
    assert summary.gated_illiquid == 0


def test_gate_skips_widened_group_below_floor():
    store = _store()
    summary = _run(store, FLOOR)
    assert (1, TD) in store.prices          # curated (EQ) always stored
    assert (3, TD) in store.prices          # widened but turnover 10M >= floor
    assert (2, TD) not in store.prices      # widened X, turnover 50k < floor -> GATED
    assert summary.gated_illiquid == 1


def test_gate_never_touches_curated_group():
    """A curated NSE-EQ name with turnover far below the floor is still stored (never gated)."""
    store = _store()
    _run(store, FLOOR)
    assert (1, TD) in store.prices          # curated, turnover 100k << floor, still stored


def test_gate_protects_already_tracked_widened_name():
    """A widened name that is actively tracked must keep getting bars even below the floor,
    so an in-flight 100-day window is never corrupted."""
    store = _store()
    store.register_strategy("s", 7)
    store.create_tracker_entry(2, 7, TD, 50.0, 100)  # widened id=2 is actively tracked
    summary = _run(store, FLOOR)
    assert (2, TD) in store.prices          # tracked -> stored despite sub-floor turnover
    assert summary.gated_illiquid == 0


def test_unknown_series_is_never_gated():
    """Defensive: an instrument with no/blank series (not X/XT/T) is never dropped by the gate."""
    store = FakeStore()
    store.add_instrument(InstrumentRef(9, "U", "900", "BSE_EQ", None))  # series unknown
    client = FakeClient({"900": {"ohlc": {"open": 10, "high": 10, "low": 10, "close": 10}, "volume": 1}})
    summary = run_scan(
        TD, store=store, dhan_client=client, strategy_configs=[], horizon_days=100, turnover_floor=FLOOR
    )
    assert (9, TD) in store.prices          # turnover 10, but series not in {X,XT,T} -> kept
    assert summary.gated_illiquid == 0
