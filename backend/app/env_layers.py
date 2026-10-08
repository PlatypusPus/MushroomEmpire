"""Live environmental map layers: NWS alert polygons, NHC cyclone cones/tracks, RainViewer radar frames, Open-Meteo marine/AQI/wind.

Same honesty contract as `context.py`: everything here is LIVE overlay data, never part of the historical replay and never fed into the
flood model. All fetched text is untrusted: only structured fields are used, strings are cleaned and length-capped.

Sources (all keyless, checked reachable 2026-10-09): api.weather.gov alerts (GeoJSON, geometry KEPT here unlike context.py),
NHC CurrentStorms.json + per-storm forecast cone/track KMZ, api.rainviewer.com radar frame list, Open-Meteo marine / air-quality / forecast.
"""
import asyncio
import io
import time
import zipfile
from datetime import UTC, datetime
from typing import Any

import httpx
from defusedxml import ElementTree as ET

from app.context import (
    COUNTY_SAME,
    EVENT_LEVEL,
    REGION,
    UA,
    clean,
    parse_storms,
)

KML_NS = "{http://www.opengis.net/kml/2.2}"  # legacy constant; parsing below is namespace-agnostic (NHC uses kml/2.1)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _descendants(el: Any, *names: str) -> Any:
    for child in el.iter():
        if _local(child.tag) in names:
            yield child

URL = {
    "alerts": "https://api.weather.gov/alerts/active?area=FL",
    "storms": "https://www.nhc.noaa.gov/CurrentStorms.json",
    "radar": "https://api.rainviewer.com/public/weather-maps.json",
    "marine": f"https://marine-api.open-meteo.com/v1/marine?latitude={REGION['lat']}&longitude={REGION['lon']}"
              "&hourly=wave_height,wave_period&forecast_days=2&timezone=GMT",
    "aqi": f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={REGION['lat']}&longitude={REGION['lon']}"
           "&hourly=us_aqi,pm2_5,ozone&forecast_days=2&timezone=GMT",
    # 4x4 wind grid over Miami-Dade + Broward + nearby water (Open-Meteo answers one row per coordinate, in lat-major order)
    "wind": ("https://api.open-meteo.com/v1/forecast?latitude=25.0,25.0,25.0,25.0,25.5,25.5,25.5,25.5,26.0,26.0,26.0,26.0,26.5,26.5,26.5,26.5"
             "&longitude=-81.0,-80.6,-80.2,-79.8,-81.0,-80.6,-80.2,-79.8,-81.0,-80.6,-80.2,-79.8,-81.0,-80.6,-80.2,-79.8"
             "&hourly=wind_speed_10m,wind_direction_10m&forecast_days=1&timezone=GMT"),
}
WIND_LATS = [25.0, 25.5, 26.0, 26.5]
WIND_LONS = [-81.0, -80.6, -80.2, -79.8]
TTL = {"alerts": 120, "storms": 600, "radar": 300, "marine": 1800, "aqi": 1800, "wind": 1800, "cone": 1800}
STALE_FACTOR = 5
MAX_ALERT_COORDS = 4000  # per polygon ring: NWS polygons are small; truncate absurd ones
MAX_CONE_STORMS = 5  # KMZ fetches per refresh, nearest Atlantic storms first
CONE_MAX_KM = 2500  # skip KMZ work for storms too far to matter on this map

_cache: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()


def _t(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


# ------------------------------------------------------------------ parsing (pure functions, tested)
def parse_alerts_geo(data: dict, now: datetime | None = None) -> dict:
    """NWS active flood/tropical alerts WITH geometry -> GeoJSON FeatureCollection (county-tagged, level-coded)."""
    now = now or datetime.now(UTC)
    feats = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        ev = clean(p.get("event"), 60)
        level = EVENT_LEVEL.get(ev.lower())
        if level is None or p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        end = _t(p.get("ends")) or _t(p.get("expires"))
        if end and (end if end.tzinfo else end.replace(tzinfo=UTC)) < now:
            continue
        g = f.get("geometry")
        if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        same = (p.get("geocode") or {}).get("SAME") or []
        counties = [c for c, code in COUNTY_SAME.items() if code in same]
        feats.append({"type": "Feature", "geometry": _truncate(g),
                      "properties": {"event": ev, "level": level, "counties": counties,
                                     "headline": clean(p.get("headline"), 200), "ends": clean(p.get("ends") or p.get("expires"), 40)}})
    feats.sort(key=lambda a: -a["properties"]["level"])
    return {"type": "FeatureCollection", "features": feats}


def _truncate(g: dict) -> dict:
    if g["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [ring[:MAX_ALERT_COORDS] for ring in g["coordinates"]]}
    return {"type": "MultiPolygon", "coordinates": [[ring[:MAX_ALERT_COORDS] for ring in poly] for poly in g["coordinates"]]}


def parse_kmz(raw: bytes) -> dict:
    """NHC forecast cone/track KMZ -> {"cone": [[lat, lon], ...] | None, "track": [[lat, lon], ...] | None}."""
    out: dict[str, Any] = {"cone": None, "track": None}
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
        if name is None:
            return out
        root = ET.fromstring(z.read(name))
    except Exception:
        return out
    polys, lines = [], []
    for pm in _descendants(root, "Placemark"):
        for poly in _descendants(pm, "Polygon"):
            outer = next(_descendants(poly, "outerBoundaryIs"), poly)
            coord = next((c for c in _descendants(outer, "coordinates") if c.text and c.text.strip()), None)
            if coord is not None:
                polys.append(_kml_coords(coord.text or ""))
        for ls in _descendants(pm, "LineString"):
            coord = next((c for c in _descendants(ls, "coordinates") if c.text and c.text.strip()), None)
            if coord is not None:
                lines.append(_kml_coords(coord.text or ""))
    if polys:
        out["cone"] = max(polys, key=len)
    if lines:
        out["track"] = max(lines, key=len)
    return out


def _kml_coords(text: str) -> list[list[float]]:
    pts = []
    for tup in text.split():
        parts = tup.split(",")
        if len(parts) >= 2:
            try:
                pts.append([float(parts[1]), float(parts[0])])  # KML is lon,lat -> Leaflet wants lat,lon
            except ValueError:
                continue
    return pts


def parse_radar(data: dict) -> dict:
    """RainViewer frame list -> {host, color, options, frames:[{time, path}]} (past + nowcast, oldest first)."""
    frames = [{"time": f.get("time"), "path": f.get("path")}
              for key in ("past", "nowcast") for f in (data.get("radar", {}).get(key) or []) if f.get("path")]
    return {"host": data.get("host", "https://tilecache.rainviewer.com"), "color": 4, "options": "1_1", "frames": frames}


def _hour_index(times: list[str], now: datetime) -> int:
    top = now.replace(minute=0, second=0, microsecond=0)
    for i, t in enumerate(times):
        tt = _t(t)
        if tt and tt.replace(tzinfo=UTC) >= top:
            return i
    return max(0, len(times) - 1)


def parse_marine(data: dict, now: datetime | None = None) -> dict | None:
    h, now = data.get("hourly", {}), now or datetime.now(UTC)
    times, wh = h.get("time", []), h.get("wave_height", [])
    if not times or not wh:
        return None
    i = _hour_index(times, now)
    nxt = [v for v in wh[i:i + 24] if v is not None]
    wp = h.get("wave_period", [])
    return {"wave_height_now_m": wh[i] if i < len(wh) else None,
            "wave_height_next_24h_max_m": round(max(nxt), 1) if nxt else None,
            "wave_period_now_s": wp[i] if i < len(wp) else None}


def parse_aqi(data: dict, now: datetime | None = None) -> dict | None:
    h, now = data.get("hourly", {}), now or datetime.now(UTC)
    times = h.get("time", [])
    if not times:
        return None
    i = _hour_index(times, now)
    get = lambda k: (h.get(k, []) + [None] * (i + 1))[i]
    return {"us_aqi_now": get("us_aqi"), "pm2_5_now": get("pm2_5"), "ozone_now": get("ozone")}


def parse_wind_grid(rows: list[dict], now: datetime | None = None) -> dict | None:
    """16 Open-Meteo location rows (lat-major order) -> {ref_time, lats, lons, speed_kmh[4][4], dir_deg[4][4]}."""
    now = now or datetime.now(UTC)
    if len(rows) < 16:
        return None
    ref, speed, direction = None, [[0.0] * 4 for _ in range(4)], [[0] * 4 for _ in range(4)]
    for n, row in enumerate(rows[:16]):
        h = row.get("hourly", {})
        times = h.get("time", [])
        if not times:
            return None
        i = _hour_index(times, now)
        if ref is None:
            ref = times[i] if i < len(times) else None
        sp = h.get("wind_speed_10m", [])
        dr = h.get("wind_direction_10m", [])
        r, c = divmod(n, 4)
        speed[r][c] = sp[i] if i < len(sp) and sp[i] is not None else 0.0
        direction[r][c] = dr[i] if i < len(dr) and dr[i] is not None else 0
    return {"ref_time": ref, "lats": WIND_LATS, "lons": WIND_LONS, "speed_kmh": speed, "dir_deg": direction}


# ------------------------------------------------------------------ fetching with cache and staleness
async def _fetch(client: httpx.AsyncClient, name: str) -> Any:
    r = await client.get(URL[name], headers=UA, timeout=20, follow_redirects=True)
    r.raise_for_status()
    return r.json()


PARSE = {"alerts": parse_alerts_geo, "radar": parse_radar, "marine": parse_marine, "aqi": parse_aqi}


async def _source(client: httpx.AsyncClient, name: str, force: bool = False) -> dict:
    c = _cache.get(name)
    if c and not force and time.time() - c["at"] < TTL[name]:
        return c
    try:
        data = await _fetch(client, name)
        parsed = PARSE[name](data) if name in PARSE else data
        _cache[name] = {"data": parsed, "at": time.time(), "ok": True, "error": None}
    except Exception as e:
        _cache[name] = {**(c or {"data": None, "at": None}), "ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    return _cache[name]


def _status(c: dict, name: str) -> dict:
    age = None if c.get("at") is None else int(time.time() - c["at"])
    usable = c.get("data") is not None and age is not None and age <= TTL[name] * STALE_FACTOR
    return {"ok": bool(c.get("ok")), "usable": usable, "age_s": age, "error": c.get("error")}


async def _cone_for(client: httpx.AsyncClient, kmz_url: str) -> dict:
    """One storm's cone+track KMZ -> parsed GeoJSON-ish dict; never raises (returns nulls on any failure)."""
    try:
        r = await client.get(kmz_url, headers=UA, timeout=20, follow_redirects=True)
        r.raise_for_status()
        import functools

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(parse_kmz, r.content))
    except Exception:
        return {"cone": None, "track": None}


async def get_env(force: bool = False) -> dict:
    """Everything the environmental map overlays need, in one payload. Overlay-only: never model input."""
    async with _lock, httpx.AsyncClient() as client:
        res = dict(zip([n for n in URL if n != "wind"],
                       await asyncio.gather(*[_source(client, n, force) for n in URL if n != "wind"])))
        wind_rows = await _source(client, "wind", force)
    st = {n: _status(res[n], n) for n in res}
    st["wind"] = _status(wind_rows, "wind")
    use = lambda n: res[n]["data"] if st[n]["usable"] else None

    cyclones: list[dict] = []
    cone_ok, cone_err = True, None
    raw_storms = (res.get("storms") or {}).get("data") or {}
    try:
        parsed = parse_storms(raw_storms)
    except Exception:
        parsed = {"storms": []}
    near = [s for s in parsed.get("storms", []) if (s.get("distance_km") or 999999) <= CONE_MAX_KM][:MAX_CONE_STORMS]
    # NOTE: parse_storms drops the KMZ links, so re-read them from the raw record matched by storm id.
    by_id = {str(s.get("id", "")).lower(): s for s in raw_storms.get("activeStorms", [])}
    if near:
        async with httpx.AsyncClient() as client:
            jobs = []
            for s in near:
                raw = by_id.get(str(s["id"]).lower(), {})
                cone_url = (raw.get("trackCone") or {}).get("kmzFile")
                track_url = (raw.get("forecastTrack") or {}).get("kmzFile")
                jobs.append((s, cone_url, track_url))

            async def _both(u: str | None, t: str | None) -> tuple[dict, dict]:
                cone_r = await _cone_for(client, u) if u else {"cone": None, "track": None}
                track_r = await _cone_for(client, t) if t and t != u else {"cone": None, "track": None}
                return cone_r, track_r

            results = await asyncio.gather(*[_both(u, t) for _, u, t in jobs])
        for (s, _, _), (cone_r, track_r) in zip(jobs, results):
            cone, track = cone_r.get("cone"), track_r.get("track") or cone_r.get("track")
            if cone is None and track is None:
                cone_ok = False
            cyclones.append({**s, "cone": cone, "track": track})
    else:
        cyclones = [{**s, "cone": None, "track": None} for s in parsed.get("storms", [])]
    if near and not any(c.get("cone") or c.get("track") for c in cyclones):
        cone_err = "cone/track KMZ unavailable"
    storms_usable = bool(st.get("storms", {}).get("usable"))
    st["cone"] = {"ok": cone_ok and st.get("storms", {}).get("ok", False),
                  "usable": storms_usable and cone_err is None,
                  "age_s": st.get("storms", {}).get("age_s"), "error": cone_err}

    out = {"live": True, "note": "Live overlay data. Not part of the historical replay and not fed into the flood model.",
           "fetched_at": datetime.now(UTC).isoformat(),
           "alerts_geo": use("alerts") or {"type": "FeatureCollection", "features": []},
           "cyclones": cyclones if st.get("storms", {}).get("usable") else [],
           "radar": use("radar") or {"host": "https://tilecache.rainviewer.com", "color": 4, "options": "1_1", "frames": []},
           "marine": use("marine"), "aqi": use("aqi"),
           "wind": parse_wind_grid(wind_rows["data"], datetime.now(UTC)) if wind_rows["data"] and st["wind"]["usable"] else None,
           "sources": st, "partial": [n for n in st if n != "cone" and not st[n].get("usable")] + (["cone"] if cone_err else [])}
    return out
