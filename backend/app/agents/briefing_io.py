"""Input/output contract for a briefing (LLM) wrapper.

briefing_input(): one ZonePayload -> a small, safe dict an LLM may narrate. It drops everything the model must not
print (stage values, rain, raw coordinates), collapses the exposure list to counts, and states the situation as an
explicit `status` so the LLM does not have to infer it. grounded(): hard check that a generated text only uses
numbers (and zone name) that appear in that input. See backend/BRIEFING_IO.md.
"""
import re
from collections import Counter
from datetime import timedelta

from app import calibration
from app.schemas import ZonePayload

HORIZON_H = 24
NUM = re.compile(r"\d+(?:[.:]\d+)?")
STATUS = ("insufficient_data", "episode_possible", "no_episode_expected", "already_above_normal_high_water", "episode_expected")


def clock(t) -> str:
    return t.strftime("%I:%M %p").lstrip("0")  # SF2Bench wall clock, no timezone label (ROOT_CONTEXT item 2f)


def _window(w):
    return None if w is None else {"earliest": clock(w.earliest), "likely": clock(w.likely), "latest": clock(w.latest)}


def _status(p: ZonePayload) -> str:
    if p.probability is None:
        return "insufficient_data"
    if p.onset is None and p.probability >= calibration.alert_threshold():
        return "episode_possible"  # median stays under the mark but the upper band crosses it: validated alert rule
    if p.onset is None:
        return "no_episode_expected"
    if p.onset.likely - p.issue_ts <= timedelta(hours=1):  # the first forecast step is already above the mark
        return "already_above_normal_high_water"
    return "episode_expected"


def briefing_input(p: ZonePayload, zone_name: str, max_names: int = 3) -> dict:
    status = _status(p)
    counts = Counter(e.type for e in p.exposure)
    named = [e.name for e in p.exposure if e.type == "hospital"][:max_names]  # only confirmed-kind facilities are named
    return {
        "zone_id": p.zone_id, "zone_name": zone_name, "status": status,
        "as_of": clock(p.issue_ts), "horizon_h": HORIZON_H,
        "probability_pct": None if p.probability is None else round(p.probability * 100),
        "severity": p.severity, "onset": _window(p.onset), "peak": _window(p.peak),
        "drivers": p.drivers_text,
        "reasons": [{"phrase": r.phrase, "strength": r.strength} for r in p.reasons], "explanation": p.explanation,
        "exposure_counts": dict(counts), "hospitals_named": named,
        "exposure_note": "shelters are only potential (OSM schools and community centres); never call them confirmed shelters",
        "rank": p.rank, "rank_reason": p.rank_reason,
        # peak: dedicated model since ROOT_CONTEXT 2n (mean error ~3.3 h, 80% window ~12 h wide); onset hour is only slightly better than "now"
        "timing_reliability": {"peak": "moderate", "onset": "rough"},
        "is_simulated": p.is_simulated, "coverage": p.coverage, "model": p.model,
        "alert_text": p.alert_text,  # the deterministic template: the fallback if the LLM is down or fails the check
    }


def allowed_numbers(inp: dict) -> set[str]:
    nums = set(NUM.findall(" ".join(str(x) for x in [inp["zone_name"], inp["as_of"], inp["horizon_h"], inp["probability_pct"], inp["rank"],
                                                      *(inp["onset"] or {}).values(), *(inp["peak"] or {}).values(),
                                                      *inp["exposure_counts"].values(), *inp["hospitals_named"], *inp["drivers"], inp["explanation"] or ""])))
    return nums


def briefing_prompt(p: ZonePayload, zone_name: str) -> dict:
    """Minimal status-conditioned prompt for the 2 to 3 sentence briefing.

    Same `status` derivation as briefing_input, but only the fields the output
    may use: causes collapse to one `reasons` list (no drivers/explanation/
    alert_text triple telling), times only where the rules allow them, exposure
    only when the zone has mapped facilities, and no rank/caveat boilerplate
    (labels are added server-side, never by the model).
    """
    status = _status(p)
    d: dict = {"zone_name": zone_name, "status": status, "severity": p.severity, "horizon_h": HORIZON_H}
    if p.probability is not None:
        d["probability_pct"] = round(p.probability * 100)
    if status == "episode_expected":
        if p.onset is not None:
            d["onset"] = clock(p.onset.likely)
        if p.peak is not None:
            d["peak"] = clock(p.peak.likely)
    elif status == "already_above_normal_high_water":
        if p.peak is not None:
            d["peak"] = clock(p.peak.likely)
    # episode_possible / no_episode_expected: no times (the rules forbid them).
    reasons = [r.phrase for r in p.reasons][:3] or list(p.drivers_text[:3])
    if reasons:
        d["reasons"] = reasons
    if p.exposure:
        counts = dict(Counter(e.type for e in p.exposure))
        if counts:
            d["exposure_counts"] = counts
        named = [e.name for e in p.exposure if e.type == "hospital"][:2]
        if named:
            d["hospitals"] = named
    return d


def prompt_allowed_numbers(inp: dict) -> set[str]:
    """Grounding set matching briefing_prompt: every number the model may print."""
    bits = [inp.get("zone_name"), inp.get("probability_pct"), inp.get("horizon_h")]
    for k in ("onset", "peak"):
        if inp.get(k) is not None:
            bits.append(inp[k])
    for r in inp.get("reasons") or []:
        bits.append(r)
    for v in (inp.get("exposure_counts") or {}).values():
        bits.append(v)
    for h in inp.get("hospitals") or []:
        bits.append(h)
    return set(NUM.findall(" ".join(str(x) for x in bits if x is not None)))


def grounded_prompt(text: str, inp: dict) -> str:
    """Raise ValueError if the text contains a number not present in its trimmed prompt."""
    bad = [n for n in NUM.findall(text) if n not in prompt_allowed_numbers(inp)]
    if bad:
        raise ValueError(f"briefing invented numbers {bad}: {text!r}")
    return text


def grounded(text: str, inp: dict) -> str:
    """Raise ValueError if the text contains a number not present in its input; return the text otherwise."""
    bad = [n for n in NUM.findall(text) if n not in allowed_numbers(inp)]
    if bad:
        raise ValueError(f"briefing invented numbers {bad}: {text!r}")
    return text
