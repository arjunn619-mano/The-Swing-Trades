import pytest

from swing_trades.config import load_settings, load_strategy_configs
from swing_trades.config.settings import Settings
from swing_trades.config.strategies_loader import load_tracking_horizon_days


def test_three_strategies_loaded():
    keys = {c.key for c in load_strategy_configs()}
    assert {"bullish_vol_rsi_candle", "top_breakout", "supertrend_buy"} <= keys


def test_bottom_breakout_params():
    cfgs = {c.key: c for c in load_strategy_configs()}
    p = cfgs["bullish_vol_rsi_candle"].params
    assert p["volume_ratio_min"] == 1.5
    assert p["rsi_max"] == 50
    assert p["volume_min_absolute"] == 50000


def test_top_breakout_uses_rsi_min():
    cfgs = {c.key: c for c in load_strategy_configs()}
    assert cfgs["top_breakout"].params["rsi_min"] == 55


def test_default_horizon_is_100():
    assert load_tracking_horizon_days() == 100


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    assert load_settings().database_url == "postgres://example"


def test_require_database_url_raises_when_missing():
    s = Settings(None, None, None, None, None, None, None)
    with pytest.raises(RuntimeError):
        s.require_database_url()


def test_require_dhan_lists_missing():
    s = Settings("db", None, "client", None, None, None, None)
    with pytest.raises(RuntimeError) as exc:
        s.require_dhan()
    assert "DHAN_PIN" in str(exc.value)
    assert "DHAN_TOTP_SECRET" in str(exc.value)
