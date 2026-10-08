from datetime import datetime, timezone

import pytest

from app.agents.forecast import forecast, persistence_baseline
from app.models.lightgbm_model import Forecaster
from app.schemas import FeatureVector

fv = FeatureVector(zone_id="Z", issue_ts=datetime(2022, 11, 8, tzinfo=timezone.utc), level_m=0.5, level_trend_m_per_h=0.1,
                   rain_6h=1.0, rain_24h=2.0, rain_72h=3.0, hand_m=0.9, elevation_m=3.5, is_simulated=False)


@pytest.mark.skipif(Forecaster.load() is None, reason="model file not present")
def test_lightgbm_trajectory_is_ordered_and_explained():
    t = Forecaster.load().forecast(fv)
    assert len(t.steps) == 24 and t.model.startswith("lightgbm")
    assert all(s.depth_m.q10 <= s.depth_m.q50 <= s.depth_m.q90 for s in t.steps)
    from app.agents.explain import PHRASES
    assert t.drivers and all(d.feature in PHRASES for d in t.drivers)  # every driver must have a plain-language phrase


def test_missing_rain_does_not_crash_and_agent_returns_a_trajectory():
    t = forecast(fv.model_copy(update={"rain_6h": None, "rain_24h": None, "rain_72h": None}))
    assert len(t.steps) == 24
    assert persistence_baseline(fv).model == "persistence-baseline-v0"
