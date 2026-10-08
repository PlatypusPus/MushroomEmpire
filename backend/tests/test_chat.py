"""Graph parity + chat endpoint. LLM calls are faked: no daemon, no network."""

import asyncio
from types import SimpleNamespace

import litellm
import pytest
from fastapi.testclient import TestClient
from test_backend import T0, synthetic_snapshot

from app import api
from app.agents.graph import run_tick_graph, run_zone
from app.llm.client import ChatResult, LLMUnavailable, ThinkStripper
from app.llm.client import chat as real_chat
from app.main import app
from app.orchestrator import run_tick


def test_graph_matches_run_tick():
    snap = synthetic_snapshot()
    want = [p.model_dump() for p in run_tick(snap, T0)]
    got = [p.model_dump() for p in run_tick_graph(snap, T0)]
    assert got == want


def test_graph_zone_unknown_ends_after_ingest():
    out = run_zone(synthetic_snapshot(), "C", T0)  # C has no gauge
    assert out.get("fv") is None and "risk" not in out and out["exp"] == []


def test_chat_endpoint(monkeypatch):
    async def fake(messages, *, system=None):
        assert messages[-1]["content"] == "hi"
        return ChatResult(text="hello", model="ollama/qwen3:4b")

    monkeypatch.setattr(api, "llm_chat", fake)
    r = TestClient(app).post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"message": "hello", "model": "ollama/qwen3:4b"}


def test_chat_rejects_empty():
    c = TestClient(app)
    assert c.post("/api/chat", json={"messages": []}).status_code == 422
    assert c.post("/api/chat", json={"messages": [{"role": "user", "content": "  "}]}).status_code == 422


def test_chat_llm_down_is_503(monkeypatch):
    async def down(messages, *, system=None):
        raise LLMUnavailable("daemon down")

    monkeypatch.setattr(api, "llm_chat", down)
    r = TestClient(app).post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503


def test_client_wraps_transport_errors(monkeypatch):
    async def boom(**kwargs):
        raise ConnectionError("refused")

    monkeypatch.setattr(litellm, "acompletion", boom)
    with pytest.raises(LLMUnavailable):
        import asyncio

        asyncio.run(real_chat([{"role": "user", "content": "hi"}]))


def test_think_stripper_whole_and_split():
    s = ThinkStripper()
    assert s.feed("Hello <think>hidden thoughts</think> world") + s.flush() == "Hello  world"

    s = ThinkStripper()
    out = s.feed("Hi <th") + s.feed("ink>secret</th") + s.feed("ink> there")
    assert out + s.flush() == "Hi  there"


def test_think_stripper_drops_unclosed_span():
    s = ThinkStripper()
    assert s.feed("Answer <think>never closed") == "Answer "
    assert s.flush() == ""


def _acompletion_with(content):
    async def fake(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    return fake


@pytest.mark.parametrize("content,want", [
    ("<think>reasoning here</think>High water likely in Miami.", "High water likely in Miami."),
    ("Answer first <think>reasoning</think> then more.", "Answer first  then more."),
    ("No thinking at all.", "No thinking at all."),
])
def test_chat_strips_thinking_but_keeps_answer(monkeypatch, content, want):
    monkeypatch.setattr(litellm, "acompletion", _acompletion_with(content))
    res = asyncio.run(real_chat([{"role": "user", "content": "hi"}]))
    assert res.text == want


@pytest.mark.parametrize("content", [
    "<think>only thinking, no answer</think>",  # think-only: nothing visible survives
    "<think>never closed",  # unclosed span is dropped, never leaked
    "",  # genuinely empty
])
def test_chat_think_only_is_unavailable_not_leaked(monkeypatch, content):
    monkeypatch.setattr(litellm, "acompletion", _acompletion_with(content))
    with pytest.raises(LLMUnavailable):
        asyncio.run(real_chat([{"role": "user", "content": "hi"}]))


def test_chat_stream_endpoint(monkeypatch):
    async def fake_stream(messages, *, system=None):
        assert messages[-1]["content"] == "hi"
        yield "hel"
        yield "lo"

    monkeypatch.setattr(api, "llm_chat_stream", fake_stream)
    r = TestClient(app).post("/api/chat/stream", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200, r.text
    assert '"token": "hel"' in r.text and '"token": "lo"' in r.text
    assert '"done": true' in r.text


def test_chat_stream_rejects_empty():
    c = TestClient(app)
    assert c.post("/api/chat/stream", json={"messages": []}).status_code == 422


def test_chat_stream_error_event(monkeypatch):
    async def down(messages, *, system=None):
        raise LLMUnavailable("daemon down")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(api, "llm_chat_stream", down)
    r = TestClient(app).post("/api/chat/stream", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert '"error": "daemon down"' in r.text and "done" not in r.text
