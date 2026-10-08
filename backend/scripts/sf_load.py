"""Load the processed South Florida data into Postgres (idempotent: truncates the loaded tables first).

Run from backend/: uv run python -m scripts.sf_load [--no-hourly]
Needs DATABASE_URL in backend/.env and the alembic migration applied.
"""
import asyncio
import json
import sys
import time
from datetime import timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db.models import Event, ExposureAsset, FloodObservation, Region, Station, Zone

ROOT = Path(__file__).resolve().parents[2] / "data" / "processed"
RULE_KM = 10  # ROOT_CONTEXT item 2b


def nn(v):  # NaN -> None
    return None if pd.isna(v) else v


def build_rows():
    pl = gpd.read_file(ROOT / "sf_places.geojson")
    tab = pd.read_csv(ROOT / "sf_places.csv", dtype={"zone_id": str}).set_index("zone_id")
    st = pd.read_csv(ROOT / "sf_static.csv", dtype={"zone_id": str}).set_index("zone_id")
    zones = []
    for r in pl.itertuples():
        t, s = tab.loc[r.GEOID], st.loc[r.GEOID]
        cov = "direct" if t.WATER_in > 0 else ("nearby" if t.WATER_km <= RULE_KM else "insufficient")
        zones.append(dict(id=r.GEOID, region_id=1, name=r.NAME, county=r.county, geometry=json.loads(gpd.GeoSeries([r.geometry]).to_json())["features"][0]["geometry"],
                          area_km2=float(r.area_km2), coverage_class=cov, nearest_water_km=float(t.WATER_km),
                          elevation_m=float(s.elev_mean_m), hand_depth_m=float(s.hand_mean_m), slope=float(s.slope_deg), imperviousness=float(s.builtup_share)))
    # stations: all four subset variables, with the containing place
    ss = pd.read_csv(ROOT / "sf_subset_stations.csv")
    g = gpd.GeoDataFrame(ss, geometry=gpd.points_from_xy(ss.lon, ss.lat), crs=4326)
    g = gpd.sjoin(g, pl[["GEOID", "geometry"]], how="left", predicate="within").drop_duplicates(["var", "station"])
    stations = [dict(id=i + 1, var=r.var, name=r.station, lon=float(r.lon), lat=float(r.lat), zone_id=nn(r.GEOID)) for i, r in enumerate(g.itertuples())]
    # events: reported storms (>= 5 reports inside places), +-2 days around the report dates; all fall in the S_7 holdout
    ob = pd.read_csv(ROOT / "sf_flood_obs.csv", parse_dates=["date"]).drop_duplicates()
    z = ob[ob.place_id.notna()].groupby("EVENT_NAME").date.agg(["size", "min", "max"])
    z = z[(z["size"] >= 5) & (z["max"] <= "2023-12-31")]
    events = [dict(id=i + 1, region_id=1, name=n, start_ts=(r["min"] - pd.Timedelta(days=2)).tz_localize("UTC"), end_ts=(r["max"] + pd.Timedelta(days=2)).tz_localize("UTC"),
                   is_simulated=False, is_holdout=True, source="real_gauge") for i, (n, r) in enumerate(z.iterrows())]
    floods = [dict(unique_id=r.UNIQUE_ID, obs_date=r.date.date(), date_is_collection=bool(r.date_is_collection), zone_id=nn(r.place_id), county=r.county,
                   event_name=nn(r.EVENT_NAME), flood_depth=nn(r.FLOOD_DEPTH), affected_area=nn(r.AFFECTED_AREA), lon=float(r.lon), lat=float(r.lat))
              for r in ob.assign(place_id=ob.place_id.astype("Int64").astype(str).replace("<NA>", np.nan), date=pd.to_datetime(ob.date)).itertuples()]
    fac = pd.read_csv(ROOT / "sf_facilities.csv", dtype={"place_id": str})
    assets = [dict(zone_id=r.place_id, osm_id=r.osm_id, kind="shelter" if r.kind == "potential_shelter" else r.kind, name=nn(r.name),
                   confidence="potential" if r.kind == "potential_shelter" else "confirmed") for r in fac.itertuples()]
    return zones, stations, events, floods, assets


async def main(hourly=True):
    zones, stations, events, floods, assets = build_rows()
    eng = create_async_engine(settings.database_url)
    async with eng.begin() as c:
        await c.execute(text("TRUNCATE exposure_assets, flood_observations, dynamic_features, stations, events, zones, regions RESTART IDENTITY CASCADE"))
        await c.execute(insert(Region), [dict(id=1, name="South Florida (Miami-Dade + Broward)", kind="deep", coverage_label="experimental")])
        for model, rows in [(Zone, zones), (Station, stations), (Event, events), (FloodObservation, floods), (ExposureAsset, assets)]:
            await c.execute(insert(model), rows)
        await c.execute(text("SELECT setval(pg_get_serial_sequence('regions','id'), 1), setval(pg_get_serial_sequence('stations','id'), (SELECT max(id) FROM stations)), setval(pg_get_serial_sequence('events','id'), (SELECT max(id) FROM events))"))
    print(f"zones {len(zones)}, stations {len(stations)}, events {len(events)}, flood_observations {len(floods)}, exposure_assets {len(assets)}")
    if hourly:
        sid = {(s["var"], s["name"]): s["id"] for s in stations}
        df = pd.read_parquet(ROOT / "sf_hourly.parquet")
        t0, n = time.time(), 0
        async with eng.connect() as c:
            raw = await c.get_raw_connection()
            drv = raw.driver_connection
            for (var, name), g in df.groupby(["var", "station"], observed=True):
                ts = g.ts.dt.tz_localize(timezone.utc)  # source has no timezone; stored as UTC-labelled (see ROOT_CONTEXT)
                av = g.availability_ts.dt.tz_localize(timezone.utc)
                recs = list(zip([sid[(var, name)]] * len(g), ts.dt.to_pydatetime(), av.dt.to_pydatetime(),
                                [nn(v) for v in g.value], g.confidence.astype(int), [nn(v) for v in g.interp], [False] * len(g)))
                await drv.copy_records_to_table("dynamic_features", records=recs,
                    columns=["station_id", "ts", "availability_ts", "value", "confidence", "interpolated_value", "is_simulated"])
                n += len(g)
                if n % 1_000_000 < len(g):
                    print(f"  {n:,} rows, {time.time() - t0:.0f}s", flush=True)
            await raw.commit() if hasattr(raw, "commit") else None
        print(f"dynamic_features {n:,} rows in {time.time() - t0:.0f}s")
    await eng.dispose()

asyncio.run(main("--no-hourly" not in sys.argv))
