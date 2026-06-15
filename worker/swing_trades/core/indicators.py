"""Technical indicators implemented in pure pandas/numpy.

Why not pandas-ta? The plan called for pandas-ta (to avoid TA-Lib's C-extension install pain
on CI). In practice pandas-ta itself breaks on numpy>=2. We only need four well-defined
indicators, so they're implemented here directly with Wilder's smoothing — zero extra deps,
fully deterministic, and unit-tested against known values. This honours the same intent
(no fragile native dependency) and the project's reliability-first value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _wilder_rma_from_zero(series: pd.Series, period: int) -> pd.Series:
    """Wilder's running moving average seeded at index `period-1` with the SMA of the
    first `period` values (used for ATR, where the series is valid from index 0)."""
    arr = series.to_numpy(dtype="float64")
    n = len(arr)
    out = np.full(n, np.nan)
    if n < period:
        return pd.Series(out, index=series.index)
    out[period - 1] = np.nanmean(arr[:period])
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + arr[i]) / period
    return pd.Series(out, index=series.index)


def _wilder_rma_after_diff(series: pd.Series, period: int) -> pd.Series:
    """Wilder smoothing for a diff-derived series (index 0 is NaN). Seeds the first
    average at index `period` with the mean of indices 1..period (used for RSI)."""
    arr = series.to_numpy(dtype="float64")
    n = len(arr)
    out = np.full(n, np.nan)
    if n <= period:
        return pd.Series(out, index=series.index)
    out[period] = np.mean(arr[1 : period + 1])
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + arr[i]) / period
    return pd.Series(out, index=series.index)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI. Returns values in [0, 100]; NaN until enough history."""
    close = close.astype("float64")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder_rma_after_diff(gain, period)
    avg_loss = _wilder_rma_after_diff(loss, period)
    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    # No losses at all -> 100; perfectly flat (no gains and no losses) -> neutral 50.
    out = out.where(avg_loss != 0, 100.0)
    flat = (avg_gain == 0) & (avg_loss == 0)
    out = out.where(~flat, 50.0)
    out = out.where(~avg_gain.isna(), np.nan)  # keep leading NaNs
    return out


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    high = high.astype("float64")
    low = low.astype("float64")
    prev_close = close.astype("float64").shift(1)
    return pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10) -> pd.Series:
    """Wilder's Average True Range."""
    return _wilder_rma_from_zero(true_range(high, low, close), period)


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """Supertrend. Returns a DataFrame with columns:
      - supertrend: the trailing stop line
      - direction:  +1 = uptrend (long), -1 = downtrend (short)
    A "buy flip" is direction going -1 -> +1 day over day.
    """
    high = high.astype("float64")
    low = low.astype("float64")
    close_s = close.astype("float64")
    atr_s = atr(high, low, close_s, period)

    hl2 = (high + low) / 2.0
    basic_upper = (hl2 + multiplier * atr_s).to_numpy()
    basic_lower = (hl2 - multiplier * atr_s).to_numpy()
    close_a = close_s.to_numpy()
    atr_a = atr_s.to_numpy()
    n = len(close_a)

    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    st = np.full(n, np.nan)
    direction = np.full(n, np.nan)

    valid = np.where(~np.isnan(atr_a))[0]
    if valid.size == 0:
        return pd.DataFrame({"supertrend": st, "direction": direction}, index=close.index)

    first = int(valid[0])
    final_upper[first] = basic_upper[first]
    final_lower[first] = basic_lower[first]
    direction[first] = 1  # convention: assume long at the first valid bar
    st[first] = final_lower[first]

    for i in range(first + 1, n):
        final_upper[i] = (
            basic_upper[i]
            if (basic_upper[i] < final_upper[i - 1]) or (close_a[i - 1] > final_upper[i - 1])
            else final_upper[i - 1]
        )
        final_lower[i] = (
            basic_lower[i]
            if (basic_lower[i] > final_lower[i - 1]) or (close_a[i - 1] < final_lower[i - 1])
            else final_lower[i - 1]
        )

        if close_a[i] > final_upper[i - 1]:
            direction[i] = 1
        elif close_a[i] < final_lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

        st[i] = final_lower[i] if direction[i] == 1 else final_upper[i]

    return pd.DataFrame({"supertrend": st, "direction": direction}, index=close.index)


def avg_volume(volume: pd.Series, period: int = 14) -> pd.Series:
    """Average of the *prior* `period` days' volume (excludes today), so a surge in today's
    volume isn't diluted by today's own value."""
    return volume.astype("float64").rolling(window=period).mean().shift(1)


def volume_ratio(volume: pd.Series, period: int = 14) -> pd.Series:
    """today_volume / average(prior `period` days). > 1 means above-average volume."""
    av = avg_volume(volume, period)
    return volume.astype("float64") / av
