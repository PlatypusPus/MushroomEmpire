"""Backend tests on a SYNTHETIC snapshot (every row is_simulated=True). No DB, no network."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import replay
from app.agents.briefing import brief, check_numbers
from app.agents.ingestion import ingest
from app.agents.ranking import rank
from app.agents.risk import derive
from app.main import app
from app.orchestrator import run_tick
from app.schemas import DepthQuantiles, DepthStep, DepthTrajectory, Weights
from app.store import Snapshot

T0 = datetime(2023, 4, 12, 12, tzinfo=timezone(timedelta(hours=-4)))
SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def synthetic_snapshot() -> Snapshot:
    """Zone A rising fast with a hospital, B rising slowly with many shelters, C has no gauge."""
    rows = []
    for k in range(-48, 25):
        ts = T0 + timedelta(hours=k)
        for sid, base, rate in [(1, 1.0, 0.05), (2, 1.0, 0.01)]:
            rows.append({"station_id": sid, "ts": ts, "availability_ts": ts + timedelta(hours=1),
                         "value": base + rate * (k + 48), "is_simulated": True})
        rows.append({"station_id": 3, "ts": ts, "availability_ts": ts + timedelta(hours=1), "value": 0.1, "is_simulated": True})
    zone = lambda i, n: {"id": i, "name": n, "county": "Mock", "geometry": SQUARE, "elevation_m": 1.0,  # noqa: E731
                         "hand_m": 0.5, "coverage_class": "direct", "is_simulated": True}
    return Snapshot(
        event={"id": 999, "region_id": "1", "name": "Synthetic test event", "start_ts": T0, "end_ts": T0 + timedelta(hours=6),
               "is_simulated": True, "is_holdout": True, "source": "labelled_simulation"},
        regions=[{"id": "1", "name": "Mock", "kind": "deep", "coverage": "experimental", "is_simulated": True}],
        zones=[zone("A", "Zone A"), zone("B", "Zone B"), zone("C", "Zone C")],
        stations=[{"id": 1, "var": "WATER", "zone_id": "A", "threshold": 3.0},
                  {"id": 2, "var": "WATER", "zone_id": "B", "threshold": 1.4},
                  {"id": 3, "var": "RAIN", "zone_id": "A", "threshold": None}],
        rows=rows,
        assets=[{"zone_id": "A", "kind": "hospital", "name": "H", "confidence": "confirmed"}]
        + [{"zone_id": "B", "kind": "shelter", "name": f"S{i}", "confidence": "potential"} for i in range(5)],
    )


def traj(levels):
    return DepthTrajectory(
        zone_id="A", issue_ts=T0, model="t", is_simulated=True, drivers=[],
        steps=[DepthStep(t=T0 + timedelta(hours=i + 1), depth_m=DepthQuantiles(q10=x - 0.1, q50=x, q90=x + 0.1))
               for i, x in enumerate(levels)],
    )


def test_risk_derives_everything_from_one_trajectory():
    r = derive(traj([-0.5, -0.05, 0.05, 0.3, 0.2, -0.2]))
    assert r.onset.earliest == T0 + timedelta(hours=2)  # q90 crosses first
    assert r.onset.likely == T0 + timedelta(hours=3)
    assert r.onset.latest == T0 + timedelta(hours=4)
    assert r.peak.likely == T0 + timedelta(hours=4)
    assert r.probability >= 0.9 and r.severity == "high"
    quiet = derive(traj([-0.5] * 6))
    assert quiet.onset is None and quiet.severity == "low" and quiet.probability <= 0.05


def test_ingestion_never_sees_unavailable_rows():
    snap = synthetic_snapshot()
    # a spike observed before issue time but only available after it must be invisible
    snap.rows.append({"station_id": 1, "ts": T0, "availability_ts": T0 + timedelta(minutes=1), "value": 99.0, "is_simulated": True})
    fv = ingest(snap, "A", T0)
    assert fv.level_m < 50
    latest_visible = 1.0 + 0.05 * 47  # row at T0-1h became available exactly at T0
    assert fv.level_m == pytest.approx(latest_visible - 3.0)
    assert ingest(snap, "C", T0) is None  # no gauge -> unknown, not low


def test_briefing_rejects_invented_numbers():
    r = derive(traj([0.1, 0.3, 0.2]))
    text = brief("Zone A", r, ["water rising fast"])
    assert text.startswith("High Flood Risk, Zone A. Onset 1:00 PM")
    with pytest.raises(ValueError):
        check_numbers(text + " + 85 mm rain", "Zone A", r, ["water rising fast"])


def test_alert_without_onset_says_possible_not_expected():
    from app import calibration

    r = derive(traj([-0.5] * 6)).model_copy(update={"probability": max(calibration.alert_threshold(), 0.5)})
    text = brief("Zone A", r, ["water rising fast"])
    assert "possible" in text and "No flooding" not in text


def test_ranking_moves_with_weights():
    snap = synthetic_snapshot()
    zones = [(p.zone_id, p) for p in run_tick(snap, T0)]
    risks = [(derive(traj([0.4] * 6)).model_copy(update={"zone_id": "A"}), [p for z, p in zones if z == "A"][0].exposure),
             (derive(traj([0.1] * 6)).model_copy(update={"zone_id": "B"}), [p for z, p in zones if z == "B"][0].exposure)]
    only_severity = Weights(probability=0, severity=1, urgency=0, exposure=0, vulnerable=0)
    assert rank(risks, only_severity)[0][0] == "A"
    only_exposure = Weights(probability=0, severity=0, urgency=0, exposure=1, vulnerable=0)
    assert rank(risks, only_exposure)[0][0] == "B"


def test_orchestrator_payloads_keep_labels_and_unknowns():
    out = run_tick(synthetic_snapshot(), T0)
    by = {p.zone_id: p for p in out}
    assert [p.rank for p in out] == [1, 2, 3]
    assert by["C"].coverage == "insufficient_data" and by["C"].probability is None and by["C"].rank == 3
    assert all(p.is_simulated for p in out)
    assert by["A"].coverage == "simulation" and by["A"].exposure[0].type == "hospital"


def test_api_end_to_end_and_replay_ws():
    snap = synthetic_snapshot()
    replay._snaps[999] = snap
    c = TestClient(app)
    q = "?event_id=999"
    assert c.get(f"/api/regions{q}").json()[0]["id"] == "1"
    assert len(c.get(f"/api/regions/1/zones{q}").json()) == 3
    assert c.get(f"/api/zones/A{q}").json()["is_simulated"]
    assert c.get(f"/api/zones/A/alert{q}").json()["alert_text"]
    assert c.get(f"/api/zones/nope{q}").status_code == 404
    order = [p["zone_id"] for p in c.post("/api/ranking/weights", json={"event_id": 999, "weights": {
        "probability": 0, "severity": 0, "urgency": 0, "exposure": 1, "vulnerable": 0}}).json()]
    assert order[-1] == "C"
    assert c.get(f"/api/ranking{q}&exposure=1&probability=0").status_code == 200
    sess = c.post("/api/replay/999/start?step_h=3").json()
    assert len(sess["ticks"]) == 3
    feed = c.get(f"/api/replay/{sess['session_id']}/alerts?upto=2").json()
    assert [f["issue_ts"] for f in feed] == sorted((f["issue_ts"] for f in feed), reverse=True)  # newest first
    assert len({f["zone_id"] for f in feed if f["issue_ts"] == feed[-1]["issue_ts"]}) == len(
        [f for f in feed if f["issue_ts"] == feed[-1]["issue_ts"]])  # a zone fires once per crossing
    assert all(f["zone_id"] != "C" for f in feed)  # unknown zones never alert
    assert c.get("/api/replay/nope/alerts").status_code == 404
    # a restart loses sessions; the id alone must bring it back instead of a 404
    replay.sessions.clear()
    assert c.get(f"/api/replay/{sess['session_id']}/alerts?upto=2").json() == feed
    assert c.post("/api/replay/999/start?step_h=3").json()["session_id"] == sess["session_id"]  # same id, one warm-up
    with c.websocket_connect(f"/ws/replay/{sess['session_id']}?interval_s=0") as ws:
        frames = [ws.receive_json() for _ in sess["ticks"]]
    assert len(frames[-1]["zones"]) == 3
