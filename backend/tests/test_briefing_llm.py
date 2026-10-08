"""LLM briefing guard rails, with the model call stubbed (no Ollama needed)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.agents import briefing_llm
from app.llm.client import ChatResult, LLMUnavailable
from app.schemas import TimeWindow, ZonePayload

T0 = datetime(2022, 11, 9, 12, tzinfo=timezone.utc)


def payload(**kw) -> ZonePayload:
    w = TimeWindow(earliest=T0 + timedelta(hours=2), likely=T0 + timedelta(hours=3), latest=T0 + timedelta(hours=5))
    base = dict(zone_id="Z", issue_ts=T0, coverage="experimental", is_simulated=False, probability=0.78, severity="high",
                onset=w, peak=w, drivers_text=["water rising fast"], exposure=[], rank=1, rank_reason="r",
                alert_text="High Water Risk, Miami. Onset 3:00 PM, peak 3:00 PM. Drivers: water rising fast", model="m")
    return ZonePayload(**{**base, **kw})


def run(monkeypatch, reply):
    async def fake_chat(messages, system=None, **kwargs):
        if isinstance(reply, Exception):
            raise reply
        return ChatResult(text=reply, model="ollama/qwen2.5:3b")

    monkeypatch.setattr(briefing_llm, "chat", fake_chat)
    return asyncio.run(briefing_llm.llm_brief(payload(), "Miami"))


def test_grounded_text_is_used(monkeypatch):
    out = run(monkeypatch, "High water likely in Miami from 3:00 PM, 78% chance.")
    assert out["source"] == "llm" and "78%" in out["text"]
    assert out["text"].endswith("Experimental forecast.") and not out["text"].startswith("Simulation")  # code-owned labels


@pytest.mark.parametrize("bad", [
    "High water in Miami, 85 mm of rain expected.",  # invented number
    "Miami is safe tonight.",  # forbidden word
    "Simulation: high water likely in Miami from 3:00 PM.",  # real data labelled as simulated
    "High water in Miami at 3:00 PM. No high-water episode expected in next 24 hours.",  # contradicts the forecast
    LLMUnavailable("ollama down"),
])
def test_bad_or_missing_answer_falls_back_to_template(monkeypatch, bad):
    out = run(monkeypatch, bad)
    assert out["source"] == "template" and out["text"].startswith("High Water Risk, Miami")


def test_insufficient_data_never_calls_model(monkeypatch):
    monkeypatch.setattr(briefing_llm, "chat", None)  # would crash if called
    p = payload(probability=None, severity=None, onset=None, peak=None, coverage="insufficient_data")
    assert asyncio.run(briefing_llm.llm_brief(p, "X"))["text"] == "Insufficient data, risk unknown."


def test_briefing_uses_the_non_thinking_brief_model(monkeypatch):
    seen = {}

    async def fake_chat(messages, system=None, **kwargs):
        seen.update(kwargs)
        return ChatResult(text="High water likely in Miami from 3:00 PM, 78% chance.", model=kwargs.get("model"))

    monkeypatch.setattr(briefing_llm, "chat", fake_chat)
    out = asyncio.run(briefing_llm.llm_brief(payload(), "Miami"))
    from app.config import settings

    assert out["source"] == "llm" and seen.get("model") == settings.llm_brief_model


def test_guard_allows_flood_risk_but_blocks_claims_that_a_flood_happened():
    from app.agents.briefing_llm import FORBIDDEN
    for ok in ("Flood risk is high in Miami.", "A Flood Warning is active.", "Flooding is possible in the next 24 hours."):
        assert not FORBIDDEN.search(ok), ok
    for bad in ("Miami is flooded.", "Miami has been flooding all day.", "Miami is safe.", "We guarantee it."):
        assert FORBIDDEN.search(bad), bad
