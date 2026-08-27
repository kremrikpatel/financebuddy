import numpy as np

from app.services.forecaster import forecast_net_flow, runway_months, spending_spikes


def test_upward_trend_forecast():
    nets = [100_000 * i for i in range(1, 9)]
    fc = forecast_net_flow(nets, horizon=3)
    assert fc["forecast"][0] > 800_000  # trend continues upward


def test_downward_trend_flags_runway():
    nets = [-10_000] * 8
    fc = forecast_net_flow(nets, horizon=6)
    runway = runway_months(50_000, fc["forecast"])
    assert runway is not None and runway <= 5


def test_safe_balance_has_no_runway():
    fc = {"forecast": [5000, 5000]}
    assert runway_months(100_000_000, fc["forecast"]) is None


def test_spike_detection():
    daily = [(f"2026-{(d // 28) + 1:02d}-{(d % 28) + 1:02d}", 1000) for d in range(45)]
    daily.append(("2026-03-15", 90_000))
    spikes = spending_spikes(daily)
    assert len(spikes) >= 1 and spikes[-1]["amount"] == 90_000
