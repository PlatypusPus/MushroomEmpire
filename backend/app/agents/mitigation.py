"""Mitigation agent: for one place, what people can do now, who to call, and the nearest potential shelters and services.

Deterministic on purpose (no LLM): safety advice must not be paraphrased into something wrong. It follows the project rules:
* recommends, never orders; never says a place or shelter is safe;
* shelters are POTENTIAL only (OSM schools and community centres). Counties open shelters per storm, so every list says
  "call to check it is open" and points at the county line;
* unknown risk (no usable gauge) is treated as unknown, never low;
* distances are straight-line from the place's centre, not driving routes.
Contacts were checked against county and state sources (Oct 2026); see CONTACTS.
"""
import json
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from shapely.geometry import shape

from app.schemas import ZonePayload

DATA = Path(__file__).with_name("facilities.json")  # built from data/processed/sf_facilities.csv, named places only
NEAREST = {"shelter": 3, "hospital": 1, "fire_station": 1, "police": 1}

EMERGENCY = {"name": "Emergency (life in danger, trapped by water)", "phone": "911"}
STATE = [
    {"name": "Florida Emergency Information Line (active during disasters)", "phone": "1-800-342-3557", "url": "https://www.floridadisaster.org"},
    {"name": "American Red Cross: find an open shelter", "phone": "1-800-733-2767", "url": "https://www.redcross.org/get-help/disaster-relief-and-recovery-services/find-an-open-shelter.html"},
    {"name": "FEMA disaster assistance (after the flood)", "phone": "1-800-621-3362", "url": "https://www.disasterassistance.gov"},
]
CONTACTS = {
    "Miami-Dade": {"name": "Miami-Dade 311 Answer Center: open shelters, evacuation buses, special-needs help", "phone": "311 or 305-468-5900",
                   "url": "https://www.miamidade.gov/global/emergency/hurricane/home.page"},
    "Broward": {"name": "Broward County Emergency Hotline: open shelters, special-needs and pet-friendly shelters", "phone": "311 or 954-831-4000",
                "url": "https://www.broward.org/Hurricane"},
}

ALWAYS = [
    "Never walk or drive through flood water. Six inches of moving water can knock you down and a foot can carry a car away.",
    "If your county orders an evacuation for your area, leave when told.",
]
STEPS = {
    "unknown": [
        "We cannot forecast this place: there is no working water sensor nearby. Treat the risk as unknown, not low.",
        "Follow National Weather Service warnings and your county's instructions.",
        "Have a go-bag ready: medicines, documents in a waterproof bag, phone charger, water and food for 3 days.",
    ],
    "low": [
        "Flooding is not expected here now. Use the time to prepare.",
        "Clear gutters and storm drains near your home if it is safe to do so.",
        "Keep your phone charged and documents in a waterproof bag.",
    ],
    "moderate": [
        "Move valuables, documents and electrical items off the floor or upstairs.",
        "Park your car on higher ground, away from low streets and canals.",
        "Plan how you would get to higher ground, and check on neighbours who may need help.",
        "Have a go-bag ready: medicines, documents, phone charger, water and food for 3 days.",
    ],
    "high": [
        "Be ready to leave before the water arrives. Low streets may flood first and cut off your route.",
        "Move people, pets and valuables to a higher floor. Do not shelter in an attic you cannot climb out of.",
        "If water is about to enter your home, switch off electricity at the main switch, but only if you can do it dry.",
        "Check with your county which shelters are open before you go.",
    ],
}
STEPS["severe"] = ["This is the highest risk level we show. If you are told to evacuate, do not wait.", *STEPS["high"]]


@lru_cache(maxsize=1)
def facilities() -> list[dict]:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    return [dict(zip(d["columns"], r)) for r in d["rows"]]


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance."""
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def nearest(lat: float, lon: float, facs: list[dict]) -> dict[str, list[dict]]:
    # ponytail: linear scan over ~2k points per request, a KD-tree only if this ever covers a whole state
    out = {}
    for kind, n in NEAREST.items():
        ds = sorted(((km(lat, lon, f["lat"], f["lon"]), f) for f in facs if f["kind"] == kind), key=lambda x: x[0])[:n]
        out[kind] = [{"name": f["name"], "km": round(d, 1), "lat": f["lat"], "lon": f["lon"]} for d, f in ds]
    return out


def _when(p: ZonePayload) -> str | None:
    if not p.onset:
        return None
    t = p.onset.likely.strftime("%H:%M")
    return f"Water may start rising around {t}{' on ' + p.onset.likely.strftime('%b %d') if p.peak and p.peak.likely.date() != p.onset.likely.date() else ''}. Finish getting ready before then."


def _advice(zone: dict, level: str, steps: list[str], is_simulated: bool, facs: list[dict] | None) -> dict:
    c = shape(zone["geometry"]).representative_point()  # inside the polygon even for odd shapes, unlike the centroid
    county = CONTACTS.get(zone.get("county") or "")
    return {
        "zone_id": zone["id"],
        "name": zone["name"],
        "county": zone.get("county"),
        "level": level,
        "steps": steps + ALWAYS,
        "contacts": [EMERGENCY, *([county] if county else []), *STATE],
        "nearest": nearest(c.y, c.x, facs if facs is not None else facilities()),
        "shelter_note": "These are schools and community centres that are often used as shelters. Not all of them open in every storm. "
                        "Call your county line before you go to check which shelters are open.",
        "distance_note": "Straight-line distance from the centre of the place, not a driving route.",
        "is_simulated": is_simulated,
    }


def advise(p: ZonePayload, zone: dict, facs: list[dict] | None = None) -> dict:
    """Replay: advice from the flood model's forecast for one place at one tick. `zone` is the snapshot zone row."""
    level = "unknown" if p.probability is None or p.severity is None else p.severity
    return _advice(zone, level, [s for s in [_when(p)] if s] + STEPS[level], p.is_simulated, facs)


# Live: no model forecast exists (no live gauge feed), so advice follows the official NWS level for the place's county.
# context.LEVELS: 0 none, 1 advisory or statement, 2 watch, 3 warning, 4 most serious warning; None = alert feed unavailable.
LIVE_STEPS = {
    None: ["We cannot reach the official warning feed right now. That does not mean there is no danger.",
           "Check weather.gov or local news, and call your county line for instructions."],
    0: ["There is no official flood watch or warning for this county right now. Use the time to prepare."] + STEPS["low"][1:],
    1: ["An official advisory or statement is in effect. Minor flooding of low roads is possible."] + STEPS["moderate"],
    2: ["An official watch is in effect: flooding is possible. Be ready to act quickly if it becomes a warning."] + STEPS["moderate"],
    3: ["An official warning is in effect: flooding is happening or about to happen."] + STEPS["high"],
    4: ["The most serious official warnings are in effect here, such as a hurricane or storm surge warning."] + STEPS["severe"],
}
LIVE_LEVEL = {None: "unknown", 0: "low", 1: "moderate", 2: "moderate", 3: "high", 4: "severe"}


def advise_live(zone: dict, county_ctx: dict | None, facs: list[dict] | None = None) -> dict:
    """Live: `county_ctx` is context.get_context()["counties"][county] ({level, label, drivers}); missing = feed unavailable."""
    lv = (county_ctx or {}).get("level")
    out = _advice(zone, LIVE_LEVEL[lv], list(LIVE_STEPS[lv]), False, facs)
    out["official"] = {"level": lv, "label": (county_ctx or {}).get("label", "unknown (alert feed unavailable)"),
                       "active": (county_ctx or {}).get("drivers", [])}
    return out


# ------------------------------------------------------------------ anywhere (live): a clicked point outside the places we cover
OSM_KIND = {"hospital": "hospital", "fire_station": "fire_station", "police": "police", "school": "shelter", "community_centre": "shelter"}


def advise_point(lat: float, lon: float, where: dict | None, alerts: list[dict] | None, facs: list[dict] | None) -> dict:
    """Live advice for any US point from the official alerts AT that point (NWS ?point=), not our flood model.
    where: {"city", "state"} from NWS /points; alerts: [{"event", "level", "headline", "ends"}], None = feed unavailable;
    facs: nearby OSM facilities, None = lookup failed (said so, never an empty "no shelters")."""
    from app.context import LEVELS

    lv = None if alerts is None else max([a["level"] for a in alerts], default=0)
    state = (where or {}).get("state")
    contacts = [EMERGENCY, *[c for c in STATE if state == "FL" or "Florida" not in c["name"]]]  # the FL line only serves Florida
    return {
        "zone_id": None,
        "name": f"{where['city']}, {state}" if where else f"{lat:.3f}, {lon:.3f}",
        "county": None,
        "level": LIVE_LEVEL[lv],
        "steps": list(LIVE_STEPS[lv]) + ["This spot is outside the places we cover in detail, so we do not list its county's number. "
                                         "Call 911 in danger, and follow your county emergency management and local news."] + ALWAYS,
        "contacts": contacts,
        "nearest": nearest(lat, lon, facs) if facs else {k: [] for k in NEAREST},
        "nearest_failed": facs is None,
        "shelter_note": "These are schools and community centres that are often used as shelters. Not all of them open in every storm. "
                        "Check with local emergency management which shelters are open before you go.",
        "distance_note": "Straight-line distance from the point you clicked, not a driving route.",
        "is_simulated": False,
        "official": {"level": lv, "label": "unknown (alert feed unavailable)" if lv is None else LEVELS[lv],
                     "active": [a["event"] for a in alerts or []]},
        "point": {"lat": lat, "lon": lon},
    }
