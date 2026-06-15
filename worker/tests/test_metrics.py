from swing_trades.metrics.strategy_metrics import compute_strategy_metrics


def test_empty_returns_zero_sample():
    m = compute_strategy_metrics([], horizon_days=100)
    assert m.sample_size == 0 and m.hit_rate is None


def test_hit_rate_expectancy_and_win_loss():
    m = compute_strategy_metrics([0.1, -0.05, 0.2, -0.1])
    assert m.sample_size == 4
    assert m.hit_rate == 0.5
    assert abs(m.expectancy - (0.1 - 0.05 + 0.2 - 0.1) / 4) < 1e-9
    assert abs(m.avg_win - 0.15) < 1e-9
    assert abs(m.avg_loss - (-0.075)) < 1e-9


def test_excess_vs_base_rate():
    m = compute_strategy_metrics([0.1, 0.1, 0.1, -0.1], base_returns=[0.1, -0.1, -0.1, -0.1])
    assert m.hit_rate == 0.75
    assert m.base_rate == 0.25
    assert abs(m.excess_hit_rate - 0.5) < 1e-9


def test_threshold_hit_rates():
    m = compute_strategy_metrics([0.04, 0.06, 0.11, -0.2])
    assert m.hit_rate_at_5pct == 0.5    # 0.06, 0.11
    assert m.hit_rate_at_10pct == 0.25  # 0.11
