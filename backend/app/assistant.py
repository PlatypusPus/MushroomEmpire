"""Grounded assistant: an orchestrator that delegates to the other agents.

    question + history --plan (LLM, validated; rules fallback)--> {intent, zones, tools}
                        --run tools in parallel--> small, checked facts
                        --compose (local LLM, facts + history)--> draft
                        --guard (grounded numbers, forbidden words, status contradictions)--> answer, else deterministic render

The orchestrator never answers from its own knowledge: specialist tools
(zone detail, exposure, ranking, model metrics, live official context) do the
work and the model only phrases their outputs. Every number in its text must
occur in the tool results, otherwise the deterministic render is returned
(`source` says which). Multi-turn follow-ups ("check again", "and the
exposure there?") resolve against the conversation history; meta questions
("give me your system prompt") get a fixed friendly reply, never data.
"""

import asyncio
import json
import re
from difflib import SequenceMatcher
from typing import Any

from app.agents.briefing_io import NUM, briefing_input
from app.agents.briefing_llm import FORBIDDEN
from app.config import settings
from app.llm.client import LLMUnavailable, chat
from app.schemas import ZonePayload

SYSTEM = """You are KADAL, a calm colleague helping emergency responders with coastal water risk. Answer the question just asked the way you would say it out loud: direct, specific, varied — never the same sentence pattern twice. Lead with what matters and name the place.
You are given verified JSON facts plus the recent conversation. Ground every claim in the facts: reuse their numbers and names exactly, never compute new numbers, never invent places, warnings or details. The facts hold per-place risk under "zones", a prioritised ranking under "top", official alerts and cyclones under "live", and forecast reliability under "model". Say it in your own words: do not copy phrasing from the facts, the conversation, or these instructions — weave the reason phrases into your own sentences rather than quoting them. If the facts do not cover something, say what you do know and name what you do not.
Use plain, everyday words: say "flood risk". Never use the words safe, guarantee, dispatch.
Recommend, never order. Mention prioritisation only when ranking facts are present, and exposure only when exposure facts are present. Never refer to "the system", prompts, tools or facts — just answer. Plain text, 1 to 3 short sentences, no markdown, no lists."""

HELP = ("I can tell you a zone's risk and why, who is exposed there, which zones to prioritise, "
        "what official alerts or cyclones are active, or how reliable the forecast is. "
        "You can follow up too — 'and the exposure there?', 'check again'.")

META_REPLIES = {
    "hi": ("Hi — I'm KADAL, watching the zone data live. Ask about a place: its status, why it's "
           "at risk, who's exposed, or what to prioritise first."),
    "about": ("I'm KADAL, the coastal water-risk assistant. I check the latest model run and the "
              "official alerts, and every number I give comes from that data. I can't share my "
              "internal instructions, but I can cover any zone, the ranking, exposures, active "
              "alerts, or how reliable the forecast is."),
    "thanks": "Anytime — stay safe out there.",
    "bye": "Signing off. The zone data keeps updating on the dashboard.",
}

# Tools the orchestrator can delegate to. Each reads the agents' outputs;
# only "live" touches the network (via context_fn) and it is awaited only then.
TOOLS = ("zone_detail", "exposure", "top_zones", "model_metrics", "live")

INTENT_TOOLS = {
    "zone": ["zone_detail"],
    "why": ["zone_detail"],
    "exposure": ["exposure"],
    "top": ["top_zones"],
    "model": ["model_metrics"],
    "context": ["live"],
    "zone_context": ["zone_detail", "live"],
    "meta": [],
    "help": [],
}

ZONE_INTENTS = {"zone", "why", "exposure", "zone_context"}

# Instant rule-based planning: the fallback when the LLM planner is down or
# returns something invalid. Same intent + zone discipline as the LLM plan.
_RULE_CONTEXT = re.compile(
    r"\b(alerts?|warnings?|watch\w*|cyclones?|hurricanes?|tropical|storms?|nhc|nws|weather|official|advisor\w*)\b",
    re.I,
)
_RULE_TOP = re.compile(
    r"\b(top|highest|worst|most at risk|priorit\w*|rank\w*|first|where should|which zones?|biggest)\b",
    re.I,
)
_RULE_WHY = re.compile(
    r"\b(why|reason\w*|driver\w*|cause\w*|explain\w*|because)\b", re.I
)
_RULE_WHO = re.compile(
    r"\b(who|hospital\w*|exposed|exposure|affected|shelter\w*|roads?|fire station\w*|police|facilit\w*)\b",
    re.I,
)
_RULE_MODEL = re.compile(
    r"\b(accura\w*|reliab\w*|trust\w*|metric\w*|how good|validat\w*|precision|recall|miss\w*|false alarm\w*|uncertain\w*|confiden\w*)\b",
    re.I,
)
_RULE_META_ABOUT = re.compile(
    r"\b(who are you|what are you|system prompt|your prompt|instructions|what can you|how (do|does) (you|this|it) work|about you)\b",
    re.I,
)
_RULE_META_THANKS = re.compile(r"\b(thanks|thank you|thx)\b", re.I)
_RULE_META_BYE = re.compile(r"\b(bye|goodbye|see you)\b", re.I)
_RULE_META_HI = re.compile(r"^(hi|hey|hello|yo|good (morning|afternoon|evening))\b", re.I)


def _rule_zone_from_text(q: str, zones: list[dict]) -> str | None:
    """Longest zone-name match in the text (case-insensitive, whole words)."""
    best = None
    for z in zones:
        if re.search(rf"\b{re.escape(z['name'])}\b", q, re.I) and (
            best is None or len(z["name"]) > len(best["name"])
        ):
            best = z
    return best["id"] if best else None


def _zone_from_history(history: list[dict], zones: list[dict]) -> str | None:
    """Most recently mentioned zone in the conversation (newest message first)."""
    for m in reversed(history or []):
        zid = _rule_zone_from_text(m.get("content", ""), zones)
        if zid:
            return zid
    return None


def _meta_kind(q: str) -> str | None:
    if _RULE_META_THANKS.search(q):
        return "thanks"
    if _RULE_META_BYE.search(q):
        return "bye"
    if _RULE_META_ABOUT.search(q):
        return "about"
    if _RULE_META_HI.search(q):
        return "hi"
    return None


def rule_route(
    question: str, zones: list[dict], zone_id: str | None = None, history: list[dict] | None = None
) -> dict:
    """Deterministic intent + zone without any model call. Follow-ups with no
    place named ("check again") resolve to the last place in the conversation,
    then the dashboard's selected zone. Meta questions become "meta"."""
    q = question
    zid = _rule_zone_from_text(q, zones) or _zone_from_history(history or [], zones) or zone_id
    if _RULE_MODEL.search(q):
        intent = "model"
    elif _RULE_CONTEXT.search(q) and zid:
        intent = "zone_context"
    elif _RULE_CONTEXT.search(q):
        intent = "context"
    elif _RULE_TOP.search(q) and not _rule_zone_from_text(q, zones):
        intent = "top"
    elif zid and _RULE_WHO.search(q):
        intent = "exposure"
    elif zid and _RULE_WHY.search(q):
        intent = "why"
    elif zid:
        intent = "zone"
    elif _RULE_TOP.search(q):
        intent = "top"
    else:
        intent = "help"
    if intent in ZONE_INTENTS and zid is None:
        intent = "help"
    if intent in {"top", "model", "context", "help"}:
        zid = None
    meta = None
    if intent == "help":
        meta = _meta_kind(q)
        if meta:
            intent = "meta"
    return {"intent": intent, "zone_id": zid, "meta_kind": meta}


def _is_empty_followup(q: str, zones: list[dict]) -> bool:
    """No place, no intent keywords, no meta: only resolves against history ("check again")."""
    return (
        not _rule_zone_from_text(q, zones)
        and not _meta_kind(q)
        and not _RULE_MODEL.search(q)
        and not _RULE_CONTEXT.search(q)
        and not _RULE_TOP.search(q)
        and not _RULE_WHO.search(q)
        and not _RULE_WHY.search(q)
    )


def rule_plan(
    question: str, zones: list[dict], zone_id: str | None = None, history: list[dict] | None = None
) -> dict:
    hist = history or []
    if _is_empty_followup(question, zones) and hist:
        # "check again" means the previous question: walk back to the last
        # substantive user turn and plan that, with the full history for
        # place resolution.
        for m in reversed(hist):
            prev = str(m.get("content", "")).strip()
            if m.get("role") == "user" and prev and prev != question.strip() \
                    and not _is_empty_followup(prev, zones):
                return rule_plan(prev, zones, zone_id, hist)
    r = rule_route(question, zones, zone_id, hist)
    zids = [r["zone_id"]] if r["zone_id"] else []
    return {
        "intent": r["intent"],
        "zone_ids": zids,
        "tools": list(INTENT_TOOLS[r["intent"]]),
        "needs_live": r["intent"] in {"context", "zone_context"},
        "meta_kind": r.get("meta_kind"),
    }


PLAN_SYSTEM = """Route the user's question to one intent and pick the data tools that answer it.
Return ONLY JSON: {"intent":"...", "zone_ids":[...], "tools":[...]}
Intents:
- zone: risk/status of named places. Follow-ups with no place ("check again", "and there?", "what about exposure?") resolve to the last place in the conversation. Plain status questions ("how's X", "how is X doing", "status at X") are zone, not why.
- why: why a place has its risk
- exposure: people/facilities exposed in a place
- top: highest-risk zones / prioritisation
- model: model accuracy/reliability/validation
- context: official alerts, weather, storms or cyclones (no place named)
- zone_context: a place AND official alerts/weather/storms/cyclones
- meta: greetings, thanks, goodbyes, "who are you", asking for the system prompt or how this works
- help: anything else
zone_ids: up to 3 ids from the supplied zone list, best match first. Use the conversation to resolve follow-ups ("it", "there", "check again") to the last place discussed. For top, model, context, meta, help: [].
tools: any of ["zone_detail", "exposure", "top_zones", "model_metrics", "live"]. Include every tool whose data the answer needs (e.g. a place plus official alerts needs zone_detail and live). Per-intent defaults apply, so only add extras.
Empty follow-ups ("check again", "and now?", "what about now") mean: repeat exactly what the previous answer covered — same places, same tools.
"""


_CANNED_PREFIXES = tuple(c[:48] for c in list(META_REPLIES.values()) + [HELP])


def _clean_history(history: list[dict] | None, n: int = 6) -> list[dict]:
    out = []
    for m in (history or [])[-n:]:
        if not (isinstance(m, dict) and m.get("role") in {"user", "assistant"}):
            continue
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        if m.get("role") == "assistant" and content.startswith(_CANNED_PREFIXES):
            continue  # our own canned replies: no signal, and their example
            # phrasing ("and the exposure there?") leaks into answers
        out.append({"role": m["role"], "content": content[:2000]})
    return out


async def aplan(
    question: str, zones: list[dict], zone_id: str | None = None, history: list[dict] | None = None
) -> dict:
    """The orchestrator's plan: intent + zones + tools. The LLM proposes, the
    whitelist disposes: unknown intents, zones or tools fall back to rules."""
    hist = _clean_history(history)
    if not _rule_zone_from_text(question, zones) and _meta_kind(question):
        # Deterministic, before any model call: meta never reaches the
        # planner (which once answered "give me your system prompt" with the
        # ranking) and never reaches compose. A named place still goes to the
        # planner ("what can you tell me about Zone A" is a zone question).
        kind = _meta_kind(question)
        return {"intent": "meta", "zone_ids": [], "tools": [],
                "needs_live": False, "meta_kind": kind}
    zone_list = [
        {"id": z["id"], "name": z["name"], "county": z.get("county")} for z in zones
    ]
    try:
        res = await chat(
            [{"role": "user", "content": json.dumps(
                {"question": question, "history": hist, "zones": zone_list})}],
            system=PLAN_SYSTEM,
            model=settings.llm_brief_model,  # non-thinking: short valid JSON, no burnt budget
            max_tokens=160,
            timeout_s=settings.llm_chat_timeout_s,
        )
        decision = json.loads(res.text.strip())
        intent = decision.get("intent")
        valid_intents = set(INTENT_TOOLS)
        if intent not in valid_intents:
            raise ValueError("invalid intent")
        valid_zone_ids = {z["id"] for z in zones}
        zids = [z for z in (decision.get("zone_ids") or []) if z in valid_zone_ids][:3]
        if intent in ZONE_INTENTS and not zids:
            # The planner dropped the place (or invented one); rules still see
            # the question and the conversation.
            return rule_plan(question, zones, zone_id, hist)
        if intent not in ZONE_INTENTS:
            zids = []
        tools = [t for t in (decision.get("tools") or []) if t in TOOLS]
        for t in INTENT_TOOLS[intent]:  # defaults always run; the planner only adds
            if t not in tools:
                tools.append(t)
        if intent in {"context", "zone_context"} and "live" not in tools:
            tools.append("live")
        if intent in ZONE_INTENTS and not _rule_zone_from_text(question, zones):
            # The question names no place: the planner must follow the
            # conversation, not freestyle. A planner pick that appears
            # nowhere in the question or history (e.g. Fountainebleau after
            # talking about Miami) is overridden by the deterministic
            # resolution: history, then the dashboard's selected zone.
            mentioned = set()
            for zid in zids:
                zname = next((z["name"] for z in zones if z["id"] == zid), "")
                if zname and re.search(rf"\b{re.escape(zname)}\b", question, re.I):
                    mentioned.add(zid)
            resolved = _zone_from_history(hist, zones) or (
                zone_id if zone_id in valid_zone_ids else None
            )
            if resolved and resolved not in mentioned:
                zids = [resolved]
        # The planner often reports the live half while dropping the named
        # place; a zone name in the question upgrades to the combined plan.
        if intent == "context":
            rzid = _rule_zone_from_text(question, zones)
            if rzid is not None:
                intent, zids = "zone_context", [rzid]
                for t in INTENT_TOOLS["zone_context"]:
                    if t not in tools:
                        tools.append(t)
        return {
            "intent": intent,
            "zone_ids": zids,
            "tools": tools,
            "needs_live": intent in {"context", "zone_context"},
            "meta_kind": None,
        }
    except (LLMUnavailable, ValueError, json.JSONDecodeError, AttributeError):
        return rule_plan(question, zones, zone_id, hist)


def _by_zone(inp: dict) -> dict[str, ZonePayload]:
    return {p.zone_id: p for p in inp["payloads"]}


def _names(inp: dict) -> dict[str, str]:
    return {z["id"]: z["name"] for z in inp["zones"]}


def facts_zone(inp: dict) -> dict:
    p = _by_zone(inp)[inp["route"]["zone_id"]]
    b = briefing_input(p, _names(inp)[p.zone_id])
    return {
        k: b[k]
        for k in (
            "zone_name",
            "status",
            "as_of",
            "horizon_h",
            "probability_pct",
            "severity",
            "onset",
            "peak",
            "drivers",
            "reasons",
            "explanation",
            "rank",
            "rank_reason",
            "alert_text",
            "timing_reliability",
            "coverage",
            "is_simulated",
        )
    }


def facts_why(inp: dict) -> dict:
    f = facts_zone(inp)
    return {
        k: f[k]
        for k in ("zone_name", "status", "reasons", "explanation", "probability_pct")
    }


def facts_exposure(inp: dict) -> dict:
    p = _by_zone(inp)[inp["route"]["zone_id"]]
    b = briefing_input(p, _names(inp)[p.zone_id], max_names=5)
    return {
        "zone_name": b["zone_name"],
        "status": b["status"],
        "exposure_counts": b["exposure_counts"],
        "hospitals_named": b["hospitals_named"],
        "exposure_note": b["exposure_note"],
        "rank": b["rank"],
        "rank_reason": b["rank_reason"],
    }


def facts_top(inp: dict, n: int = 5) -> dict:
    names = _names(inp)
    ranked = sorted(inp["payloads"], key=lambda p: p.rank)[:n]
    rows = []
    for p in ranked:
        b = briefing_input(p, names[p.zone_id])
        rows.append(
            {
                "rank": p.rank,
                "zone_name": b["zone_name"],
                "status": b["status"],
                "probability_pct": b["probability_pct"],
                "severity": b["severity"],
                "rank_reason": b["rank_reason"],
            }
        )
    unknown = sum(p.probability is None for p in inp["payloads"])
    return {
        "as_of": rows and briefing_input(ranked[0], names[ranked[0].zone_id])["as_of"],
        "top_zones": rows,
        "zones_with_insufficient_data": unknown,
        "note": "The system recommends an order; responders decide.",
    }


def facts_model(inp: dict) -> dict:
    """Honest reliability facts from the stored validation, rounded to whole percents / tenths of an hour. Missing sections are skipped."""
    m = (
        next(
            (
                r["metrics_json"]
                for r in inp["model_runs"]
                if r["model_name"].startswith("lightgbm")
            ),
            None,
        )
        or {}
    )
    if isinstance(m, str):
        m = json.loads(m)
    out: dict[str, Any] = {
        "labels": "water-gauge readings above their usual high mark for 3 or more hours, not confirmed street flooding"
    }
    d = m.get("validation", {}).get("detection_and_timing", {}).get("all")
    if d:
        out["alert_precision_pct"], out["alert_recall_pct"] = (
            round(d["precision"] * 100),
            round(d["recall"] * 100),
        )
    split = m.get("review", {}).get("BCD", {}).get("F1_onset_split", {})
    if split.get("fresh_no_exceedance_in_last_72h"):
        out["new_rise_recall_pct"] = round(
            split["fresh_no_exceedance_in_last_72h"]["recall"] * 100
        )
    pk = m.get("peak_eval", {}).get("methods", {}).get("new_peak_model")
    if pk:
        out["peak_time_error_hours"] = round(pk["mae_h"], 1)
    a = m.get("review", {}).get("A")
    if a:
        out["real_reports_covered_by_an_alert_pct"] = round(
            a["share_of_reports_with_an_alert_covering_them"] * 100
        )
        out["alerts_are_not_selective_note"] = (
            "during storms many zones are alerted, so the ranking matters more than the alert flag"
        )
    out["caveats"] = (
        "our forecast does not use rain forecasts or tides; new rises are often missed; 29 of 109 places have no working water sensor and show not enough data"
    )
    return out


def _context_facts(ctx: dict | None, county: str | None) -> dict:
    """Live official context -> small facts. Unavailable stays unavailable: it is never described as "no warnings"."""
    if not ctx or ctx.get("level") is None:
        return {
            "level": None,
            "available": False,
            "note": "live alert data is unavailable, so active warnings cannot be confirmed",
            "last_recorded": (ctx or {}).get("last_recorded"),
        }
    c = ctx["counties"].get(county) if county else None
    f = {
        "available": True,
        "region": ctx["region"],
        "level": ctx["level"],
        "level_label": ctx["label"],
        "level_scope": county or "worst county",
        "drivers": (c or {}).get("drivers")
        or [d for v in ctx["counties"].values() for d in v["drivers"]][:5],
        "cyclones": [
            {
                k: s[k]
                for k in (
                    "name",
                    "classification",
                    "intensity_kt",
                    "distance_km",
                    "heading_toward_region",
                )
            }
            for s in ctx["cyclones"][:3]
        ],
        "note": "official products and a distance rule, not the flood model's probability",
    }
    if county and c:
        f["level"], f["level_label"] = c["level"], c["label"]
    if ctx.get("forecast"):
        f["weather_model"] = {
            k: ctx["forecast"][k]
            for k in ("rain_next_24h_mm", "rain_next_72h_mm", "max_gust_next_48h_kmh")
        }
    if ctx.get("partial"):
        f["unavailable_sources"] = ctx["partial"]
    return f


def _county_of_zone(zones: list[dict], zid: str | None) -> str | None:
    return next((z.get("county") for z in zones if z["id"] == zid), None) if zid else None


async def run_tools(plan: dict, inp: dict) -> dict:
    """Execute the plan's tools (zone agents, ranking, live context, metrics)
    and merge their outputs into one facts container for compose."""
    names = _names(inp)
    by = _by_zone(inp)
    facts: dict[str, Any] = {
        "primary_zone": plan["zone_ids"][0] if plan["zone_ids"] else None,
        "zones": {},
        "exposure": {},
        "top": None,
        "model": None,
        "live": None,
    }
    used: list[str] = []
    for zid in plan["zone_ids"]:
        if zid not in by:
            continue
        sub = {**inp, "route": {"zone_id": zid}}
        if "zone_detail" in plan["tools"]:
            facts["zones"][zid] = facts_zone(sub)
            used.append("zone_detail")
        if "exposure" in plan["tools"]:
            facts["exposure"][zid] = facts_exposure(sub)
            used.append("exposure")
    if "top_zones" in plan["tools"]:
        facts["top"] = facts_top(inp)
        used.append("top_zones")
    if "model_metrics" in plan["tools"]:
        facts["model"] = facts_model(inp)
        used.append("model_metrics")
    if "live" in plan["tools"]:
        fn = inp.get("context_fn")
        ctx = await fn() if fn else None
        facts["live"] = _context_facts(ctx, _county_of_zone(inp["zones"], facts["primary_zone"]))
        used.append("live")
    facts["tools_used"] = sorted(set(used))
    return facts


def template(intent: str, f: dict) -> str:
    """Deterministic answer built only from facts: the fallback and the style reference."""
    if intent == "zone":
        head = f["alert_text"].split(" Drivers:")[
            0
        ]  # the explanation below says the same thing in full
        return f"{head} {f['explanation'] or ''}".strip()
    if intent == "why":
        return f["explanation"] or "No single factor stands out."
    if intent == "exposure":
        c = f["exposure_counts"]
        noun = lambda k, n: (
            k.replace("_", " ") + ("" if n == 1 or k == "police" else "s")
        )  # noqa: E731
        parts = (
            ", ".join(f"{n} {noun(k, n)}" for k, n in c.items())
            or "no mapped facilities"
        )
        hosp = (
            f" Hospitals: {', '.join(f['hospitals_named'])}."
            if f["hospitals_named"]
            else ""
        )
        return f"{f['zone_name']} has {parts} (shelters are only potential).{hosp}"
    if intent == "top":
        if not f["top_zones"]:
            return "No zones to rank."
        lines = "; ".join(
            f"{r['rank']}. {r['zone_name']}"
            + (
                f" ({r['probability_pct']}%, {r['severity']})"
                if r["probability_pct"] is not None
                else " (not enough data)"
            )
            for r in f["top_zones"]
        )
        return f"Responders may prioritise, in this order: {lines}."
    if intent == "context":
        if not f.get("available"):
            return "Live alert data is unavailable right now, so I cannot say whether any warnings are active."
        parts = [
            f"Official hazard level for {f['level_scope']}: {f['level_label']}"
            + (f" ({'; '.join(f['drivers'])})" if f["drivers"] else "")
            + "."
        ]
        for c in f["cyclones"][:2]:
            parts.append(
                f"Active Atlantic cyclone: {c['classification']} {c['name']}, {c['distance_km']} km away"
                + (
                    ", heading toward the region."
                    if c["heading_toward_region"]
                    else "."
                )
            )
        if "weather_model" in f:
            parts.append(
                f"The weather model forecasts about {f['weather_model']['rain_next_24h_mm']} mm of rain in the next 24 hours."
            )
        return " ".join(parts) + " This is separate from the flood model's probability."
    if intent == "zone_context":
        zf, lf = f["zone"], f["live"]
        head = zf["alert_text"].split(" Drivers:")[
            0
        ]  # same head style as the zone answer
        zone_txt = f"{head} {zf['explanation'] or ''}".strip()
        if not lf.get("available"):
            return f"{zone_txt} Live alert data is unavailable right now, so I cannot say whether any warnings are active."
        return f"{zone_txt} Officially: {template('context', lf)}"
    if intent == "model":
        bits = []
        if "alert_precision_pct" in f:
            bits.append(
                f"alerts were right {f['alert_precision_pct']}% of the time and caught {f['alert_recall_pct']}% of events in the 2020 to 2023 test years"
            )
        if "new_rise_recall_pct" in f:
            bits.append(f"but only {f['new_rise_recall_pct']}% of brand-new rises")
        peak = (
            f" The peak time is off by about {f['peak_time_error_hours']} hours on average."
            if "peak_time_error_hours" in f
            else ""
        )
        return (
            ("The forecast " + ", ".join(bits) + "." if bits else "")
            + peak
            + f" Labels are {f['labels']}. Caveats: {f['caveats']}."
        )
    return HELP


def render(plan: dict, facts: dict) -> str:
    """Deterministic multi-tool answer: each tool's slice rendered from the same facts compose sees."""
    intent = plan["intent"]
    if intent == "meta":
        return META_REPLIES.get(plan.get("meta_kind") or "about", META_REPLIES["about"])
    if intent == "help":
        return HELP
    if intent in {"zone", "why", "zone_context"}:
        zones = [facts["zones"][z] for z in plan["zone_ids"] if z in facts["zones"]]
        if not zones:
            return HELP
        if intent == "zone":
            out = " ".join(template("zone", z) for z in zones)
            extra = [facts["exposure"][z] for z in plan["zone_ids"] if z in facts.get("exposure", {})]
            if extra:  # the planner asked for exposure too: answer it, don't drop it
                out += " " + " ".join(template("exposure", e) for e in extra)
        elif intent == "why":
            out = " ".join(
                template("why", {k: z[k] for k in ("zone_name", "status", "reasons", "explanation", "probability_pct")})
                for z in zones
            )
        else:
            out = " ".join(
                template("zone_context", {"zone": z, "live": facts["live"]}) for z in zones
            )
        return out
    if intent == "exposure":
        parts = [facts["exposure"][z] for z in plan["zone_ids"] if z in facts["exposure"]]
        return " ".join(template("exposure", e) for e in parts) if parts else HELP
    if intent == "top":
        return template("top", facts["top"]) if facts["top"] else HELP
    if intent == "context":
        return template("context", facts["live"]) if facts["live"] else HELP
    if intent == "model":
        return template("model", facts["model"]) if facts["model"] else HELP
    return HELP


def _numbers_ok(text: str, facts: dict) -> list[str]:
    allowed = set(NUM.findall(json.dumps(facts, default=str)))
    return [n for n in NUM.findall(text) if n not in allowed]


def _zone_statuses(plan: dict, facts: dict) -> list[tuple[str, str]]:
    return [
        (facts["zones"][z]["zone_name"], facts["zones"][z]["status"])
        for z in plan["zone_ids"]
        if z in facts["zones"]
    ]


STATUS_WORDS = {
    "insufficient_data": "unknown (not enough data)",
    "episode_possible": "possible",
    "no_episode_expected": "not expected",
    "already_above_normal_high_water": "already happening",
    "episode_expected": "expected",
}


def _compose_facts(facts: dict) -> dict:
    """Facts for the model: structured data only. The pre-baked `alert_text`
    and `explanation` prose is withheld — a small model copies such fields
    verbatim, which is why every answer read like the template. Raw material
    (reason phrases, drivers, numbers, windows) stays. (Guards still check
    against the full facts.)"""
    def strip(o, key=None):
        if isinstance(o, dict):
            return {k: strip(v, k) for k, v in o.items() if k not in {"alert_text", "explanation"}}
        if isinstance(o, list):
            return [strip(v) for v in o]
        if key == "status" and o in STATUS_WORDS:
            return STATUS_WORDS[o]  # snake_case enums leak into prose as-is
        return o
    return strip(facts)


def _repeats_previous(text: str, history: list[dict]) -> bool:
    """True when the draft says the previous assistant turn over again."""
    prev = next((m for m in reversed(history) if m.get("role") == "assistant"), None)
    if not prev:
        return False
    norm = lambda s: re.sub(r"\s+", " ", s.lower()).strip()
    a, b = norm(text), norm(str(prev.get("content", "")))
    return bool(a and b) and SequenceMatcher(None, a, b).ratio() > 0.85


async def compose(plan: dict, facts: dict, question: str, history: list[dict],
                  zone_names: list[str] | None = None) -> dict:
    intent = plan["intent"]
    out = {
        "answer": render(plan, facts),
        "source": "template",
        "model": None,
        "reason": None,
        "tools": facts.get("tools_used", []),
    }
    if intent in {"help", "meta"}:
        return out  # fixed replies: never narrated, never leaked
    primary = facts.get("primary_zone")
    zf = facts["zones"].get(primary, {}) if primary else {}
    if primary and zf.get("status") == "insufficient_data":
        # Unknown is never narrated by a model: it could call it low.
        out["answer"] = f"Insufficient data, {zf['zone_name']}. Risk unknown."
        return out

    async def draft(note: str | None) -> tuple[str, str]:
        content: dict[str, Any] = {
            "question": question,
            "history": history[-4:],
            "facts": _compose_facts(facts),
        }
        if note:
            content["note"] = note
        res = await chat(
            [{"role": "user", "content": json.dumps(content, default=str)}],
            system=SYSTEM,
            # Non-thinking model for every compose: a thinking model burns the
            # small token budget on reasoning and returns empty content, which
            # silently degrades every answer to the template.
            model=settings.llm_brief_model,
            max_tokens=settings.llm_chat_max_tokens,
            timeout_s=settings.llm_chat_timeout_s,
            temperature=0.4,  # a little warmth; numbers stay hard-guarded, worst case is a render fallback
        )
        text = res.text.strip()
        bad = _numbers_ok(text, facts)
        if bad:
            raise ValueError(f"invented numbers {bad}")
        if FORBIDDEN.search(text):
            raise ValueError("forbidden word")
        if re.search(r"\bi don'?t (have that information|know)\b", text, re.I):
            raise ValueError(
                "model abstained despite available facts"
            )  # the render above is always substantive
        statuses = _zone_statuses(plan, facts)
        if statuses and any(s != "no_episode_expected" for _, s in statuses) and re.search(
            r"\bno\b[^.]*\bepisode\b|\bnot expected\b", text, re.I
        ):
            raise ValueError("contradicts status")
        live = facts.get("live") or {}
        if intent == "context" and (zone_names or []):
            # A context answer speaks of counties and the region; naming a
            # census place means it invented zone status without zone facts.
            for name in zone_names:
                if re.search(rf"\b{re.escape(name)}\b(?!-)", text, re.I):
                    raise ValueError("names a zone without zone facts")
        if (
            intent in ("context", "zone_context")
            and live.get("level") is None
            and re.search(
                r"\b(no|any|none)\b[^.]*\b(alerts?|warnings?|watch\w*)\b", text, re.I
            )
        ):
            raise ValueError("claims about warnings while alert data is unavailable")
        if intent == "zone_context":
            for name, _ in statuses:
                if name.lower() not in text.lower():
                    raise ValueError("drops the zone half")
            if live.get("available") and not re.search(
                r"\bofficial\b|warnings?|watch\w*|advisory|cyclone|hurricane|alerts?|NWS|NHC",
                text,
                re.I,
            ):
                raise ValueError("drops the official half")
        if intent == "zone" and len(statuses) > 1:
            for name, _ in statuses:
                if name.lower() not in text.lower():
                    raise ValueError("drops a requested zone")
        if (
            intent == "top"
            and (facts.get("top") or {}).get("zones_with_insufficient_data")
            and re.search(r"\blow\b[^.]*\brisk\b", text, re.I)
        ):
            raise ValueError("calls an unknown zone low risk")
        if (
            intent in {"zone", "why", "zone_context"}
            and "exposure" not in (facts.get("tools_used") or [])
            and re.search(r"\bhospitals?\b|\bshelters?\b|\bfire ?stations?\b|\bpolice\b", text, re.I)
        ):
            # Zone facts carry no facility data (rank_reason only hints at
            # it): naming facilities without the exposure tool is ungrounded.
            raise ValueError("names facilities without exposure facts")
        return text, res.model

    try:
        text, model = await draft(None)
    except (LLMUnavailable, ValueError) as e:
        return {**out, "reason": str(e)[:160]}
    if _repeats_previous(text, history):
        # Same facts, same wording as last turn: one retry that must add the
        # next-most-important reason or acknowledge briefly. Accepted if the
        # normal guards pass, even if still similar.
        try:
            text, model = await draft(
                "Your previous answer already said this — add the next-most-important "
                "reason, or acknowledge very briefly."
            )
        except (LLMUnavailable, ValueError) as e:
            return {**out, "reason": str(e)[:160]}
    if zf.get("is_simulated"):
        text = "Simulation: " + text
    return {**out, "answer": text, "source": "llm", "model": model}


async def arun(
    plan: dict,
    question: str,
    payloads: list[ZonePayload],
    zones: list[dict],
    model_runs: list[dict],
    context_fn=None,
    history: list[dict] | None = None,
) -> dict:
    """Run the plan's tools, then compose. Split from `aplan` so the stream
    endpoint can report the plan before the tools finish."""
    hist = _clean_history(history)
    facts = await run_tools(
        plan,
        {
            "payloads": payloads,
            "zones": zones,
            "model_runs": model_runs,
            "context_fn": context_fn,
        },
    )
    res = await compose(plan, facts, question, hist, [z["name"] for z in zones])
    return {
        "answer": res["answer"],
        "source": res["source"],
        "model": res["model"],
        "intent": plan["intent"],
        "zone_id": plan["zone_ids"][0] if plan["zone_ids"] else None,
        "reason": res["reason"],
        "tools": res["tools"],
    }


async def ask(
    question: str,
    payloads: list[ZonePayload],
    zones: list[dict],
    model_runs: list[dict],
    zone_id: str | None = None,
    context_fn=None,
    history: list[dict] | None = None,
) -> dict:
    """context_fn: optional async callable returning app.context.get_context();
    awaited only when the plan needs live official data. history: recent
    {role, content} turns, newest last, used to resolve follow-ups."""
    plan = await aplan(question, zones, zone_id, history)
    return await arun(plan, question, payloads, zones, model_runs, context_fn, history)
