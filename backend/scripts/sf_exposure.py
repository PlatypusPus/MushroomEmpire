"""Roads and buildings per place, for the Exposure agent. Writes backend/app/agents/place_exposure.json (shipped with the app).

Run from backend/: uv run python -m scripts.sf_exposure
Inputs (data/, git-ignored): processed/sf_places.geojson, processed/sf_roads.geojson (OSM major roads, scripts/sf_osm.py),
raw/static/hand_mosaic.tif (GLO-30 HAND), raw/buildings/Florida.geojson.zip (Microsoft US building footprints v2, ODbL;
fetched by scripts/fetch_all.py; if missing, buildings are skipped).

"Low-lying" = HAND (height above the nearest drainage) at or below 0.5 m, the same cut sf_osm.py uses. HAND is ~30 m
resolution with metre-level error on this flat coast, so the low-lying shares are indicative, not surveyed. Bridges never count
as low-lying. Building low-lying = footprint centre at or below the cut. Counts only: nothing here says a road or building floods.
"""
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from shapely import STRtree
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[2] / "data"
OUT = Path(__file__).resolve().parents[1] / "app" / "agents" / "place_exposure.json"
LOW_HAND_M = 0.5
CRS_FT = 2236  # NAD83 Florida East, US feet: lengths
FT_TO_KM = 0.0003048
TOP_ROADS = 25


def hand_low(src, xy: np.ndarray) -> np.ndarray:
    """True where HAND at (lon, lat) is at or below the cut; nodata counts as not low."""
    v = np.array([s[0] for s in src.sample(xy)], dtype=float)
    return (v <= LOW_HAND_M) & (v != src.nodata)


def roads(places: gpd.GeoDataFrame, src) -> dict:
    rd = gpd.read_file(ROOT / "processed/sf_roads.geojson")
    pieces = gpd.overlay(rd, places[["GEOID", "geometry"]], how="intersection", keep_geom_type=True)
    pieces["km"] = pieces.to_crs(CRS_FT).length * FT_TO_KM
    # sample every ~30 m along each clipped piece; bridges are never low-lying
    pts = pieces.geometry.segmentize(0.0003)
    low_km = []
    for geom, bridge, k in zip(pts, pieces["bridge"], pieces["km"]):
        if bridge or k == 0:
            low_km.append(0.0)
            continue
        xy = shapely.get_coordinates(geom)
        low_km.append(k * float(hand_low(src, xy).mean()) if len(xy) else 0.0)
    pieces["low_km"] = low_km
    pieces["name"] = pieces["name"].fillna("").str.strip()
    out = {}
    for gid, g in pieces.groupby("GEOID"):
        named = g[g["name"] != ""].groupby("name")[["km", "low_km"]].sum().sort_values("km", ascending=False)
        out[gid] = {
            "road_km": round(float(g["km"].sum()), 1),
            "road_low_km": round(float(g["low_km"].sum()), 1),
            "roads": [{"name": n, "km": round(float(r.km), 1), "low_share": round(float(r.low_km / r.km), 2) if r.km else 0.0}
                      for n, r in named.head(TOP_ROADS).iterrows()],
            "named_roads": int(len(named)),
        }
    return out


def buildings(places: gpd.GeoDataFrame, src) -> dict:
    zpath = ROOT / "raw/buildings/Florida.geojson.zip"
    if not zpath.exists():
        print("buildings: zip missing, skipped (run scripts.fetch_all)")
        return {}
    geoms = list(places.geometry)
    ids = list(places["GEOID"])
    tree = STRtree(geoms)
    x0, y0, x1, y1 = places.total_bounds
    count, low, centres = defaultdict(int), defaultdict(int), []
    with zipfile.ZipFile(zpath) as z, z.open(z.namelist()[0]) as f:
        for raw in f:  # one feature per line inside the FeatureCollection wrapper
            line = raw.decode("utf-8").strip().rstrip(",")
            if not line.startswith('{"type":"Feature"') and not line.startswith('{ "type": "Feature"'):
                continue
            ring = json.loads(line)["geometry"]["coordinates"][0]
            cx = sum(p[0] for p in ring) / len(ring)
            cy = sum(p[1] for p in ring) / len(ring)
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                centres.append((cx, cy))
    print(f"buildings: {len(centres):,} footprints in the places' box")
    xy = np.array(centres)
    is_low = hand_low(src, xy)
    for (cx, cy), lo in zip(centres, is_low):
        hit = tree.query(Point(cx, cy), predicate="within")
        if len(hit):
            gid = ids[hit[0]]
            count[gid] += 1
            low[gid] += int(lo)
    return {gid: {"buildings": count[gid], "buildings_low": low[gid]} for gid in count}


def main():
    places = gpd.read_file(ROOT / "processed/sf_places.geojson").to_crs(4326)
    with rasterio.open(ROOT / "raw/static/hand_mosaic.tif") as src:
        r = roads(places, src)
        b = buildings(places, src)
    out = {}
    for gid in places["GEOID"]:
        e = {"road_km": 0.0, "road_low_km": 0.0, "roads": [], "named_roads": 0, **r.get(gid, {})}
        if b:
            e |= b.get(gid, {"buildings": 0, "buildings_low": 0})
        out[gid] = e
    meta = {"source": "Roads: OpenStreetMap major roads (motorway to tertiary). Buildings: Microsoft US Building Footprints v2 (ODbL). "
                      "Low-lying: HAND (height above nearest drainage) <= 0.5 m from Copernicus GLO-30 HAND; indicative only.",
            "low_hand_m": LOW_HAND_M, "has_buildings": bool(b)}
    OUT.write_text(json.dumps({"meta": meta, "places": out}, separators=(",", ":")), encoding="utf-8")
    tot = lambda k: sum(v.get(k, 0) for v in out.values())  # noqa: E731
    print(f"wrote {OUT.name}: {len(out)} places, {tot('road_km'):,.0f} road km ({tot('road_low_km'):,.0f} low-lying), "
          f"{tot('buildings'):,} buildings ({tot('buildings_low'):,} low-lying), {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
