"""Live environmental map layers: parsers on synthetic (+ one saved real) payloads, KMZ handling, offline resilience, endpoint."""
import io
import zipfile
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import env_layers as E
from app.main import app

NOW = datetime(2026, 10, 8, 18, tzinfo=UTC)


def feat(event, geom=True, same="012086", ends="2026-10-09T12:00:00-04:00", msg="Alert"):
    return {"properties": {"event": event, "status": "Actual", "messageType": msg, "effective": "2026-10-08T12:00:00-04:00",
                           "ends": ends, "headline": f"{event} headline", "geocode": {"SAME": [same]}},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]} if geom else None}


def test_alerts_geo_keeps_geometry_and_filters():
    out = E.parse_alerts_geo({"features": [feat("Flood Warning"), feat("Flood Watch", same="012011"),
                                            feat("Rip Current Statement"), feat("Flood Advisory", geom=False),
                                            feat("Flood Warning", ends="2026-10-08T10:00:00+00:00")]}, now=NOW)
    assert out["type"] == "FeatureCollection"
    assert [(f["properties"]["event"], f["properties"]["level"]) for f in out["features"]] == [("Flood Warning", 3), ("Flood Watch", 2)]
    assert out["features"][0]["geometry"]["type"] == "Polygon"
    assert out["features"][1]["properties"]["counties"] == ["Broward"]


def test_alerts_geo_truncates_absurd_rings():
    big = [[[i, i] for i in range(E.MAX_ALERT_COORDS + 100)]]
    g = E._truncate({"type": "Polygon", "coordinates": big})
    assert len(g["coordinates"][0]) == E.MAX_ALERT_COORDS


def make_kmz() -> bytes:
    # NHC's real namespace variant (earth.google.com/kml/2.1, single quotes)
    kml = ("<kml xmlns='http://earth.google.com/kml/2.1'><Document>"
           '<Placemark><name>Cone</name><Polygon><outerBoundaryIs><LinearRing><coordinates>'
           '-80,25,0 -79,25,0 -79,26,0 -80,25,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>'
           '<Placemark><name>Track</name><LineString><coordinates>-80,25,0 -79,26,0</coordinates></LineString></Placemark>'
           '</Document></kml>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("storm_CONE.kml", kml)
    return buf.getvalue()


def test_parse_kmz_cone_track_and_lonlat_swap():
    out = E.parse_kmz(make_kmz())
    assert out["cone"][0] == [25.0, -80.0] and len(out["cone"]) == 4
    assert out["track"] == [[25.0, -80.0], [26.0, -79.0]]


def test_parse_kmz_garbage_returns_nulls():
    assert E.parse_kmz(b"not a zip") == {"cone": None, "track": None}


def test_parse_radar_frames_oldest_first():
    out = E.parse_radar({"host": "https://tilecache.rainviewer.com",
                         "radar": {"past": [{"time": 2, "path": "/b"}, {"time": 1, "path": "/a"}], "nowcast": [{"time": 3, "path": "/c"}]}})
    assert [f["path"] for f in out["frames"]] == ["/b", "/a", "/c"]  # past then nowcast, order kept
    assert out["host"].startswith("https://") and out["color"] and out["options"]


def hourly(times, **series):
    return {"hourly": {"time": times, **series}}


def test_parse_marine_current_and_24h_max():
    times = [f"2026-10-08T{h:02d}:00" for h in range(24)]
    out = E.parse_marine(hourly(times, wave_height=[float(h) for h in range(24)], wave_period=[5.0] * 24), now=NOW)
    assert out["wave_height_now_m"] == 18.0 and out["wave_height_next_24h_max_m"] == 23.0


def test_parse_aqi_current_hour():
    times = [f"2026-10-08T{h:02d}:00" for h in range(24)]
    out = E.parse_aqi(hourly(times, us_aqi=list(range(24)), pm2_5=[1.5] * 24, ozone=[10] * 24), now=NOW)
    assert out == {"us_aqi_now": 18, "pm2_5_now": 1.5, "ozone_now": 10}


def test_parse_wind_grid_shape_and_values():
    times = [f"2026-10-08T{h:02d}:00" for h in range(24)]
    rows = [{"hourly": {"time": times, "wind_speed_10m": [float(n)] * 24, "wind_direction_10m": [n * 10] * 24}} for n in range(16)]
    out = E.parse_wind_grid(rows, now=NOW)
    assert out is not None and out["lats"] == E.WIND_LATS and out["lons"] == E.WIND_LONS
    assert out["speed_kmh"] == [[float(r * 4 + c) for c in range(4)] for r in range(4)]
    assert out["dir_deg"][3][3] == 150
    assert E.parse_wind_grid(rows[:15]) is None


@pytest.fixture(autouse=True)
def clean():
    E._cache.clear()
    yield
    E._cache.clear()


async def _boom(client, name):
    raise ConnectionError("offline")


def test_get_env_offline_never_raises_and_marks_partial():
    import asyncio

    E._fetch, orig = _boom, E._fetch
    try:
        out = asyncio.run(E.get_env())
    finally:
        E._fetch = orig
    assert out["alerts_geo"] == {"type": "FeatureCollection", "features": []}
    assert out["cyclones"] == [] and out["wind"] is None and out["marine"] is None and out["aqi"] is None
    assert set(out["partial"]) >= {"alerts", "storms", "radar", "marine", "aqi", "wind"}
    assert all(out["sources"][n]["ok"] is False for n in ("alerts", "storms", "radar"))


def test_env_endpoint_shape(monkeypatch):
    times = [f"2026-10-08T{h:02d}:00" for h in range(24)]

    async def fake_fetch(client, name):
        if name == "alerts":
            return {"features": [feat("Tropical Storm Warning")]}
        if name == "storms":
            return {"activeStorms": [{"id": "al092026", "name": "Isaias", "classification": "HU", "intensity": "75",
                                      "pressure": "975", "latitudeNumeric": 24.0, "longitudeNumeric": -89.8,
                                      "movementDir": 60, "movementSpeed": 10, "lastUpdate": "2026-10-08T18:00:00.000Z",
                                      "trackCone": {"kmzFile": "https://www.nhc.noaa.gov/x/cone.kmz"},
                                      "forecastTrack": {"kmzFile": "https://www.nhc.noaa.gov/x/track.kmz"}}]}
        if name == "radar":
            return {"host": "https://tilecache.rainviewer.com", "radar": {"past": [{"time": 1, "path": "/p"}], "nowcast": []}}
        if name == "marine":
            return hourly(times, wave_height=[2.0] * 24, wave_period=[6.0] * 24)
        if name == "aqi":
            return hourly(times, us_aqi=[30] * 24, pm2_5=[7.0] * 24, ozone=[20] * 24)
        if name == "wind":
            return [{"hourly": {"time": times, "wind_speed_10m": [10.0] * 24, "wind_direction_10m": [90] * 24}} for _ in range(16)]
        raise AssertionError(name)

    async def fake_cone(client, url):
        assert url.endswith(".kmz")
        return E.parse_kmz(make_kmz())

    monkeypatch.setattr(E, "_fetch", fake_fetch)
    monkeypatch.setattr(E, "_cone_for", fake_cone)
    out = TestClient(app).get("/api/env").json()
    assert out["live"] is True and "flood model" in out["note"]
    assert len(out["alerts_geo"]["features"]) == 1
    assert out["cyclones"][0]["name"] == "Isaias" and out["cyclones"][0]["cone"][0] == [25.0, -80.0]
    assert out["radar"]["frames"] and out["marine"]["wave_height_now_m"] == 2.0
    assert out["aqi"]["us_aqi_now"] == 30 and out["wind"]["speed_kmh"][0][0] == 10.0
    assert out["partial"] == []
