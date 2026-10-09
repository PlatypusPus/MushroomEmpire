"""Water agent: neighbours, spread toward lower ground, and spill shapes."""
from app.agents.water import neighbours, spread
from app.orchestrator import run_tick
from tests.test_backend import T0, synthetic_snapshot


def _with(ps, **sev):
    return [p.model_copy(update={"severity": sev[p.zone_id][0], "probability": sev[p.zone_id][1]}) if p.zone_id in sev else p for p in ps]


def test_water_spreads_from_a_flooding_place_to_its_neighbours_and_less_to_higher_ground():
    snap = synthetic_snapshot()  # three places on the same square: all neighbours
    snap.zones[2]["hand_m"] = 5.0  # C sits much higher than A
    assert set(neighbours(snap)["A"]) == {"B", "C"}
    ps = _with(run_tick(snap, T0), A=("severe", 0.9), B=("low", 0.1), C=("low", 0.1))
    s = spread(snap, ps)
    assert s["affected"]["B"] == {"score": 0.9, "from": ["A"], "lower": True}
    assert s["affected"]["C"]["score"] == 0.45 and not s["affected"]["C"]["lower"]  # uphill: half
    assert "A" not in s["affected"]  # nothing around A floods
    assert [f["properties"]["zone_id"] for f in s["spill_geo"]["features"]] == ["A"]  # only flooding places spill
