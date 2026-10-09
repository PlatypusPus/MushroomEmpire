"""Live priority: ranked like the replay, unknown places last and never low, background refresh reported as progress."""
from app import live_priority as lp
from app.agents.explain import explain_zone
from app.agents.risk import derive
from app.models.lightgbm_model import Forecaster
from app.schemas import Weights
from tests.test_backend import T0, synthetic_snapshot
from app.agents.ingestion import ingest


def test_known_places_rank_first_and_a_place_without_a_gauge_is_unknown_not_low(monkeypatch):
    snap = synthetic_snapshot()
    f = Forecaster.load()
    res = {}
    for zid in ("A", "B"):  # C has no gauge
        fv = ingest(snap, zid, T0)
        traj = f.forecast(fv)
        risk = derive(traj)
        res[zid] = {"fv": fv, "traj": traj, "risk": risk, "drivers": explain_zone(traj.drivers, fv, risk),
                    "site": {"id": "0228", "km": 2.0}, "version": "v"}
    res["C"] = None
    monkeypatch.setitem(lp._state, "results", res)
    monkeypatch.setitem(lp._state, "issued", T0)
    rows = lp.payloads(snap, Weights())
    assert [r.zone_id for r in rows][-1] == "C" and rows[-1].probability is None and rows[-1].coverage == "insufficient_data"
    assert {r.zone_id for r in rows[:2]} == {"A", "B"} and all(r.coverage == "experimental" and "USGS 0228" in r.model for r in rows[:2])
    assert [r.rank for r in rows] == [1, 2, 3]


def test_status_starts_one_background_refresh_and_reports_progress(monkeypatch):
    snap = synthetic_snapshot()
    started = []
    monkeypatch.setattr("app.accounts.spawn", lambda coro: (started.append(1), coro.close()))
    monkeypatch.setattr(lp, "_state", {"at": 0.0, "issued": None, "running": False, "done": 0, "total": 0, "results": {}})
    out = lp.status(snap, Weights())
    assert out["status"] == "computing" and out["rows"] == [] and out["total"] == 3 and started == [1]
    lp._state["running"] = True
    lp.status(snap, Weights())
    assert started == [1]  # already running: no second refresh
