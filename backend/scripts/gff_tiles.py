"""Phase 1: list GFF tiles that are India-only and near the coast.

Run from backend/: uv run python scripts/gff_tiles.py
Reads data/raw/gff/base/rois/*-meta.json (+ the tile .tif for location) and
Natural Earth land/admin_1 in data/raw/ne. Writes data/processed/gff_india_coastal.csv.
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.warp import transform_bounds
from shapely.geometry import Point, box

ROOT = Path(__file__).resolve().parents[2] / "data"
ROIS = ROOT / "raw/gff/base/rois"
MAX_KM = 50

rows = []
for mf in sorted(ROIS.glob("*-meta.json")):
    m = json.loads(mf.read_text())
    tif = ROIS / m["floodmap"]
    with rasterio.open(tif) as src:
        w, s, e, n = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    # ROIs can be 250+ km wide (centre may be offshore), so locate by flooded sub-tiles
    visit = gpd.read_file(ROIS / m["visit_tiles"])
    wet = visit[visit.n_flooded > 0] if "n_flooded" in visit else visit.iloc[:0]
    c = wet.union_all().centroid if len(wet) else box(w, s, e, n).centroid
    rows.append({
        "tile_id": m["key"], "type": m["type"], "post_date": m["post_date"][:10],
        "pre1_date": m["pre1_date"][:10], "flooding": m.get("flooding"),
        "flooded_subtiles": int(len(wet)), "roi_width_deg": round(e - w, 2),
        "lon": c.x, "lat": c.y,
    })
tiles = gpd.GeoDataFrame(rows, geometry=[Point(r["lon"], r["lat"]) for r in rows], crs=4326)

# state + country (admin_1 point-in-polygon; Natural Earth is a generalised boundary)
adm1 = gpd.read_file(ROOT / "raw/ne/adm1/ne_10m_admin_1_states_provinces.shp")[["admin", "name", "geometry"]]
tiles = gpd.sjoin(tiles, adm1, how="left", predicate="within").drop(columns="index_right")
tiles = tiles.rename(columns={"admin": "country", "name": "state"})

# distance to coast: land boundary, measured in a per-tile azimuthal equidistant projection
coast = gpd.read_file(ROOT / "raw/ne/land/ne_10m_land.shp").boundary
def km_to_coast(p):
    crs = f"+proj=aeqd +lat_0={p.y} +lon_0={p.x} +units=m"
    near = coast.clip(box(p.x - 2, p.y - 2, p.x + 2, p.y + 2))
    if near.empty:
        return float("inf")
    return gpd.GeoSeries([Point(0, 0)], crs=crs).distance(near.to_crs(crs).union_all()).iloc[0] / 1000
tiles["km_to_coast"] = tiles.geometry.apply(km_to_coast).round(1)

india = tiles[(tiles.country == "India") & (tiles.km_to_coast <= MAX_KM)].copy()
# distinct events: same state with post dates within 14 days count as one
india = india.sort_values(["state", "post_date"])
india["event_group"] = (india.groupby("state").post_date.transform(lambda s: pd.to_datetime(s).diff().dt.days.gt(14).cumsum())).astype(int)
out = india[["tile_id", "type", "state", "post_date", "pre1_date", "flooding", "flooded_subtiles", "roi_width_deg", "lat", "lon", "km_to_coast", "event_group"]]
(ROOT / "processed").mkdir(exist_ok=True)
out.to_csv(ROOT / "processed/gff_india_coastal.csv", index=False)
print(f"{len(tiles)} tiles total, {len(out)} India-only within {MAX_KM} km of coast")
print(out.to_string(index=False))
print("\nper state:", out.state.value_counts().to_dict())
print("distinct events (state, group):", out.groupby(["state", "event_group"]).ngroups)
