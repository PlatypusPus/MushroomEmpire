"""High-water episodes per WATER gauge (train-only 0.95 threshold from S_5) and a check against real flood reports.

Run from backend/: uv run python -m scripts.sf_labels
Writes data/processed/sf_episodes.csv. Episodes are a stage-exceedance PROXY, not observed flooding.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

from app.features import episodes, threshold

ROOT = Path(__file__).resolve().parents[2] / "data"
df = pd.read_parquet(ROOT / "processed/sf_hourly.parquet", columns=["station", "var", "split", "ts", "interp"])
w = df[df["var"] == "WATER"]
stations = pd.read_csv(ROOT / "processed/sf_subset_stations.csv").query("`var` == 'WATER'").set_index("station")

rows = []
for name, g in w.groupby("station"):
    s = g.set_index("ts").interp.sort_index()
    thr = threshold(s[g.set_index("ts").split.sort_index() == "S_5"])  # TRAIN ONLY
    for split, sp in g.set_index("ts").sort_index().groupby("split"):
        e = episodes(sp.interp, thr)
        e.insert(0, "split", split), e.insert(0, "station", name), e.insert(2, "threshold", thr)
        rows.append(e)
ep = pd.concat(rows, ignore_index=True)
ep.to_csv(ROOT / "processed/sf_episodes.csv", index=False)
yrs = {"S_5": 5, "S_6": 5, "S_7": 4}
print(ep.groupby("split").agg(episodes=("hours", "size"), median_h=("hours", "median"), p90_h=("hours", lambda x: x.quantile(0.9))))
print("episodes per gauge-year:", {k: round(len(ep[ep.split == k]) / ep.station.nunique() / v, 2) for k, v in yrs.items()})

# check against real reports in the holdout years: does any gauge within 10 km show an episode within +-1 day?
obs = pd.read_csv(ROOT / "processed/sf_flood_obs.csv", parse_dates=["date"])
obs = obs[obs.place_id.notna() & obs.date.between("2020-01-01", "2023-12-31")]
t = Transformer.from_crs(4326, 2236, always_xy=True)
gx, gy = t.transform(stations.lon.values, stations.lat.values)
ox, oy = t.transform(obs.lon.values, obs.lat.values)
dist = np.hypot(ox[:, None] - gx[None], oy[:, None] - gy[None]) * 0.0003048
hold = ep[ep.split == "S_7"].copy()
hold[["start", "end"]] = hold[["start", "end"]].apply(pd.to_datetime)
by_station = {k: v for k, v in hold.groupby("station")}
names = stations.index.to_numpy()

def hit(i, km=10, pad=1):
    d0 = obs.date.iloc[i]
    for n in names[dist[i] <= km]:
        e = by_station.get(n)
        if e is not None and ((e.start <= d0 + pd.Timedelta(days=pad + 1)) & (e.end >= d0 - pd.Timedelta(days=pad))).any():
            return True
    return False

obs["hit"] = [hit(i) for i in range(len(obs))]
# chance rate: same test on random dates in S_7 at the same report locations
rng = np.random.default_rng(0)
rand = []
for i in range(len(obs)):
    for _ in range(20):
        d0 = pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(rng.integers(0, 1461)))
        old = obs.date.iloc[i]; obs.iloc[i, obs.columns.get_loc("date")] = d0
        rand.append(hit(i)); obs.iloc[i, obs.columns.get_loc("date")] = old
print(f"\nreports in holdout inside places: {len(obs)}; episode within 10 km and +-1 day: {obs.hit.mean():.2f}; chance rate (random dates, same places): {np.mean(rand):.2f}")
print(obs.groupby("EVENT_NAME").hit.agg(["size", "mean"]).sort_values("size", ascending=False).head(6).round(2))
