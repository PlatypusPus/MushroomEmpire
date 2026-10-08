"""LLM briefing for one zone (the selected zone only: a local 3B model is too slow for every zone every tick).

Follows backend/BRIEFING_IO.md: the model sees only briefing_input(), its text must pass grounded() and the
forbidden-word check, and any failure falls back to the deterministic template, so the UI never shows unchecked text.
"""

import json
import re

from app.agents.briefing_io import briefing_input, grounded
from app.llm.client import LLMUnavailable, chat
from app.schemas import ZonePayload

SYSTEM = """You write a short briefing for emergency responders about ONE zone, from the JSON you are given.
Rules:
1. Use only numbers that appear in the JSON (probability_pct, clock times, rank, exposure counts, horizon_h). No others.
2. Never give water levels, rain amounts or depths. Say high, rising, heavy.
3. Say "high water" or "water risk". Never use the words flood, safe, guarantee, dispatch.
4. status insufficient_data: write exactly "Insufficient data, risk unknown."
5. status no_episode_expected: say no high-water episode is expected in the next horizon_h hours. Do not promise safety.
6. status episode_possible: say an episode is possible with probability_pct; give no onset or peak time.
7. status already_above_normal_high_water: say water is already high; give the peak time, not an onset time.
8. Shelters are only potential. Name hospitals from hospitals_named, count the rest.
9. Never mention simulation, experiments or data quality; labels are added separately.
10. Recommend, never order: "responders may prioritise".
Write 2 to 3 plain sentences, under 60 words. Plain text only, no markdown, no lists."""

FORBIDDEN = re.compile(r"\b(flood\w*|safe\w*|guarantee\w*|dispatch\w*)\b", re.IGNORECASE)


async def llm_brief(p: ZonePayload, zone_name: str) -> dict:
    inp = briefing_input(p, zone_name)
    out = {"zone_id": p.zone_id, "text": inp["alert_text"], "source": "template", "model": None, "reason": None}
    if inp["status"] == "insufficient_data":
        out["text"] = "Insufficient data, risk unknown."
        return out
    try:
        res = await chat([{"role": "user", "content": json.dumps(inp)}], system=SYSTEM)
        text = grounded(res.text.strip(), inp)  # ValueError on any invented number
        if FORBIDDEN.search(text):
            raise ValueError(f"forbidden word in {text!r}")
        if inp["status"] != "no_episode_expected" and re.search(r"\bno\b[^.]*\bepisode\b|\bnot expected\b", text, re.IGNORECASE):
            raise ValueError(f"text contradicts status {inp['status']}: {text!r}")  # a 3B model copies the wrong rule
        if "simulat" in text.lower():  # labels are code-owned (below); a 3B model mislabels real data
            raise ValueError(f"model wrote a simulation label: {text!r}")
        text = ("Simulation: " if p.is_simulated else "") + text
        if p.coverage == "experimental":
            text += " Experimental forecast."
        return {**out, "text": text, "source": "llm", "model": res.model}
    except (LLMUnavailable, ValueError) as e:
        return {**out, "reason": str(e)[:200]}  # template fallback, reason kept for debugging
