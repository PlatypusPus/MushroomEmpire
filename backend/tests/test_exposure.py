"""Exposure agent: facilities plus each place's roads and buildings, with buildings counted by footprint, not as one item."""
from app.agents import exposure as X
from app.agents.briefing_io import briefing_input
from app.orchestrator import run_tick
from tests.test_backend import T0, synthetic_snapshot

PLACE = {"road_km": 12.0, "road_low_km": 5.0, "named_roads": 2, "buildings": 4210, "buildings_low": 900,
         "roads": [{"name": "Biscayne Blvd", "km": 2.1, "low_share": 0.62}, {"name": "NW 7th Ave", "km": 1.4, "low_share": 0.1}]}


def test_roads_and_buildings_join_the_facilities_with_honest_status(monkeypatch):
    X.places.cache_clear()
    monkeypatch.setattr(X, "places", lambda: {"A": PLACE})
    items = X.exposure("A", [{"zone_id": "A", "kind": "hospital", "name": "H", "confidence": "confirmed"}])
    road = {e.name: e for e in items if e.type == "road"}
    assert road["Biscayne Blvd"].status == "potentially_exposed" and road["Biscayne Blvd"].detail == "2.1 km here, 62% on low ground"
    assert road["NW 7th Ave"].status == "confirmed"  # mostly on higher ground
    b = next(e for e in items if e.type == "building")
    assert b.count == 4210 and b.status == "potentially_exposed" and "900 on low ground" in b.detail
    assert X.counts(items) == {"hospital": 1, "road": 2, "building": 4210}  # buildings counted by footprint
    assert X.exposure("B", []) == []  # a place missing from the file just has no roads or buildings


def test_briefing_reports_building_footprints_not_one_building(monkeypatch):
    X.places.cache_clear()
    monkeypatch.setattr(X, "places", lambda: {"A": PLACE})
    p = next(p for p in run_tick(synthetic_snapshot(), T0) if p.zone_id == "A")
    assert briefing_input(p, "Zone A")["exposure_counts"]["building"] == 4210


def test_shipped_file_covers_the_places_when_built():
    X.places.cache_clear()
    data = X.places()
    if data:  # built by scripts/sf_exposure.py; absent file means facilities only
        assert len(data) == 109 and all({"road_km", "roads"} <= set(v) for v in data.values())
