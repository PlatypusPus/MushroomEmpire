"""Neighbourhood zones = US Census places in Miami-Dade + Broward, with gauge coverage.

Run from backend/: uv run python scripts/sf_places.py
Writes data/processed/sf_places.geojson and sf_places.csv.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2] / "data"
CRS = 2236  # Florida East, US ft (see ROOT_CONTEXT decision 9)
FT_KM = 0.0003048

county = gpd.read_file(ROOT / "raw/census/county/cb_2023_us_county_500k.shp").to_crs(CRS)
county = county[(county.STATEFP == "12") & county.NAME.isin(["Miami-Dade", "Broward"])]
places = gpd.read_file(ROOT / "raw/census/place/cb_2023_12_place_500k.shp").to_crs(CRS)
places = gpd.sjoin(places, county[["NAME", "geometry"]].rename(columns={"NAME": "county"}), predicate="intersects")
# a place can touch both counties; keep the county holding most of its area
places["inter"] = [r.geometry.intersection(county.loc[county.NAME == r.county].geometry.iloc[0]).area for r in places.itertuples()]
places = places.sort_values("inter").drop_duplicates("GEOID", keep="last")
places["area_km2"] = (places.area * 0.09290304 / 1e6).round(1)

st = pd.read_csv(ROOT / "processed/sf_subset_stations.csv")
pts = gpd.GeoDataFrame(st, geometry=gpd.points_from_xy(st.lon, st.lat), crs=4326).to_crs(CRS)
rows = []
for r in places.itertuples():
    o = {"zone_id": r.GEOID, "name": r.NAME, "county": r.county, "area_km2": r.area_km2}
    c = r.geometry.centroid
    for v in ["WATER", "RAIN", "GATE", "PUMP"]:
        p = pts[pts["var"] == v]
        o[f"{v}_in"] = int(p.within(r.geometry).sum())
        o[f"{v}_km"] = round(p.distance(c).min() * FT_KM, 1)  # nearest gauge to the place centroid
    rows.append(o)
t = pd.DataFrame(rows).sort_values(["county", "name"])
t.to_csv(ROOT / "processed/sf_places.csv", index=False)
places[["GEOID", "NAME", "county", "area_km2", "geometry"]].to_crs(4326).to_file(ROOT / "processed/sf_places.geojson", driver="GeoJSON")
print(len(t), "places; total area km2:", t.area_km2.sum().round(0))
print(t.to_string(index=False))
print("\nplaces with no water gauge inside:", (t.WATER_in == 0).sum(), "| nearest water gauge >5 km:", (t.WATER_km > 5).sum())
