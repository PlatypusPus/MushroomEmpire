"""Live hazard context: official alerts, active cyclones, a weather-model outlook, and one transparent "hazard context level".

This is NOT part of the flood model's probability. It is shown NEXT TO it (see `agreement`), because there is no historical archive of
alerts here to calibrate any uplift, and the replay events are historical. All fetched text is untrusted: only structured fields are
used, strings are cleaned and length-capped, and nothing from here is fed to an LLM except event names, counts and distances.

Sources (checked reachable 2026-10-08): NWS alerts API, NHC CurrentStorms.json and Atlantic RSS, Open-Meteo forecast.
Unknown is never "none": if the alert feed is unavailable or too old the level is None, not 0.
"""
import asyncio
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from defusedxml import ElementTree as ET

REGION = {"name": "South Florida (Miami-Dade + Broward)", "lat": 25.8, "lon": -80.2}
COUNTY_SAME = {"Miami-Dade": "012086", "Broward": "012011"}
UA = {"User-Agent": "coastguard-hackathon/0.1", "Accept": "application/geo+json, application/json, application/xml"}
URL = {
    "alerts": "https://api.weather.gov/alerts/active?area=FL",
    "storms": "https://www.nhc.noaa.gov/CurrentStorms.json",
    "bulletins": "https://www.nhc.noaa.gov/index-at.xml",
    "forecast": f"https://api.open-meteo.com/v1/forecast?latitude={REGION['lat']}&longitude={REGION['lon']}"
                "&hourly=precipitation,pressure_msl,wind_gusts_10m&forecast_days=3&timezone=GMT",
}
TTL = {"alerts": 120, "storms": 600, "bulletins": 600, "forecast": 900}  # seconds before a refetch
STALE_FACTOR = 5  # older than TTL x 5 = too old to trust (alerts: 10 minutes)
CACHE_FILE = Path(__file__).resolve().parents[1] / "cache" / "context_last.json"

LEVELS = {0: "none", 1: "advisory or statement", 2: "watch", 3: "warning", 4: "most serious warning"}  # 4: hurricane, storm surge, extreme wind warnings or a flash flood emergency
# NWS event name -> level. A heuristic ordering of official products, not a calibrated probability.
EVENT_LEVEL = {
    "coastal flood statement": 1, "flood statement": 1, "flood advisory": 1, "coastal flood advisory": 1, "tropical cyclone local statement": 1,
    "hurricane local statement": 1, "flood watch": 2, "coastal flood watch": 2, "flash flood watch": 2, "tropical storm watch": 2,
    "hurricane watch": 2, "storm surge watch": 2, "flood warning": 3, "coastal flood warning": 3, "flash flood warning": 3,
    "tropical storm warning": 3, "hurricane warning": 4, "storm surge warning": 4, "extreme wind warning": 4,
}
# cyclone proximity heuristic (unvalidated): thresholds in km from the region centre
NEAR_KM, APPROACH_KM, MONITOR_KM = 300, 800, 1500

_cache: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()


def clean(text: Any, limit: int = 140) -> str:
    """Untrusted text -> short single-line plain text: strip tags, control characters and extra whitespace."""
    t = re.sub(r"<[^>]*>", " ", str(text or ""))
    t = re.sub(r"[\x00-\x1f\x7f]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:limit]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _t(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


# ------------------------------------------------------------------ parsing (pure functions, tested on saved real responses)
def parse_alerts(data: dict, now: datetime | None = None) -> dict[str, list[dict]]:
    """-> {county: [alert, ...]} for flood/tropical products that are active now and apply to that county (SAME code)."""
    now = now or datetime.now(timezone.utc)
    out: dict[str, list[dict]] = {c: [] for c in COUNTY_SAME}
    for f in data.get("features", []):
        p = f.get("properties", {})
        ev = clean(p.get("event"), 60)
        level = EVENT_LEVEL.get(ev.lower())
        if level is None or p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        end = _t(p.get("ends")) or _t(p.get("expires"))
        if end and end < now:
            continue
        head = clean(p.get("headline"), 200)
        if ev.lower() == "flash flood warning" and "flash flood emergency" in head.lower():
            level = 4
        same = (p.get("geocode") or {}).get("SAME") or []
        for county, code in COUNTY_SAME.items():
            if code in same:
                out[county].append({"event": ev, "level": level, "severity": clean(p.get("severity"), 20), "certainty": clean(p.get("certainty"), 20),
                                    "effective": clean(p.get("effective"), 40), "ends": clean(p.get("ends") or p.get("expires"), 40), "headline": head})
    for v in out.values():
        v.sort(key=lambda a: -a["level"])
    return out


def parse_storms(data: dict) -> dict:
    """Atlantic cyclones with distance and heading relative to the region; other basins are only counted."""
    storms, other = [], 0
    for s in data.get("activeStorms", []):
        if not str(s.get("id", "")).lower().startswith("al"):
            other += 1
            continue
        try:
            lat, lon = float(s["latitudeNumeric"]), float(s["longitudeNumeric"])
        except (KeyError, TypeError, ValueError):
            continue
        d = haversine_km(lat, lon, REGION["lat"], REGION["lon"])
        brg = bearing_deg(lat, lon, REGION["lat"], REGION["lon"])
        mdir = s.get("movementDir")
        toward = mdir is not None and abs((float(mdir) - brg + 180) % 360 - 180) <= 60 and float(s.get("movementSpeed") or 0) > 0
        storms.append({"id": clean(s.get("id"), 12), "name": clean(s.get("name"), 30), "classification": clean(s.get("classification"), 4),
                       "intensity_kt": int(float(s["intensity"])) if str(s.get("intensity", "")).replace(".", "").isdigit() else None,
                       "pressure_mb": int(float(s["pressure"])) if str(s.get("pressure", "")).replace(".", "").isdigit() else None,
                       "lat": lat, "lon": lon, "distance_km": round(d), "heading_toward_region": bool(toward), "last_update": clean(s.get("lastUpdate"), 30)})
    storms.sort(key=lambda s: s["distance_km"])
    return {"storms": storms, "other_basin_count": other}


def cyclone_level(storms: list[dict]) -> tuple[int, str | None]:
    best, why = 0, None
    for s in storms:
        if s["classification"] not in ("TD", "TS", "HU", "STS", "PTC", "SS"):
            continue
        lv = 3 if s["distance_km"] <= NEAR_KM else 2 if s["distance_km"] <= APPROACH_KM and s["heading_toward_region"] else 1 if s["distance_km"] <= MONITOR_KM else 0
        if lv > best:
            best, why = lv, f"{s['classification']} {s['name']}, {s['distance_km']} km away" + (", heading toward the region" if s["heading_toward_region"] else "")
    return best, why


def parse_bulletins(xml_text: str, limit: int = 5) -> list[dict]:
    items = []
    for it in ET.fromstring(xml_text).iter("item"):
        link = clean(it.findtext("link"), 200)
        if not link.startswith("https://www.nhc.noaa.gov/"):  # official domain only
            continue
        items.append({"title": clean(it.findtext("title"), 120), "published": clean(it.findtext("pubDate"), 40), "link": link})
        if len(items) >= limit:
            break
    return items


def parse_forecast(data: dict, now: datetime | None = None) -> dict:
    h = data.get("hourly", {})
    now = now or datetime.now(timezone.utc)
    rows = [(datetime.fromisoformat(t).replace(tzinfo=timezone.utc), p, q, g) for t, p, q, g in zip(h.get("time", []), h.get("precipitation", []), h.get("pressure_msl", []), h.get("wind_gusts_10m", []))]
    fut = [r for r in rows if r[0] >= now.replace(minute=0, second=0, microsecond=0)]
    nxt = lambda n: fut[:n]  # noqa: E731
    vals = lambda i, n: [r[i] for r in nxt(n) if r[i] is not None]  # noqa: E731
    return {"source": "Open-Meteo weather model, not our flood model", "units": data.get("hourly_units", {}),
            "rain_next_24h_mm": round(sum(vals(1, 24)), 1), "rain_next_72h_mm": round(sum(vals(1, 72)), 1),
            "max_gust_next_48h_kmh": round(max(vals(3, 48), default=0)), "min_pressure_next_48h_hpa": round(min(vals(2, 48), default=0))}


# ------------------------------------------------------------------ the level and its agreement with the model
def hazard_level(alerts: dict | None, storms: dict | None) -> dict:
    """Overall and per-county level. alerts None = feed unavailable/too old -> level None (never 0)."""
    cy, cy_why = cyclone_level(storms["storms"]) if storms else (0, None)
    counties = {}
    for c in COUNTY_SAME:
        if alerts is None:
            counties[c] = {"level": None, "label": "unknown (alert feed unavailable)", "drivers": []}
            continue
        al = alerts.get(c, [])
        lv = max([a["level"] for a in al] + [cy])
        drivers = [f"{a['event']} ({c})" for a in al] + ([cy_why] if cy_why and cy >= max([a["level"] for a in al] + [0]) else [])
        counties[c] = {"level": lv, "label": LEVELS[lv], "drivers": drivers}
    levels = [v["level"] for v in counties.values()]
    top = None if any(x is None for x in levels) else max(levels)
    return {"level": top, "label": "unknown (alert feed unavailable)" if top is None else LEVELS[top], "counties": counties,
            "heuristic_note": "A simple rating from official warnings and how close a storm is. It is not a probability."}


def agreement(level: int | None, model_probability: float | None, alert_threshold: float) -> dict:
    """How the official level and the flood model relate for one zone. Shown side by side; never merged into one number."""
    if level is None:
        return {"code": "context_unavailable", "text": "We cannot get official warnings right now."}
    if model_probability is None:
        return {"code": "no_model_data", "text": "We have no data for this place." + (" An official watch or warning is active." if level >= 2 else "")}
    m = model_probability >= alert_threshold
    if m and level >= 3:
        return {"code": "agree_warning", "text": "Our flood forecast and an official warning both show a flood risk."}
    if m and level == 2:
        return {"code": "model_with_watch", "text": "Our forecast shows a risk and there is an official watch."}
    if m:
        return {"code": "model_only", "text": "Only our forecast shows a risk. There is no official watch or warning."}
    if level >= 3:
        return {"code": "official_only", "text": "There is an official warning here, but our forecast shows no risk. Check it yourself."}
    if level == 2:
        return {"code": "official_watch_only", "text": "There is an official watch here, but our forecast shows no risk."}
    return {"code": "none", "text": "Neither our forecast nor the officials show a risk."}


# ------------------------------------------------------------------ fetching with cache, staleness and an offline fallback
async def _fetch(client: httpx.AsyncClient, name: str) -> Any:
    r = await client.get(URL[name], headers=UA, timeout=20, follow_redirects=True)
    r.raise_for_status()
    return r.text if name == "bulletins" else r.json()


PARSE = {"alerts": parse_alerts, "storms": parse_storms, "bulletins": lambda t: parse_bulletins(t), "forecast": parse_forecast}


async def _source(client, name: str, force: bool = False) -> dict:
    c = _cache.get(name)
    if c and not force and time.time() - c["at"] < TTL[name]:
        return c
    try:
        parsed = PARSE[name](await _fetch(client, name))
        _cache[name] = {"data": parsed, "at": time.time(), "ok": True, "error": None}
    except Exception as e:  # network, HTTP, parse: keep the last good copy, flag it
        _cache[name] = {**(c or {"data": None, "at": None}), "ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return _cache[name]


def _status(c: dict, name: str) -> dict:
    age = None if c.get("at") is None else int(time.time() - c["at"])
    usable = c.get("data") is not None and age is not None and age <= TTL[name] * STALE_FACTOR
    return {"ok": bool(c.get("ok")), "usable": usable, "age_s": age, "error": c.get("error")}


async def get_context(force: bool = False) -> dict:
    async with _lock:
        async with httpx.AsyncClient() as client:
            res = dict(zip(URL, await asyncio.gather(*[_source(client, n, force) for n in URL])))
    st = {n: _status(res[n], n) for n in URL}
    use = lambda n: res[n]["data"] if st[n]["usable"] else None  # noqa: E731
    lvl = hazard_level(use("alerts"), use("storms"))
    out = {"live": True, "note": "Live data. Not part of the historical replay and not fed into the flood model.", "region": REGION["name"],
           "fetched_at": datetime.now(timezone.utc).isoformat(), "level": lvl["level"], "label": lvl["label"], "counties": lvl["counties"],
           "heuristic_note": lvl["heuristic_note"], "alerts": use("alerts"), "cyclones": (use("storms") or {}).get("storms", []),
           "other_basin_cyclones": (use("storms") or {}).get("other_basin_count"), "forecast": use("forecast"), "bulletins": use("bulletins") or [],
           "sources": st, "partial": [n for n in URL if not st[n]["usable"]]}
    if out["level"] is None and CACHE_FILE.exists():  # last recorded context, clearly marked old, never promoted to "live"
        try:
            last = json.loads(CACHE_FILE.read_text())
            out["last_recorded"] = {"at": last.get("fetched_at"), "level": last.get("level"), "label": last.get("label")}
        except (OSError, ValueError):
            pass
    if out["level"] is not None:
        try:
            CACHE_FILE.parent.mkdir(exist_ok=True)
            CACHE_FILE.write_text(json.dumps({k: out[k] for k in ("fetched_at", "level", "label", "counties")}, default=str))
        except OSError:
            pass
    return out
