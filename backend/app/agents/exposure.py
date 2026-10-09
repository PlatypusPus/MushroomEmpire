"""Exposure agent: what sits in a place. Facilities are lane A's OSM assets already joined to zones; roads and buildings come
from scripts/sf_exposure.py (place_exposure.json, shipped with the app).

Roads: the place's named major roads (OSM motorway to tertiary), with length inside the place and the share on low ground
(HAND <= 0.5 m, bridges excluded); a road is "potentially exposed" when at least a quarter of it is low-lying.
Buildings: one item per place carrying the footprint count (Microsoft footprints), "potentially exposed" when any sit on low
ground. Low-lying is indicative (30 m HAND, metre-level error on this flat coast); nothing here says a road or building floods.
"""
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from app.schemas import ExposureItem

STATUS = {"confirmed": "confirmed", "potential": "potentially_exposed"}
DATA = Path(__file__).with_name("place_exposure.json")
ROAD_LOW_SHARE = 0.25


@lru_cache(maxsize=1)
def places() -> dict:
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))["places"]
    except (OSError, ValueError, KeyError):
        return {}  # file not built: facilities only


def roads_and_buildings(zone_id: str) -> list[ExposureItem]:
    p = places().get(zone_id)
    if not p:
        return []
    out = [ExposureItem(type="road", name=r["name"], status="potentially_exposed" if r["low_share"] >= ROAD_LOW_SHARE else "confirmed",
                        detail=f"{r['km']} km here, {round(r['low_share'] * 100)}% on low ground")
           for r in p["roads"]]
    if p.get("buildings"):
        out.append(ExposureItem(type="building", name="Buildings", count=p["buildings"],
                                status="potentially_exposed" if p["buildings_low"] else "confirmed",
                                detail=f"{p['buildings']:,} footprints, {p['buildings_low']:,} on low ground"))
    return out


def exposure(zone_id: str, assets: list[dict]) -> list[ExposureItem]:
    facilities = [ExposureItem(type=a["kind"], name=a["name"], status=STATUS[a["confidence"]]) for a in assets if a["zone_id"] == zone_id]
    return facilities + roads_and_buildings(zone_id)


def counts(items: list[ExposureItem]) -> dict[str, int]:
    """How many of each type: a buildings item counts as its footprints, not as one."""
    c: Counter = Counter()
    for e in items:
        c[e.type] += e.count
    return dict(c)
