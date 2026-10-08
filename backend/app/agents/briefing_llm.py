"""LLM briefing for one zone (the selected zone only: a local 3B model is too slow for every zone every tick).

Follows backend/BRIEFING_IO.md: the model sees only briefing_input(), its text must pass grounded() and the
forbidden-word check, and any failure falls back to the deterministic template, so the UI never shows unchecked text.
"""

import json
import re

from app.agents.briefing_io import briefing_input, briefing_prompt, grounded_prompt
from app.config import settings
from app.llm.client import LLMUnavailable, chat
from app.schemas import ZonePayload

SYSTEM = """Write a 2 to 3 sentence briefing for responders about ONE zone, from its JSON. Plain text, under 60 words.
Rules: use only numbers in the JSON; never state water levels, rain or depths (say high, rising, heavy); say "high water", never flood, safe, guarantee or dispatch; shelters are only potential, name only listed hospitals; recommend, never order.
By status: insufficient_data writes exactly "Insufficient data, risk unknown."; no_episode_expected says no episode is expected in the next 24 hours; episode_possible says an episode is possible with probability_pct and gives no times; already_above_normal_high_water says water is already high and gives the peak, never an onset."""

FORBIDDEN = re.compile(r"\b(flood\w*|safe\w*|guarantee\w*|dispatch\w*)\b", re.IGNORECASE)


async def llm_brief(p: ZonePayload, zone_name: str) -> dict:
    tpl = briefing_input(p, zone_name)  # deterministic fallback text + code-owned labels
    out = {"zone_id": p.zone_id, "text": tpl["alert_text"], "source": "template", "model": None, "reason": None}
    if tpl["status"] == "insufficient_data":
        out["text"] = "Insufficient data, risk unknown."
        return out
    prompt = briefing_prompt(p, zone_name)  # status-conditioned minimal prompt, not the full facts
    try:
        res = await chat([{"role": "user", "content": json.dumps(prompt)}], system=SYSTEM,
                         max_tokens=settings.llm_brief_max_tokens, timeout_s=settings.llm_chat_timeout_s)
        text = grounded_prompt(res.text.strip(), prompt)  # ValueError on any invented number
        if FORBIDDEN.search(text):
            raise ValueError(f"forbidden word in {text!r}")
        if tpl["status"] != "no_episode_expected" and re.search(r"\bno\b[^.]*\bepisode\b|\bnot expected\b", text, re.IGNORECASE):
            raise ValueError(f"text contradicts status {tpl['status']}: {text!r}")  # a 3B model copies the wrong rule
        if "simulat" in text.lower():  # labels are code-owned (below); a 3B model mislabels real data
            raise ValueError(f"model wrote a simulation label: {text!r}")
        text = ("Simulation: " if p.is_simulated else "") + text
        if p.coverage == "experimental":
            text += " Experimental forecast."
        return {**out, "text": text, "source": "llm", "model": res.model}
    except (LLMUnavailable, ValueError) as e:
        return {**out, "reason": str(e)[:200]}  # template fallback, reason kept for debugging
