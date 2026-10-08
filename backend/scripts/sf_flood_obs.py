"""Ingest SFBench's FLOOD_OBSERVATION_REPOSITORY_V2024.csv (real reported flooding) into places.

Run from backend/: uv run python scripts/sf_flood_obs.py
Source: github.com/AslanDing/SFBench dataset/ (copied to data/raw/sfbench_repo/flood_obs.csv).
Writes data/processed/sf_flood_obs.csv. Reports are positives only (no "no flood" records).
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkt

ROOT = Path(__file__).resolve().parents[2] / "data"
d = pd.read_csv(ROOT / "raw/sfbench_repo/flood_obs.csv", index_col=0)
d["county"] = d.COUNTY.str.title().replace({"Miami-Dade": "Miami-Dade"})
g = gpd.GeoDataFrame(d, geometry=d.geometry.map(wkt.loads), crs=2236)  # same State Plane East ft as stations
d["date"] = pd.to_datetime(d.FLOODING_DATE.fillna(d.COLLECTION_DATE), utc=True).dt.date
d["date_is_collection"] = d.FLOODING_DATE.isna()  # no flooding date: fell back to collection date
ll = g.to_crs(4326)
d["lon"], d["lat"] = ll.geometry.x, ll.geometry.y

places = gpd.read_file(ROOT / "processed/sf_places.geojson").to_crs(2236)
j = gpd.sjoin(g[["geometry"]], places[["GEOID", "NAME", "geometry"]], how="left", predicate="within")
d["place_id"], d["place"] = j.GEOID, j.NAME

out = d[["UNIQUE_ID", "date", "date_is_collection", "county", "MUNICIPALITY", "place_id", "place", "EVENT_NAME", "EVENT_TYPE",
         "FLOOD_DEPTH", "AFFECTED_AREA", "PROPERTY_TYPE", "SURVEY_TYPE", "lon", "lat"]]
out.to_csv(ROOT / "processed/sf_flood_obs.csv", index=False)

zone = out[out.place_id.notna()]
print(len(out), "reports total;", len(zone), "fall inside a Miami-Dade/Broward place")
ev = zone.groupby(["EVENT_NAME"]).agg(n=("UNIQUE_ID", "size"), places=("place_id", "nunique"), first=("date", "min"), last=("date", "max"))
print(ev.sort_values("n", ascending=False).head(10))
print("date fallback to collection date:", int(zone.date_is_collection.sum()), "| depth unknown:", int((zone.FLOOD_DEPTH == "don't_know").sum()))
