"""Forecasting agent. Any forecaster maps FeatureVector -> DepthTrajectory.

Only the explicit baseline lives here today. Lane B's LightGBM plugs in behind the same
`forecast(fv) -> DepthTrajectory` call, with SHAP values as `drivers`.
"""

from datetime import timedelta

from app.schemas import DepthQuantiles, DepthStep, DepthTrajectory, Driver, FeatureVector

HORIZON_H = 24
TREND_HOURS = 6  # extrapolate the recent trend this far, then hold
SPREAD_M = 0.03  # q10/q90 half-width grows with sqrt(lead hours)


def persistence_baseline(fv: FeatureVector, horizon_h: int = HORIZON_H) -> DepthTrajectory:
    """Level persists plus a damped trend. The honest yardstick LightGBM has to beat."""
    steps = []
    for k in range(1, horizon_h + 1):
        q50 = fv.level_m + fv.level_trend_m_per_h * min(k, TREND_HOURS)
        s = SPREAD_M * k**0.5
        steps.append(DepthStep(t=fv.issue_ts + timedelta(hours=k), depth_m=DepthQuantiles(q10=q50 - s, q50=q50, q90=q50 + s)))
    # exact additive decomposition of the baseline's peak, not SHAP
    drivers = [
        Driver(feature="level_m", contribution=fv.level_m),
        Driver(feature="level_trend", contribution=fv.level_trend_m_per_h * TREND_HOURS),
    ]
    return DepthTrajectory(
        zone_id=fv.zone_id, issue_ts=fv.issue_ts, model="persistence-baseline-v0",
        is_simulated=fv.is_simulated, steps=steps, drivers=drivers,
    )


forecast = persistence_baseline
