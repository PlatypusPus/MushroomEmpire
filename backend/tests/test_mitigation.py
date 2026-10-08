"""Mitigation agent: nearest facilities, advice by risk level, unknown never reads as low, contacts by county."""
from fastapi.testclient import TestClient

from app import replay
from app.agents.mitigation import advise, facilities, km, nearest
from app.main import app
from tests.test_backend import synthetic_snapshot

FACS = [{"kind": "shelter", "name": "Far School", "lat": 0.9, "lon": 0.9}, {"kind": "shelter", "name": "Near School", "lat": 0.5, "lon": 0.51},
        {"kind": "hospital", "name": "Hosp", "lat": 0.6, "lon": 0.6}]


def test_nearest_sorts_by_distance_and_reports_km():
    out = nearest(0.5, 0.5, FACS)
    assert [s["name"] for s in out["shelter"]] == ["Near School", "Far School"] and out["fire_station"] == []
    assert out["shelter"][0]["km"] == 1.1  # 0.01 deg of longitude at the equator
    assert round(km(25.77, -80.19, 26.12, -80.14)) == 39  # Miami to Fort Lauderdale


def test_endpoint_unknown_zone_is_never_advised_as_low_and_has_no_county_line():
    replay._snaps[999] = synthetic_snapshot()
    c = TestClient(app)
    r = c.get("/api/zones/C/mitigation?event_id=999").json()  # zone C has no water gauge
    assert r["level"] == "unknown" and "not low" in r["steps"][0]
    assert r["contacts"][0]["phone"] == "911" and all("Miami-Dade" not in x["name"] for x in r["contacts"])  # county "Mock"
    assert any("flood water" in s for s in r["steps"]) and r["is_simulated"]
    a = c.get("/api/zones/A/mitigation?event_id=999").json()
    assert a["level"] in ("low", "moderate", "high", "severe")
    assert c.get("/api/zones/nope/mitigation?event_id=999").status_code == 404


def test_real_place_gets_its_county_line_and_nearby_shelters():
    zone = {"id": "x", "name": "Miami", "county": "Miami-Dade",
            "geometry": {"type": "Polygon", "coordinates": [[[-80.20, 25.76], [-80.18, 25.76], [-80.18, 25.78], [-80.20, 25.78], [-80.20, 25.76]]]}}
    p = type("P", (), {"zone_id": "x", "probability": None, "severity": None, "onset": None, "peak": None, "is_simulated": False})()
    r = advise(p, zone)
    assert "305-468-5900" in r["contacts"][1]["phone"]
    assert len(r["nearest"]["shelter"]) == 3 and r["nearest"]["shelter"][0]["km"] < 3 and r["nearest"]["hospital"]
    assert len(facilities()) > 2000 and "open" in r["shelter_note"]


def test_live_advice_follows_the_official_county_level_and_feed_down_is_not_all_clear(monkeypatch):
    from app import context
    from app.agents.mitigation import advise_live
    from app.config import settings

    zone = {"id": "x", "name": "Miami", "county": "Miami-Dade",
            "geometry": {"type": "Polygon", "coordinates": [[[-80.20, 25.76], [-80.18, 25.76], [-80.18, 25.78], [-80.20, 25.78], [-80.20, 25.76]]]}}
    warn = advise_live(zone, {"level": 3, "label": "warning", "drivers": ["Flood Warning (Miami-Dade)"]}, FACS)
    assert warn["level"] == "high" and "warning is in effect" in warn["steps"][0] and warn["official"]["active"] == ["Flood Warning (Miami-Dade)"]
    calm = advise_live(zone, {"level": 0, "label": "none", "drivers": []}, FACS)
    assert calm["level"] == "low" and not calm["is_simulated"]
    down = advise_live(zone, None, FACS)
    assert down["level"] == "unknown" and "does not mean there is no danger" in down["steps"][0]

    replay._snaps[999] = synthetic_snapshot()
    monkeypatch.setattr(settings, "default_event_id", 999)

    async def ctx(force=False):
        return {"counties": {"Mock": {"level": 2, "label": "watch", "drivers": ["Flood Watch (Mock)"]}}}
    monkeypatch.setattr(context, "get_context", ctx)
    c = TestClient(app)
    r = c.get("/api/zones/A/mitigation/live").json()
    assert r["official"]["level"] == 2 and "watch" in r["steps"][0]
    assert c.get("/api/zones/nope/mitigation/live").status_code == 404


def test_point_outside_our_places_uses_the_official_alerts_at_that_point(monkeypatch):
    from app import live_point
    from app.agents.mitigation import advise_point

    hw = [{"event": "Hurricane Warning", "level": 4, "headline": "", "ends": None}, {"event": "Flood Watch", "level": 2, "headline": "", "ends": None}]
    r = advise_point(30.52, -86.48, {"city": "Niceville", "state": "FL"}, hw, FACS)
    assert r["name"] == "Niceville, FL" and r["level"] == "severe" and "most serious" in r["steps"][0]
    assert r["official"]["active"] == ["Hurricane Warning", "Flood Watch"]
    assert any("Florida" in c["name"] for c in r["contacts"])
    al = advise_point(31.0, -87.5, {"city": "Bay Minette", "state": "AL"}, [], None)
    assert al["level"] == "low" and all("Florida" not in c["name"] for c in al["contacts"])  # the FL line does not serve Alabama
    assert al["nearest_failed"] and al["nearest"]["shelter"] == []  # failed lookup is reported, not shown as "no shelters"
    assert advise_point(31.0, -87.5, None, None, None)["level"] == "unknown"  # feed down is never an all-clear

    replay._snaps[999] = synthetic_snapshot()
    from app.config import settings
    monkeypatch.setattr(settings, "default_event_id", 999)

    async def fake_lookup(lat, lon):
        return {"city": "Niceville", "state": "FL"}, hw, FACS
    monkeypatch.setattr(live_point, "lookup", fake_lookup)
    c = TestClient(app)
    assert c.get("/api/mitigation/live/point?lat=30.52&lon=-86.48").json()["name"] == "Niceville, FL"
    assert c.get("/api/mitigation/live/point?lat=91&lon=-86").status_code == 422
