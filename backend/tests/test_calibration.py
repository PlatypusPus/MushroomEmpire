import numpy as np
import pytest

from app import calibration

pytestmark = pytest.mark.skipif(calibration.load() is None, reason="calibration file not present")


def test_probability_map_is_monotone_and_bounded():
    p = np.linspace(0, 1, 101)
    out = np.array([calibration.probability(x) for x in p])
    assert (np.diff(out) >= -1e-12).all() and out.min() >= 0 and out.max() <= 1


def test_severity_follows_alert_threshold_and_peak():
    t = calibration.alert_threshold()
    d1, d2 = calibration.load()["severity_cuts_pred"]
    assert calibration.severity(t - 0.01, 9.0) == "low"
    assert calibration.severity(t, d1 - 0.1) == "moderate"
    assert calibration.severity(t, (d1 + d2) / 2) == "high"
    assert calibration.severity(t, d2 + 0.1) == "severe"


def test_widening_is_nonnegative_and_applied_to_the_lightgbm_trajectory():
    from datetime import datetime, timezone

    from app.models.lightgbm_model import Forecaster
    from app.schemas import FeatureVector
    fv = FeatureVector(zone_id="Z", issue_ts=datetime(2022, 11, 8, tzinfo=timezone.utc), level_m=-0.5, level_trend_m_per_h=0.0,
                       rain_6h=0.0, rain_24h=0.0, rain_72h=0.0, hand_m=1.0, elevation_m=3.0, is_simulated=False)
    t = Forecaster.load().forecast(fv)
    assert all(s.depth_m.q10 <= s.depth_m.q50 <= s.depth_m.q90 for s in t.steps)
    assert (calibration.widen(np.arange(1, 25), [1, 3, 6, 12, 18, 24]) >= 0).all()
