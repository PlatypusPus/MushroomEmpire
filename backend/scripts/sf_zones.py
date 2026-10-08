"""Propose statistical zones for the Miami-Dade + Broward subset.

Run from backend/: uv run python scripts/sf_zones.py
KMeans on WATER station positions (State Plane ft), Voronoi-style polygons clipped to the
subset box. Writes data/processed/sf_zones.geojson and sf_zone_stations.csv.
ponytail: statistical clusters, not administrative neighbourhoods; swap in Census places or basins if wanted.
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint, box
from shapely.ops import voronoi_diagram
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parents[2] / "data"
K = 14
BOX = (-80.55, -80.05, 25.1, 26.4)

st = pd.read_csv(ROOT / "processed/sf_subset_stations.csv")
g = gpd.GeoDataFrame(st, geometry=gpd.points_from_xy(st.lon, st.lat), crs=4326).to_crs(2236)
water = g[g["var"] == "WATER"].copy()
xy = np.c_[water.geometry.x, water.geometry.y]
water["zone"] = KMeans(K, n_init=10, random_state=0).fit_predict(xy)

# zone polygon = union of the Voronoi cells of its water stations, clipped to the box
clip = gpd.GeoSeries([box(BOX[0], BOX[2], BOX[1], BOX[3])], crs=4326).to_crs(2236).iloc[0]
cells = gpd.GeoDataFrame(geometry=list(voronoi_diagram(MultiPoint(list(water.geometry)), envelope=clip).geoms), crs=2236)
cells = gpd.sjoin(cells, water[["zone", "geometry"]], predicate="contains")
cells["geometry"] = cells.geometry.intersection(clip)
zones = cells.dissolve("zone")[["geometry"]].reset_index()
zones["zone_id"] = [f"Z-{i + 1:02d}" for i in range(len(zones))]
zid = dict(zip(zones.zone, zones.zone_id))

# every other station goes to the zone polygon that contains it, else the nearest zone
g["geometry"] = g.geometry
other = gpd.sjoin_nearest(g[["var", "station", "geometry"]], zones[["zone_id", "geometry"]], how="left").drop_duplicates(["var", "station"])
tab = other.drop(columns=["geometry", "index_right"])
zones["area_km2"] = (zones.area * 0.09290304 / 1e6).round(1)
counts = tab.pivot_table(index="zone_id", columns="var", values="station", aggfunc="count", fill_value=0)
zones = zones.merge(counts, left_on="zone_id", right_index=True).drop(columns="zone")
c = gpd.GeoSeries(zones.geometry.centroid, crs=2236).to_crs(4326)
zones["lon"], zones["lat"] = c.x.round(3), c.y.round(3)
zones.to_crs(4326).to_file(ROOT / "processed/sf_zones.geojson", driver="GeoJSON")
tab.to_csv(ROOT / "processed/sf_zone_stations.csv", index=False)
print(zones.drop(columns="geometry").sort_values("zone_id").to_string(index=False))
print("zones without RAIN:", (zones.RAIN == 0).sum(), "| without GATE:", (zones.GATE == 0).sum())
