from swing_trades.strategies.base import SignalRow, Strategy, registered_strategies


def test_subclass_auto_registers():
    class Dummy(Strategy):
        key = "dummy_test_strategy"
        display_name = "Dummy"

        def evaluate(self, ctx):
            return [SignalRow(instrument_id=1, close=10.0)]

    reg = registered_strategies()
    assert reg.get("dummy_test_strategy") is Dummy


def test_signalrow_optional_fields_default_none():
    s = SignalRow(instrument_id=5, close=99.5)
    assert s.rsi is None and s.volume_ratio is None and s.candle_type is None


def test_keyless_subclass_not_registered():
    class NoKey(Strategy):
        def evaluate(self, ctx):
            return []

    assert all(v is not NoKey for v in registered_strategies().values())
