"""Train/serve parity for the peak model's tide features: scripts/sf_peak.tide_timing vs app.models.peak_model.tide_timing.

Run from backend/: uv run python -m scripts.sf_peak_parity
Also reports how often the zone-centroid NOAA station differs from the gauge-based one used in training.
"""
import asyncio

import numpy as np
import pandas as pd

from app.models.peak_model import NOAA, nearest_noaa, tide_timing, zone_centroid
from app.store import from_db
from scripts import sf_peak
from scripts import sf_tide_experiment as TE


async def main():
    snap = await from_db(5)
    st = pd.read_csv(sf_peak.PROC / "sf_subset_stations.csv").query("`var` == 'WATER'").set_index("station")
    rng = np.random.default_rng(0)
    times = pd.date_range("2022-11-08 06:00", "2022-11-12 12:00", freq="h")
    pick = pd.DataFrame({"station": rng.choice(st.index, 300), "t": rng.choice(times, 300)}).set_index("t")
    train = sf_peak.tide_timing(pick)
    near = {n: min(TE.STATIONS, key=lambda s: (TE.STATIONS[s][0] - r.lat) ** 2 + (TE.STATIONS[s][1] - r.lon) ** 2) for n, r in st.iterrows()}
    cols = list(train.columns)
    diffs = []
    for i, (t, r) in enumerate(pick.iterrows()):
        serv = tide_timing(snap.tides, near[r.station], t.to_pydatetime().replace(tzinfo=__import__("datetime").timezone.utc))
        a = train.iloc[i].to_numpy(float)
        b = np.array([serv[c] for c in cols], float)
        both = ~(np.isnan(a) | np.isnan(b))
        diffs.append((np.abs(a[both] - b[both]).max() if both.any() else 0.0, int((np.isnan(a) != np.isnan(b)).sum())))
    d = np.array(diffs)
    print(f"300 samples: max abs feature difference {d[:, 0].max():.2e}; samples with a NaN-pattern mismatch: {(d[:, 1] > 0).sum()}")
    zone_agree = []
    for z in snap.zones:
        lat, lon = zone_centroid(z["geometry"])
        zid = nearest_noaa(lat, lon)
        gauges = [s for s in snap.stations if s["zone_id"] == z["id"] and s["var"] == "WATER"]
        zone_agree.append(len(gauges))
    # station agreement between zone centroid and each of its WATER gauges' training station
    import asyncio as _a
    from sqlalchemy import text
    from app.db.session import SessionLocal
    async with SessionLocal() as c:
        nm = {r.id: r.name for r in (await c.execute(text("select id, name from stations"))).all()}
    agree = tot = 0
    for z in snap.zones:
        lat, lon = zone_centroid(z["geometry"])
        zs = nearest_noaa(lat, lon)
        for s in snap.stations:
            if s["zone_id"] == z["id"] and s["var"] == "WATER" and nm[s["id"]] in near:
                tot += 1
                agree += near[nm[s["id"]]] == zs
    print(f"zone-centroid NOAA station equals the gauge-based training station for {agree}/{tot} zone-gauge links ({agree / tot:.0%})")


asyncio.run(main())
