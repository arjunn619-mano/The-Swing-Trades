import datetime as dt

import pandas as pd
import pytest

from swing_trades.core import indicators as ind
from swing_trades.core.candles import Candle
from swing_trades.core.candles import evaluate as evaluate_candle
from swing_trades.pipeline.features import InstrumentFeatures
from swing_trades.strategies import registered_strategies
from swing_trades.strategies.ema_base_breakout import EmaBaseBreakout

# Candle pattern is irrelevant to this strategy's green check (which uses f.close > f.open).
_CANDLE = evaluate_candle(Candle(99, 101, 98, 100), Candle(100, 100, 98, 99))


class _Ctx:
    def __init__(self, feats):
        self.features = feats
        self.trade_date = dt.date(2026, 6, 22)


def _feat(iid=1, *, close=100.0, open_=99.0, ema_fast=98.0, ema_mid=97.0,
          ema_long=100.5, st_dir=-1, vol=100000):
    return InstrumentFeatures(
        instrument_id=iid, trade_date=dt.date(2026, 6, 22), close=close, volume=vol,
        rsi=None, volume_ratio=None, candle=_CANDLE,
        supertrend_direction=st_dir, supertrend_flipped_long=False,
        open=open_, ema_fast=ema_fast, ema_mid=ema_mid, ema_long=ema_long,
    )


def _run(feat):
    return [s.instrument_id for s in EmaBaseBreakout({}).evaluate(_Ctx([feat]))]


# --- EMA indicator ---

def test_ema_sma_seed_and_recursion():
    e = ind.ema(pd.Series([float(i) for i in range(1, 11)]), 3)  # 1..10, period 3
    assert pd.isna(e.iloc[0]) and pd.isna(e.iloc[1])  # NaN until `period` bars
    assert e.iloc[2] == pytest.approx(2.0)            # SMA seed = mean(1, 2, 3)
    assert e.iloc[3] == pytest.approx(3.0)            # 0.5*4 + 0.5*2
    assert e.iloc[-1] == pytest.approx(9.0)


def test_ema_constant_series_is_flat():
    assert ind.ema(pd.Series([50.0] * 20), 9).iloc[-1] == pytest.approx(50.0)


def test_ema_all_nan_when_too_short():
    assert ind.ema(pd.Series([1.0, 2.0, 3.0]), 200).isna().all()


# --- strategy ---

def test_strategy_registered():
    assert "ema_base_breakout" in registered_strategies()


def test_qualifies_when_all_conditions_hold():
    # green (100>99), above EMA9/15, |100-100.5|/100.5 = 0.5% <= 2.5%, Supertrend red (-1), vol ok
    assert _run(_feat()) == [1]


def test_rejects_non_green_candle():
    assert _run(_feat(close=100.0, open_=101.0)) == []


def test_rejects_below_short_emas():
    assert _run(_feat(ema_fast=101.0)) == []
    assert _run(_feat(ema_mid=101.0)) == []


def test_rejects_far_from_long_ema():
    assert _run(_feat(ema_long=120.0)) == []  # 16.7% away > 2.5%


def test_rejects_supertrend_green_zone():
    assert _run(_feat(st_dir=1)) == []


def test_rejects_thin_volume():
    assert _run(_feat(vol=10000)) == []


def test_skips_when_long_ema_missing():
    assert _run(_feat(ema_long=None)) == []  # not enough history for EMA200
