"""The LangGraph tick (app/pipeline.py): identical to the plain reference loop, deterministic, isolates failures, traced, streamable."""
import asyncio
import json

import pytest
from reference_tick import reference_tick
from test_backend import T0, synthetic_snapshot

import app.pipeline as P
from app.schemas import Weights


def dumped(ps):
    return [p.model_dump(mode="json") for p in ps]


def test_matches_the_plain_reference_loop():
    snap = synthetic_snapshot()
    for w in (None, Weights(probability=0.6, severity=0.1, urgency=0.1, exposure=0.1, vulnerable=0.1, uncertainty=0.0)):
        assert dumped(P.run_tick(snap, T0, w)) == dumped(reference_tick(snap, T0, w))


def test_deterministic_across_runs_despite_parallel_zones():
    snap = synthetic_snapshot()
    assert dumped(P.run_tick(snap, T0)) == dumped(P.run_tick(snap, T0)) == dumped(P.run_tick(snap, T0))


def test_unknown_zone_is_insufficient_data_never_low_risk():
    out = {p.zone_id: p for p in P.run_tick(synthetic_snapshot(), T0)}
    assert out["C"].coverage == "insufficient_data" and out["C"].probability is None and out["C"].rank == 3


def test_a_failing_agent_isolates_its_zone_and_the_tick_completes(monkeypatch):
    real = P.forecast

    def flaky(fv):
        if fv.zone_id == "A":
            raise RuntimeError("boom")
        return real(fv)

    monkeypatch.setattr(P, "forecast", flaky)
    r = P.run_tick_traced(synthetic_snapshot(), T0)
    by = {p.zone_id: p for p in r.payloads}
    assert len(r.payloads) == 3 and by["A"].coverage == "insufficient_data" and by["A"].probability is None
    assert by["A"].rank_reason == "Forecast failed for this zone, check manually"
    assert by["B"].probability is not None  # the other zone is unaffected
    assert [(e["agent"], e["zone"]) for e in r.errors] == [("forecasting", "A")]


def test_trace_records_every_agent_per_zone():
    r = P.run_tick_traced(synthetic_snapshot(), T0)
    agents = {t["agent"] for t in r.trace}
    assert {"ingestion", "forecasting", "risk+peak", "explainability", "exposure"} <= agents
    s = P.summarize(r.trace)
    assert s["ingestion"]["calls"] == 3 and s["forecasting"]["calls"] == 2  # zone C has no gauge: stops after ingest
    assert all(t["ms"] >= 0 for t in r.trace)


def test_stream_reports_each_zone_then_the_payloads():
    async def collect():
        return [e async for e in P.astream_tick(synthetic_snapshot(), T0)]

    ev = asyncio.run(collect())
    zones = [e for e in ev if e["event"] == "zone"]
    assert sorted(e["done"] for e in zones) == [1, 2, 3] and all(e["total"] == 3 for e in zones)
    assert [e["event"] for e in ev][-2:] == ["ranked", "done"] and len(ev[-1]["payloads"]) == 3
    assert dumped(ev[-1]["payloads"]) == dumped(P.run_tick(synthetic_snapshot(), T0))


def test_diagram_names_the_agents():
    d = P.diagram()
    assert "ingest" in d and "forecast" in d and "rank" in d and "assemble" in d


def test_pipeline_endpoints():
    from fastapi.testclient import TestClient

    from app import replay
    from app.main import app
    replay._snaps[998] = synthetic_snapshot()
    c = TestClient(app)
    st = c.get("/api/pipeline?event_id=998").json()
    assert st["zones"] == 3 and st["forecast"] == 2 and st["insufficient_data"] == 1 and st["failed"] == []
    assert "forecasting" in st["agents"] and "ingest" in st["graph_mermaid"]
    body = c.get("/api/tick/stream?event_id=998").text
    events = [json.loads(line[6:]) for line in body.split("\n\n") if line.startswith("data: ")]
    assert [e["event"] for e in events].count("zone") == 3 and events[-1]["event"] == "done" and len(events[-1]["payloads"]) == 3
