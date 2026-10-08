"""Briefing agent: alert text in the brief's format, from the structured payload only.

Template today; an LLM can replace `render` later, but `check_numbers` still gates its output.
"""

import re
from datetime import datetime

from app.schemas import RiskOutput

NUM = re.compile(r"\d+(?:[.:]\d+)?")
# ponytail: "Water", not "Flood": labels come from stage-exceedance episodes (ROOT_CONTEXT 12.1)
NOUN = "Water"


def clock(t: datetime) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def render(zone_name: str, risk: RiskOutput, drivers: list[str]) -> str:
    head = f"{risk.severity.capitalize()} {NOUN} Risk, {zone_name}."
    if not risk.onset:
        return f"{head} No high-water episode expected in the next {risk.horizon_h} h."
    return f"{head} Onset {clock(risk.onset.likely)}, peak {clock(risk.peak.likely)}. Drivers: {' + '.join(drivers)}"


def check_numbers(text: str, zone_name: str, risk: RiskOutput, drivers: list[str]) -> str:
    """Hard error if the text holds any number not present in its input payload."""
    allowed = [zone_name, str(risk.horizon_h), *drivers]
    for w in (risk.onset, risk.peak):
        if w:
            allowed += [clock(w.earliest), clock(w.likely), clock(w.latest)]
    ok = set(NUM.findall(" ".join(allowed)))
    bad = [n for n in NUM.findall(text) if n not in ok]
    if bad:
        raise ValueError(f"briefing invented numbers {bad}: {text!r}")
    return text


def brief(zone_name: str, risk: RiskOutput, drivers: list[str]) -> str:
    return check_numbers(render(zone_name, risk, drivers), zone_name, risk, drivers)
