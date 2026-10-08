from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.models.peak_model import PeakModel, nearest_noaa, tide_timing, zone_centroid
from app.schemas import FeatureVector

T0 = datetime(2022, 11, 9, 0, tzinfo=timezone.utc)


def sine_tide(hours=200, period=12.4):
    return [{"noaa_id": "8722956", "ts": T0 - timedelta(hours=48) + timedelta(hours=h), "value": float(np.sin(2 * np.pi * (h - 48 + 3) / period))} for h in range(hours)]


def test_tide_timing_finds_next_high_and_low():
    t = tide_timing(sine_tide(), "8722956", T0)
    # sin peaks when (h-48+3)/12.4 = 0.25 -> 3.1 h after T0 + 3 offset -> first high a little after 0; spacing between highs is one period
    assert 1 <= t["hi1"] <= 13 and abs((t["hi2"] - t["hi1"]) - 12) <= 1
    assert 1 <= t["lo1"] <= 13 and not np.isnan(t["tide_rel_12"])


def test_tide_timing_without_data_is_nan_not_an_error():
    t = tide_timing([], "8722956", T0)
    assert all(np.isnan(v) for v in t.values())


def test_nearest_station_and_centroid():
    poly = {"type": "Polygon", "coordinates": [[[-80.2, 25.7], [-80.1, 25.7], [-80.1, 25.8], [-80.2, 25.8], [-80.2, 25.7]]]}
    lat, lon = zone_centroid(poly)
    assert abs(lat - 25.74) < 0.05 and nearest_noaa(lat, lon) == "8723214"  # Virginia Key


@pytest.mark.skipif(PeakModel.load() is None, reason="peak model file not present")
def test_window_is_ordered_within_24h_and_works_without_tide():
    fv = FeatureVector(zone_id="Z", issue_ts=T0, level_m=0.4, level_trend_m_per_h=0.05, rain_6h=0.0, rain_24h=0.0, rain_72h=0.0, hand_m=1.0, elevation_m=3.0,
                       is_simulated=False, level_change_6h=0.3, level_change_24h=0.2, level_max_24h=0.5, level_max_72h=0.5, level_std_24h=0.2)
    for tide in (tide_timing(sine_tide(), "8722956", T0), tide_timing([], "8722956", T0)):
        w = PeakModel.load().window(fv, tide)
        assert w.earliest <= w.likely <= w.latest
        assert T0 + timedelta(hours=1) <= w.earliest and w.latest <= T0 + timedelta(hours=24)
