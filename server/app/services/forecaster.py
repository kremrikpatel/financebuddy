"""Cash-flow forecasting.

Pure-numpy Holt's linear trend on monthly net flows with residual-based
confidence bands; runway detection (months until balance hits zero).
"""
from __future__ import annotations

import math

import numpy as np


def holt_linear(series: np.ndarray, alpha: float = 0.5, beta: float = 0.3,
                horizon: int = 6) -> tuple[np.ndarray, float, float]:
    """Returns (forecast[h], level_t, trend_t)."""
    if len(series) < 2:
        level = float(series[-1]) if len(series) else 0.0
        return np.full(horizon, level), level, 0.0
    level, trend = float(series[0]), float(series[1] - series[0])
    for obs in series[1:]:
        prev_level = level
        level = alpha * float(obs) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    steps = np.arange(1, horizon + 1)
    return level + trend * steps, level, trend


def forecast_net_flow(monthly_nets: list[float], horizon: int = 6) -> dict:
    """monthly_nets: oldest → newest net cash flow per month (minor units)."""
    if not monthly_nets:
        return {
            "forecast": [0] * horizon,
            "upper": [0] * horizon,
            "lower": [0] * horizon,
            "trend_per_month": 0,
            "residual_sigma": 0.0,
        }
    series = np.asarray(monthly_nets, dtype=np.float64)
    fitted_level, _, _ = holt_linear(series[:-1] if len(series) > 2 else series, horizon=len(series))
    residuals = (series[-len(fitted_level):] - fitted_level) if len(series) > 2 else np.array([0.0])
    sigma = float(np.std(residuals)) if len(residuals) > 1 else max(abs(float(np.mean(residuals))), 100)

    fc, _, trend = holt_linear(series, horizon=horizon)
    z95 = 1.96 * sigma * np.sqrt(np.arange(1, horizon + 1))
    return {
        "forecast": [int(round(v)) for v in fc],
        "upper": [int(round(fc[i] + z95[i])) for i in range(horizon)],
        "lower": [int(round(fc[i] - z95[i])) for i in range(horizon)],
        "trend_per_month": int(round(trend)),
        "residual_sigma": round(sigma, 2),
    }


def runway_months(current_balance_minor: int, forecast: list[int]) -> int | None:
    """Months until cumulative projected flow drives balance ≤ 0. None = safe horizon."""
    balance = current_balance_minor
    for i, delta in enumerate(forecast, start=1):
        balance += delta
        if balance <= 0:
            return i
    return None


def spending_spikes(daily_spend: list[tuple[str, int]], window_days: int = 30,
                    z_thresh: float = 3.0) -> list[dict]:
    """Detect days whose spend deviates strongly from trailing baseline."""
    if len(daily_spend) < window_days + 5:
        return []
    amounts = np.asarray([a for _, a in daily_spend], dtype=np.float64)
    spikes = []
    for i in range(window_days, len(amounts)):
        base = amounts[i - window_days : i]
        mu, sd = float(base.mean()), float(base.std()) or 1e-9
        z = (amounts[i] - mu) / sd
        if z >= z_thresh:
            spikes.append({"date": daily_spend[i][0], "amount": int(amounts[i]), "z": round(z, 2)})
    return spikes
