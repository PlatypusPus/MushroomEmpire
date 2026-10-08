"""Grounded assistant chain with a FAKE llm: no daemon, no network."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from test_backend import T0, synthetic_snapshot

from app import assistant as A
from app import replay
from app.llm.client import ChatResult, LLMUnavailable
from app.main import app
from app.pipeline import run_tick

SNAP = synthetic_snapshot()
PS = run_tick(SNAP, T0)
ZONES = SNAP.zones


def ask(q, zone_id=None):
    return asyncio.run(A.ask(q, PS, ZONES, [], zone_id))


def fake(text):
    async def f(messages, *, system=None):
        return ChatResult(text=text, model="fake")
    return f


@pytest.mark.parametrize("q,intent", [
    ("What is the risk in Zone A?", "zone"), ("Why is Zone A at risk?", "why"), ("Which hospitals are exposed in Zone A", "exposure"),
    ("Which zones should we prioritise first?", "top"), ("How accurate is the forecast?", "model"), ("hello", "help"),
])
def test_router_picks_the_intent(q, intent, monkeypatch):
    monkeypatch.setattr(A, "chat", fake("ok"))
    assert ask(q)["intent"] == intent


def test_selected_zone_is_used_when_the_question_names_none(monkeypatch):
    monkeypatch.setattr(A, "chat", fake("ok"))
    r = ask("Why is it at risk?", zone_id="B")
    assert r["intent"] == "why" and r["zone_id"] == "B"
    assert ask("Why is it at risk?", zone_id="B")["zone_id"] == ask("why?", zone_id="B")["zone_id"]


def test_grounded_llm_answer_is_used(monkeypatch):
    p = {x.zone_id: x for x in PS}["A"]
    monkeypatch.setattr(A, "chat", fake(f"Zone A has a {round(p.probability * 100)} percent chance of high water."))
    r = ask("What is the risk in Zone A?")
    assert r["source"] == "llm" and r["model"] == "fake"


@pytest.mark.parametrize("bad", ["Zone A will reach 99 percent.", "Zone A is flooded.", "Zone A is safe."])
def test_invented_number_or_forbidden_word_falls_back_to_the_template(bad, monkeypatch):
    monkeypatch.setattr(A, "chat", fake(bad))
    r = ask("What is the risk in Zone A?")
    assert r["source"] == "template" and r["reason"] and "Zone A" in r["answer"]


def test_llm_down_falls_back_to_the_template(monkeypatch):
    async def down(messages, *, system=None):
        raise LLMUnavailable("daemon down")
    monkeypatch.setattr(A, "chat", down)
    r = ask("Which zones should we prioritise?")
    assert r["source"] == "template" and r["answer"].startswith("Responders may prioritise") and "Zone" in r["answer"]


def test_unknown_zone_is_never_described_as_low_risk(monkeypatch):
    monkeypatch.setattr(A, "chat", fake("Zone C is low risk."))
    r = ask("What is the risk in Zone C?")
    assert r["answer"] == "Insufficient data, Zone C. Risk unknown." and r["source"] == "template"  # the model is not even asked


def test_model_question_uses_only_available_facts(monkeypatch):
    monkeypatch.setattr(A, "chat", fake("ok"))
    runs = [{"model_name": "lightgbm-quantile", "metrics_json": {"validation": {"detection_and_timing": {"all": {"precision": 0.58, "recall": 0.675}}},
                                                            "peak_eval": {"methods": {"new_peak_model": {"mae_h": 3.34}}}}}]
    r = asyncio.run(A.ask("how reliable is it?", PS, ZONES, runs))
    assert r["intent"] == "model"
    f = A.facts_model({"model_runs": runs})
    assert f["alert_precision_pct"] == 58 and f["alert_recall_pct"] == 68 and f["peak_time_error_hours"] == 3.3
    assert "58% of the time" in A.template("model", f) and "3.3 hours" in A.template("model", f)


def test_endpoint(monkeypatch):
    monkeypatch.setattr(A, "chat", fake("ok"))
    replay._snaps[997] = synthetic_snapshot()
    c = TestClient(app)
    r = c.post("/api/assistant", json={"question": "Which zones should we prioritise?", "event_id": 997}).json()
    assert r["intent"] == "top" and r["source"] in ("llm", "template")
    assert c.post("/api/assistant", json={"question": "  ", "event_id": 997}).status_code == 422
