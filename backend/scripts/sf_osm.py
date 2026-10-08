"""OSM exposure layers for the places: critical facilities and major roads (Overpass).

Run from backend/: uv run python -m scripts.sf_osm
Writes data/processed/sf_facilities.csv, sf_roads.geojson and sf_road_exposure.csv.
Buildings are NOT fetched (about a million in the two counties; too heavy for public Overpass).
"""
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
import shapely
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[2] / "data"
BBOX = "25.40,-80.52,26.43,-80.06"  # south,west,north,east around the places
URL = "https://overpass-api.de/api/interpreter"
HEAD = {"User-Agent": "coastguard-hackathon/0.1", "Accept": "*/*"}

def overpass(q, tries=4):
    for i in range(tries):
        r = requests.post(URL, data={"data": q}, headers=HEAD, timeout=180)
        if r.ok and r.text.lstrip().startswith("{"):
            return r.json()["elements"]
        time.sleep(15 * (i + 1))
    raise RuntimeError(f"Overpass failed: {r.status_code} {r.text[:200]}")

places = gpd.read_file(ROOT / "processed/sf_places.geojson")

# 1) critical facilities (shelter status is NOT in OSM reliably: schools/community centres are only "potential_shelter")
q = f'[out:json][timeout:150];(nwr["amenity"~"^(hospital|fire_station|police|community_centre|school)$"]({BBOX}););out tags center;'
rows = []
for e in overpass(q):
    c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
    a = e["tags"]["amenity"]
    kind = {"hospital": "hospital", "fire_station": "fire_station", "police": "police"}.get(a, "potential_shelter")
    rows.append({"osm_id": f"{e['type'][0]}{e['id']}", "kind": kind, "amenity": a, "name": e["tags"].get("name"), "lon": c["lon"], "lat": c["lat"]})
fac = gpd.GeoDataFrame(rows, geometry=gpd.points_from_xy([r["lon"] for r in rows], [r["lat"] for r in rows]), crs=4326)
fac = gpd.sjoin(fac, places[["GEOID", "geometry"]], how="inner", predicate="within").rename(columns={"GEOID": "place_id"}).drop(columns=["geometry", "index_right"])
fac.to_csv(ROOT / "processed/sf_facilities.csv", index=False)
print("facilities inside places:", fac.groupby("kind").size().to_dict())
time.sleep(5)

# 2) major roads with geometry
q = f'[out:json][timeout:170];way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]({BBOX});out geom tags;'
ways = overpass(q)
roads = gpd.GeoDataFrame(
    [{"osm_id": f"w{w['id']}", "highway": w["tags"]["highway"], "name": w["tags"].get("name"), "bridge": w["tags"].get("bridge", "no") != "no"} for w in ways],
    geometry=[LineString([(p["lon"], p["lat"]) for p in w["geometry"]]) for w in ways], crs=4326)
roads.to_file(ROOT / "processed/sf_roads.geojson", driver="GeoJSON")

# per place: km of major roads and share lying where HAND <= 0.5 m (bridges excluded from the low-lying share)
CRS = 2236
pl, rd = places.to_crs(CRS), roads.to_crs(CRS)
pieces = gpd.overlay(rd, pl[["GEOID", "geometry"]], how="intersection", keep_geom_type=True)
with rasterio.open(ROOT / "raw/static/hand_mosaic.tif") as src:
    def low_share(g):
        pts = shapely.get_coordinates(g.to_crs(4326).geometry.segmentize(0.0003))
        v = np.array([x[0] for x in src.sample(pts)])
        v = v[v != src.nodata]
        return float((v <= 0.5).mean()) if len(v) else np.nan
    out = []
    for gid, g in pieces[~pieces.bridge].groupby("GEOID"):
        out.append({"zone_id": gid, "road_km_nonbridge": round(g.length.sum() * 0.0003048, 1), "road_low_share": round(low_share(g), 3)})
km = pieces.groupby("GEOID").apply(lambda g: g.length.sum() * 0.0003048).round(1).rename("road_km").reset_index().rename(columns={"GEOID": "zone_id"})
exp = km.merge(pd.DataFrame(out), how="left")
exp.to_csv(ROOT / "processed/sf_road_exposure.csv", index=False)
print("roads:", len(roads), "segments; places with major roads:", len(exp), "| median low-lying share:", exp.road_low_share.median())
