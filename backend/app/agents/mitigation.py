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
NEAREST = {"shelter": 2, "hospital": 1, "fire_station": 1, "police": 1}

# Short on purpose: people read this under stress, often on a phone. One action per line.
EMERGENCY = {"name": "Emergency", "phone": "911"}
STATE = [
    {"name": "Florida emergency line", "phone": "1-800-342-3557", "url": "https://www.floridadisaster.org"},
    {"name": "Red Cross shelters", "phone": "1-800-733-2767", "url": "https://www.redcross.org/get-help/disaster-relief-and-recovery-services/find-an-open-shelter.html"},
    {"name": "FEMA aid (after)", "phone": "1-800-621-3362", "url": "https://www.disasterassistance.gov"},
]
CONTACTS = {  # open shelters, evacuation buses, special-needs and pet-friendly shelters
    "Miami-Dade": {"name": "Miami-Dade 311", "phone": "311 or 305-468-5900", "url": "https://www.miamidade.gov/global/emergency/hurricane/home.page"},
    "Broward": {"name": "Broward hotline", "phone": "311 or 954-831-4000", "url": "https://www.broward.org/Hurricane"},
}

ALWAYS = ["Never walk or drive through floodwater."]
STEPS = {
    "unknown": ["Risk unknown, not low: no sensor nearby.", "Follow official warnings.", "Pack a go-bag: meds, papers, charger, water."],
    "low": ["No flooding expected. Get ready anyway.", "Charge your phone.", "Bag your documents."],
    "moderate": ["Move valuables up high.", "Park on higher ground.", "Plan your way out.", "Pack a go-bag."],
    "high": ["Be ready to leave early.", "Go up a floor, never into a closed attic.", "Power off at the main, only if dry.",
             "Check which shelters are open."],
}
STEPS["severe"] = ["Told to evacuate? Go now.", *STEPS["high"]]


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
    return f"Water may rise from {p.onset.likely.strftime('%b %d, %H:%M')}. Be ready before." if p.onset else None


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
        "shelter_note": "Shelters are schools and community centres. Not all open: call first.",
        "distance_note": "Straight-line distance.",
        "is_simulated": is_simulated,
    }


def advise(p: ZonePayload, zone: dict, facs: list[dict] | None = None) -> dict:
    """Replay: advice from the flood model's forecast for one place at one tick. `zone` is the snapshot zone row."""
    level = "unknown" if p.probability is None or p.severity is None else p.severity
    return _advice(zone, level, [s for s in [_when(p)] if s] + STEPS[level], p.is_simulated, facs)


# Live: no model forecast exists (no live gauge feed), so advice follows the official NWS level for the place's county.
# context.LEVELS: 0 none, 1 advisory or statement, 2 watch, 3 warning, 4 most serious warning; None = alert feed unavailable.
LIVE_STEPS = {
    None: ["Warning feed is down. That does not mean no danger.", "Check weather.gov or local news."],
    0: ["No official warnings here. Prepare now."] + STEPS["low"][1:],
    1: ["Advisory: minor flooding possible."] + STEPS["moderate"],
    2: ["Watch: flooding possible. Stay ready."] + STEPS["moderate"],
    3: ["Warning: flooding now or very soon."] + STEPS["high"],
    4: ["Most serious warning in effect."] + STEPS["severe"],
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
        "steps": list(LIVE_STEPS[lv]) + ALWAYS,  # outside our places: no county number, the contacts list says 911 first
        "contacts": contacts,
        "nearest": nearest(lat, lon, facs) if facs else {k: [] for k in NEAREST},
        "nearest_failed": facs is None,
        "shelter_note": "Shelters are schools and community centres. Not all open: call first.",
        "distance_note": "Straight-line distance.",
        "is_simulated": False,
        "official": {"level": lv, "label": "unknown (alert feed unavailable)" if lv is None else LEVELS[lv],
                     "active": [a["event"] for a in alerts or []]},
        "point": {"lat": lat, "lon": lon},
    }
