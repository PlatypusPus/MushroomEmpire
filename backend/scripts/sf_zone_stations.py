"""Link each zone to the gauges that serve it (ROOT_CONTEXT item 2b): gauges inside the zone, else nearest within 10 km.

Run from backend/: uv run python -m scripts.sf_zone_stations
Fills zone_stations in Postgres (idempotent). WATER: up to 3 nearest; RAIN: up to 2 nearest; distance is to the zone centroid.
"""
import asyncio

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

RULE_KM, FT_KM, KEEP = 10, 0.0003048, {"WATER": 3, "RAIN": 2}


async def main():
    eng = create_async_engine(settings.database_url)
    async with eng.connect() as c:
        z = pd.DataFrame((await c.execute(text("select id, geometry from zones"))).mappings().all())
        s = pd.DataFrame((await c.execute(text("select id, var, lon, lat from stations where var in ('WATER','RAIN') and qc_ok"))).mappings().all())
    zg = gpd.GeoDataFrame(z[["id"]], geometry=[shape(g) for g in z.geometry], crs=4326).to_crs(2236)
    sg = gpd.GeoDataFrame(s, geometry=gpd.points_from_xy(s.lon, s.lat), crs=4326).to_crs(2236)
    rows = []
    for zr in zg.itertuples():
        for var, k in KEEP.items():
            g = sg[sg["var"] == var]
            d = g.distance(zr.geometry.centroid) * FT_KM
            inside = g.within(zr.geometry)
            d = d.where(~inside, 0.0)  # a gauge inside the zone always counts, distance 0
            pick = d[(d <= RULE_KM)].nsmallest(k)
            for rank, (i, km) in enumerate(pick.items(), 1):
                rows.append(dict(zone_id=zr.id, station_id=int(g.loc[i, "id"]), var=var, rank=rank, distance_km=round(float(km), 2)))
    async with eng.begin() as c:
        await c.execute(text("TRUNCATE zone_stations"))
        if rows:
            await c.execute(text("insert into zone_stations (zone_id, station_id, var, rank, distance_km) values (:zone_id, :station_id, :var, :rank, :distance_km)"), rows)
    t = pd.DataFrame(rows)
    print(len(t), "links;", t.zone_id.nunique(), "of", len(z), "zones have at least one gauge")
    print("zones with a WATER gauge:", t[t["var"] == "WATER"].zone_id.nunique(), "| with a RAIN gauge:", t[t["var"] == "RAIN"].zone_id.nunique())
    await eng.dispose()

asyncio.run(main())
