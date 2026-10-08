"""Live lookups for one clicked point anywhere in the US (Live dashboard only, never model input):
place name (NWS /points), official alerts at the point (NWS /alerts/active?point=) and nearby facilities (OSM Overpass).
Each source fails on its own: a failed lookup returns None, which the advice states, never as "no alerts" or "no shelters"."""
import asyncio
import logging
import time

import httpx

from app.agents.mitigation import OSM_KIND
from app.context import EVENT_LEVEL, UA, clean

log = logging.getLogger("coastguard.live_point")
NWS = "https://api.weather.gov"
OVERPASS = "https://overpass-api.de/api/interpreter"
RADIUS_M = 15000
TTL = {"where": 7 * 86400, "alerts": 120, "facs": 86400}
_cache: dict[tuple, tuple[float, object]] = {}  # ponytail: unbounded in-memory dict, LRU it if many people click around


def _key(kind: str, lat: float, lon: float) -> tuple:
    # alerts and place name are exact enough at ~1 km; facilities at ~1 km too (distances are recomputed from the true point)
    return kind, round(lat, 2), round(lon, 2)


async def _cached(kind: str, lat: float, lon: float, fetch):
    k = _key(kind, lat, lon)
    hit = _cache.get(k)
    if hit and time.monotonic() - hit[0] < TTL[kind]:
        return hit[1]
    try:
        val = await fetch()
    except Exception as e:  # network, HTTP or parse error: this source is unavailable, the others still answer
        log.info("%s lookup failed at %.3f,%.3f: %s", kind, lat, lon, type(e).__name__)
        return None
    _cache[k] = (time.monotonic(), val)
    return val


async def lookup(lat: float, lon: float) -> tuple[dict | None, list[dict] | None, list[dict] | None]:
    async with httpx.AsyncClient(timeout=25, headers=UA) as c:
        async def where():
            r = await c.get(f"{NWS}/points/{lat:.4f},{lon:.4f}")
            r.raise_for_status()
            p = r.json()["properties"]["relativeLocation"]["properties"]
            return {"city": clean(p["city"], 60), "state": clean(p["state"], 4)}

        async def alerts():
            r = await c.get(f"{NWS}/alerts/active", params={"point": f"{lat:.4f},{lon:.4f}"})
            r.raise_for_status()
            out = []
            for f in r.json()["features"]:
                p = f["properties"]
                lv = EVENT_LEVEL.get((p.get("event") or "").lower())
                if lv is None or p.get("status") != "Actual" or p.get("messageType") == "Cancel":
                    continue  # same filter as the South Florida context: flood and tropical products only
                out.append({"event": clean(p["event"], 60), "level": lv, "headline": clean(p.get("headline"), 200), "ends": p.get("ends")})
            return sorted({a["event"]: a for a in out}.values(), key=lambda a: -a["level"])  # one row per product

        async def facs():
            q = (f'[out:json][timeout:20];nwr["amenity"~"^(hospital|fire_station|police|community_centre|school)$"]["name"]'
                 f'(around:{RADIUS_M},{lat:.4f},{lon:.4f});out tags center 400;')
            r = await c.post(OVERPASS, data={"data": q})
            r.raise_for_status()
            out = []
            for e in r.json()["elements"]:
                pt = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
                if pt["lat"] is None:
                    continue
                out.append({"kind": OSM_KIND[e["tags"]["amenity"]], "name": clean(e["tags"]["name"], 120), "lat": pt["lat"], "lon": pt["lon"]})
            return out

        return await asyncio.gather(_cached("where", lat, lon, where), _cached("alerts", lat, lon, alerts), _cached("facs", lat, lon, facs))
