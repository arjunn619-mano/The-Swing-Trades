import numpy as np
import pandas as pd
import pytest

from swing_trades.core import indicators as ind


def test_rsi_all_gains_is_100():
    close = pd.Series(np.arange(1, 30, dtype=float))
    assert ind.rsi(close, 14).dropna().iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_0():
    close = pd.Series(np.arange(30, 1, -1, dtype=float))
    assert ind.rsi(close, 14).dropna().iloc[-1] == pytest.approx(0.0)


def test_rsi_flat_is_50():
    close = pd.Series([100.0] * 30)
    assert ind.rsi(close, 14).dropna().iloc[-1] == pytest.approx(50.0)


def test_rsi_known_wilder_reference():
    # Classic 15-close Wilder example; first RSI(14) ~ 70.5.
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
              45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    first = ind.rsi(pd.Series(closes), 14).dropna().iloc[0]
    assert 69.5 <= first <= 71.5


def test_rsi_first_value_at_index_period():
    r = ind.rsi(pd.Series(range(1, 16), dtype=float), 14)  # 15 values
    assert int(r.notna().idxmax()) == 14


def test_atr_constant_true_range():
    n = 30
    a = ind.atr(pd.Series([101.0] * n), pd.Series([99.0] * n), pd.Series([100.0] * n), 10)
    assert a.dropna().iloc[-1] == pytest.approx(2.0)


def test_atr_non_negative():
    rng = np.random.default_rng(0)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, 120)))
    a = ind.atr(close + 1.5, close - 1.5, close, 10)
    assert (a.dropna() >= 0).all()


def test_supertrend_flip_short_to_long():
    close = pd.Series(np.concatenate([np.linspace(200, 100, 30), np.linspace(100, 230, 30)]))
    st = ind.supertrend(close + 1.0, close - 1.0, close, 10, 3.0)
    dirs = st["direction"].dropna().to_numpy()
    assert dirs[-1] == 1
    assert (dirs == -1).any()
    assert any(dirs[i - 1] == -1 and dirs[i] == 1 for i in range(1, len(dirs)))


def test_supertrend_trails_below_in_uptrend():
    close = pd.Series(np.linspace(100, 200, 60))
    st = ind.supertrend(close + 1.0, close - 1.0, close, 10, 3.0)
    assert st["direction"].iloc[-1] == 1
    assert st["supertrend"].iloc[-1] < close.iloc[-1]


def test_volume_ratio_surge():
    vr = ind.volume_ratio(pd.Series([100] * 14 + [300], dtype=float), 14)
    assert vr.iloc[-1] == pytest.approx(3.0)


def test_avg_volume_excludes_today():
    av = ind.avg_volume(pd.Series([100] * 14 + [999999], dtype=float), 14)
    assert av.iloc[14] == pytest.approx(100.0)
