"""Grounded assistant: a LangChain (LCEL) chain that connects the chat to the agents' outputs.

    question --route (rules, no LLM)--> intent + zone
             --facts (tools over the pipeline's payloads)--> small, checked JSON
             --compose (local LLM, facts only)--> draft
             --guard (grounded numbers, forbidden words, status contradictions)--> answer, else deterministic template

The model never sees raw data and never computes: it phrases `facts`. Every number in its text must occur in `facts`, otherwise the
template answer is returned (`source` says which). Intent routing is rule-based because a 3B local model routes unreliably.
"""
import json
import re
from typing import Any

from langchain_core.runnables import RunnableBranch, RunnableLambda, RunnablePassthrough

from app.agents.briefing_io import NUM, briefing_input
from app.agents.briefing_llm import FORBIDDEN
from app.llm.client import LLMUnavailable, chat
from app.schemas import ZonePayload

SYSTEM = """You answer questions from emergency responders about coastal water-level risk, using ONLY the JSON facts you are given.
Rules:
1. Use only numbers that appear in the facts. Do not calculate new numbers.
2. Never give water levels, rain amounts or depths. Say high, rising, heavy.
3. Say "high water" or "water risk". Never use the words flood, safe, guarantee, dispatch.
4. If the facts do not contain the answer, say "I don't have that information."
5. Recommend, never order: "responders may prioritise".
6. Plain text, at most 4 short sentences, no markdown, no lists."""

HELP = "I can tell you a zone's risk and why, who is exposed in a zone, which zones to prioritise, what official alerts or cyclones are active, or how reliable the forecast is."
CONTEXT = re.compile(r"\b(alerts?|warnings?|watch\w*|cyclones?|hurricanes?|tropical|storms?|nhc|nws|weather|official|advisor\w*)\b", re.I)
TOP =re.compile(r"\b(top|highest|worst|most at risk|priorit\w*|rank\w*|first|where should|which zones?|biggest)\b", re.I)
WHY = re.compile(r"\b(why|reason\w*|driver\w*|cause\w*|explain\w*|because)\b", re.I)
WHO = re.compile(r"\b(who|hospital\w*|exposed|exposure|affected|shelter\w*|roads?|fire station\w*|police|facilit\w*)\b", re.I)
MODEL = re.compile(r"\b(accura\w*|reliab\w*|trust\w*|metric\w*|how good|validat\w*|precision|recall|miss\w*|false alarm\w*|uncertain\w*|confiden\w*)\b", re.I)


def _zone_from_text(q: str, zones: list[dict]) -> str | None:
    """Longest zone-name match in the question (case-insensitive, whole words)."""
    best = None
    for z in zones:
        if re.search(rf"\b{re.escape(z['name'])}\b", q, re.I) and (best is None or len(z["name"]) > len(best["name"])):
            best = z
    return best["id"] if best else None


def route(inp: dict) -> dict:
    q = inp["question"]
    zid = _zone_from_text(q, inp["zones"]) or inp.get("zone_id")
    if MODEL.search(q):
        intent = "model"
    elif CONTEXT.search(q):
        intent = "context"
    elif TOP.search(q) and not _zone_from_text(q, inp["zones"]):
        intent = "top"
    elif zid and WHO.search(q):
        intent = "exposure"
    elif zid and WHY.search(q):
        intent = "why"
    elif zid:
        intent = "zone"
    elif TOP.search(q):
        intent = "top"
    else:
        intent = "help"
    return {"intent": intent, "zone_id": zid}


def _by_zone(inp: dict) -> dict[str, ZonePayload]:
    return {p.zone_id: p for p in inp["payloads"]}


def _names(inp: dict) -> dict[str, str]:
    return {z["id"]: z["name"] for z in inp["zones"]}


def facts_zone(inp: dict) -> dict:
    p = _by_zone(inp)[inp["route"]["zone_id"]]
    b = briefing_input(p, _names(inp)[p.zone_id])
    return {k: b[k] for k in ("zone_name", "status", "as_of", "horizon_h", "probability_pct", "severity", "onset", "peak", "drivers", "reasons", "explanation",
                              "rank", "rank_reason", "alert_text", "timing_reliability", "coverage", "is_simulated")}


def facts_why(inp: dict) -> dict:
    f = facts_zone(inp)
    return {k: f[k] for k in ("zone_name", "status", "reasons", "explanation", "probability_pct")}


def facts_exposure(inp: dict) -> dict:
    p = _by_zone(inp)[inp["route"]["zone_id"]]
    b = briefing_input(p, _names(inp)[p.zone_id], max_names=5)
    return {"zone_name": b["zone_name"], "status": b["status"], "exposure_counts": b["exposure_counts"], "hospitals_named": b["hospitals_named"],
            "exposure_note": b["exposure_note"], "rank": b["rank"], "rank_reason": b["rank_reason"]}


def facts_top(inp: dict, n: int = 5) -> dict:
    names = _names(inp)
    ranked = sorted(inp["payloads"], key=lambda p: p.rank)[:n]
    rows = []
    for p in ranked:
        b = briefing_input(p, names[p.zone_id])
        rows.append({"rank": p.rank, "zone_name": b["zone_name"], "status": b["status"], "probability_pct": b["probability_pct"], "severity": b["severity"], "rank_reason": b["rank_reason"]})
    unknown = sum(p.probability is None for p in inp["payloads"])
    return {"as_of": rows and briefing_input(ranked[0], names[ranked[0].zone_id])["as_of"], "top_zones": rows, "zones_with_insufficient_data": unknown,
            "note": "The system recommends an order; responders decide."}


def facts_model(inp: dict) -> dict:
    """Honest reliability facts from the stored validation, rounded to whole percents / tenths of an hour. Missing sections are skipped."""
    m = next((r["metrics_json"] for r in inp["model_runs"] if r["model_name"].startswith("lightgbm")), None) or {}
    if isinstance(m, str):
        m = json.loads(m)
    out: dict[str, Any] = {"labels": "gauge high-water episodes (3 or more hours above a gauge's usual high mark), not observed flooding"}
    d = m.get("validation", {}).get("detection_and_timing", {}).get("all")
    if d:
        out["alert_precision_pct"], out["alert_recall_pct"] = round(d["precision"] * 100), round(d["recall"] * 100)
    split = m.get("review", {}).get("BCD", {}).get("F1_onset_split", {})
    if split.get("fresh_no_exceedance_in_last_72h"):
        out["new_rise_recall_pct"] = round(split["fresh_no_exceedance_in_last_72h"]["recall"] * 100)
    pk = m.get("peak_eval", {}).get("methods", {}).get("new_peak_model")
    if pk:
        out["peak_time_error_hours"] = round(pk["mae_h"], 1)
    a = m.get("review", {}).get("A")
    if a:
        out["real_reports_covered_by_an_alert_pct"] = round(a["share_of_reports_with_an_alert_covering_them"] * 100)
        out["alerts_are_not_selective_note"] = "during storms many zones are alerted, so the ranking matters more than the alert flag"
    out["caveats"] = "no rain forecast or tide in the water-level model; new rises are often missed; 29 of 109 zones have no usable gauge and show insufficient data"
    return out


def _context_facts(ctx: dict | None, county: str | None) -> dict:
    """Live official context -> small facts. Unavailable stays unavailable: it is never described as "no warnings"."""
    if not ctx or ctx.get("level") is None:
        return {"level": None, "available": False, "note": "live alert data is unavailable, so active warnings cannot be confirmed",
                "last_recorded": (ctx or {}).get("last_recorded")}
    c = ctx["counties"].get(county) if county else None
    f = {"available": True, "region": ctx["region"], "level": ctx["level"], "level_label": ctx["label"], "level_scope": county or "worst county",
         "drivers": (c or {}).get("drivers") or [d for v in ctx["counties"].values() for d in v["drivers"]][:5],
         "cyclones": [{k: s[k] for k in ("name", "classification", "intensity_kt", "distance_km", "heading_toward_region")} for s in ctx["cyclones"][:3]],
         "note": "official products and a distance rule, not the flood model's probability"}
    if county and c:
        f["level"], f["level_label"] = c["level"], c["label"]
    if ctx.get("forecast"):
        f["weather_model"] = {k: ctx["forecast"][k] for k in ("rain_next_24h_mm", "rain_next_72h_mm", "max_gust_next_48h_kmh")}
    if ctx.get("partial"):
        f["unavailable_sources"] = ctx["partial"]
    return f


def _county_of(inp: dict) -> str | None:
    zid = inp["route"]["zone_id"]
    return next((z.get("county") for z in inp["zones"] if z["id"] == zid), None) if zid else None


def facts_context(inp: dict) -> dict:  # sync path: no live fetch is available
    return _context_facts(None, None)


async def afacts_context(inp: dict) -> dict:
    fn = inp.get("context_fn")
    return _context_facts(await fn() if fn else None, _county_of(inp))


def _tool(fn):
    return RunnableLambda(fn)


facts_branch = RunnableBranch(
    (lambda x: x["route"]["intent"] == "zone", _tool(facts_zone)),
    (lambda x: x["route"]["intent"] == "why", _tool(facts_why)),
    (lambda x: x["route"]["intent"] == "exposure", _tool(facts_exposure)),
    (lambda x: x["route"]["intent"] == "top", _tool(facts_top)),
    (lambda x: x["route"]["intent"] == "model", _tool(facts_model)),
    (lambda x: x["route"]["intent"] == "context", RunnableLambda(facts_context, afunc=afacts_context)),
    RunnableLambda(lambda x: {"help": HELP}),
)


def template(intent: str, f: dict) -> str:
    """Deterministic answer built only from facts: the fallback and the style reference."""
    if intent == "zone":
        head = f["alert_text"].split(" Drivers:")[0]  # the explanation below says the same thing in full
        return f"{head} {f['explanation'] or ''}".strip()
    if intent == "why":
        return f["explanation"] or "No single factor stands out."
    if intent == "exposure":
        c = f["exposure_counts"]
        noun = lambda k, n: k.replace("_", " ") + ("" if n == 1 or k == "police" else "s")  # noqa: E731
        parts = ", ".join(f"{n} {noun(k, n)}" for k, n in c.items()) or "no mapped facilities"
        hosp = f" Hospitals: {', '.join(f['hospitals_named'])}." if f["hospitals_named"] else ""
        return f"{f['zone_name']} has {parts} (shelters are only potential).{hosp}"
    if intent == "top":
        if not f["top_zones"]:
            return "No zones to rank."
        lines = "; ".join(f"{r['rank']}. {r['zone_name']}" + (f" ({r['probability_pct']}%, {r['severity']})" if r["probability_pct"] is not None else " (insufficient data)") for r in f["top_zones"])
        return f"Responders may prioritise, in this order: {lines}."
    if intent == "context":
        if not f.get("available"):
            return "Live alert data is unavailable right now, so I cannot say whether any warnings are active."
        parts = [f"Official hazard level for {f['level_scope']}: {f['level_label']}" + (f" ({'; '.join(f['drivers'])})" if f["drivers"] else "") + "."]
        for c in f["cyclones"][:2]:
            parts.append(f"Active Atlantic cyclone: {c['classification']} {c['name']}, {c['distance_km']} km away" + (", heading toward the region." if c["heading_toward_region"] else "."))
        if "weather_model" in f:
            parts.append(f"The weather model forecasts about {f['weather_model']['rain_next_24h_mm']} mm of rain in the next 24 hours.")
        return " ".join(parts) + " This is separate from the flood model's probability."
    if intent == "model":
        bits = []
        if "alert_precision_pct" in f:
            bits.append(f"alerts were right {f['alert_precision_pct']}% of the time and caught {f['alert_recall_pct']}% of events on the 2020 to 2023 holdout")
        if "new_rise_recall_pct" in f:
            bits.append(f"but only {f['new_rise_recall_pct']}% of brand-new rises")
        peak = f" The peak time is off by about {f['peak_time_error_hours']} hours on average." if "peak_time_error_hours" in f else ""
        return ("The forecast " + ", ".join(bits) + "." if bits else "") + peak + f" Labels are {f['labels']}. Caveats: {f['caveats']}."
    return HELP


def _numbers_ok(text: str, facts: dict) -> list[str]:
    allowed = set(NUM.findall(json.dumps(facts, default=str)))
    return [n for n in NUM.findall(text) if n not in allowed]


async def compose(x: dict) -> dict:
    facts, intent = x["facts"], x["route"]["intent"]
    out = {"answer": template(intent, facts), "source": "template", "model": None, "reason": None, "route": x["route"], "facts": facts}
    if intent == "help":
        return out
    if facts.get("status") == "insufficient_data":  # unknown is never narrated by a model: it could call it low
        out["answer"] = f"Insufficient data, {facts['zone_name']}. Risk unknown."
        return out
    try:
        res = await chat([{"role": "user", "content": json.dumps({"question": x["question"], "facts": facts}, default=str)}], system=SYSTEM)
        text = res.text.strip()
        bad = _numbers_ok(text, facts)
        if bad:
            raise ValueError(f"invented numbers {bad}")
        if FORBIDDEN.search(text):
            raise ValueError("forbidden word")
        if intent in ("zone", "why") and facts.get("status") != "no_episode_expected" and re.search(r"\bno\b[^.]*\bepisode\b|\bnot expected\b", text, re.I):
            raise ValueError("contradicts status")
        if intent == "context" and facts.get("level") is None and re.search(r"\b(no|any|none)\b[^.]*\b(alerts?|warnings?|watch\w*)\b", text, re.I):
            raise ValueError("claims about warnings while alert data is unavailable")
        if intent == "top" and facts.get("zones_with_insufficient_data") and re.search(r"\blow\b[^.]*\brisk\b", text, re.I):
            raise ValueError("calls an unknown zone low risk")
        if facts.get("is_simulated"):
            text = "Simulation: " + text
        return {**out, "answer": text, "source": "llm", "model": res.model}
    except (LLMUnavailable, ValueError) as e:
        return {**out, "reason": str(e)[:160]}


# the chain: route -> facts -> compose. Each stage is a Runnable, so it can be traced, streamed, batched or swapped.
ASSISTANT = (
    RunnablePassthrough.assign(route=RunnableLambda(route))
    | RunnablePassthrough.assign(facts=facts_branch)
    | RunnableLambda(compose).with_config(run_name="compose")
)


async def ask(question: str, payloads: list[ZonePayload], zones: list[dict], model_runs: list[dict], zone_id: str | None = None, context_fn=None) -> dict:
    """context_fn: optional async callable returning app.context.get_context(); awaited only for alert / cyclone questions."""
    res = await ASSISTANT.ainvoke({"question": question, "payloads": payloads, "zones": zones, "model_runs": model_runs, "zone_id": zone_id, "context_fn": context_fn})
    return {"answer": res["answer"], "source": res["source"], "model": res["model"], "intent": res["route"]["intent"],
            "zone_id": res["route"]["zone_id"], "reason": res["reason"]}
