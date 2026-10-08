"""Forecasting agent. Any forecaster maps FeatureVector -> DepthTrajectory.

LightGBM quantile model (app/models/lightgbm_model.py) when its file exists, else the explicit persistence baseline.
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


from app.models.lightgbm_model import Forecaster  # noqa: E402

_lgbm = Forecaster.load()  # None if models_store/lightgbm_v1.joblib is missing: fall back to the baseline


def forecast(fv: FeatureVector, horizon_h: int = HORIZON_H) -> DepthTrajectory:
    return _lgbm.forecast(fv, horizon_h) if _lgbm else persistence_baseline(fv, horizon_h)
