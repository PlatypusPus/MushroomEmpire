"""Pick the Miami-Dade + Broward station subset and report data quality + top rain events.

Run from backend/: uv run python scripts/sf_subset.py
Writes data/processed/sf_subset_stations.csv.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2] / "data"
BASE = ROOT / "raw/sf2bench/data/Processed_hour"
BOX = (-80.55, -80.05, 25.1, 26.4)  # lon min/max, lat min/max: Miami-Dade + Broward
SPLITS = ["S_5", "S_6", "S_7"]
VARS = ["WATER", "RAIN", "GATE", "PUMP"]

st = pd.read_csv(ROOT / "processed/sf2bench_stations.csv")
st = st[st.lon.between(BOX[0], BOX[1]) & st.lat.between(BOX[2], BOX[3]) & st["var"].isin(VARS) & st.split.isin(SPLITS)]
# keep stations present in all three splits
keep = st.groupby(["var", "station"]).split.nunique().loc[lambda s: s == 3].reset_index()[["var", "station"]]
st = st.merge(keep)

def load(var, split, station):
    return pd.read_csv(BASE / var / split / station / f"{station}.csv", parse_dates=["TIMESTAMP"], index_col="TIMESTAMP")

rows = []
for (var, station), g in st.groupby(["var", "station"]):
    r = {"var": var, "station": station, "lon": round(g.lon.iloc[0], 4), "lat": round(g.lat.iloc[0], 4)}
    for sp in SPLITS:
        d = load(var, sp, station)
        r[f"missing_{sp}"] = round(d.VALUE.isna().mean(), 3)
        r[f"interp_{sp}"] = round((d.VALUE.isna() | (d.VALUE != d.INTERPOLATED_VALUE)).mean(), 3)
    rows.append(r)
out = pd.DataFrame(rows)
out.to_csv(ROOT / "processed/sf_subset_stations.csv", index=False)
print(out.groupby("var").size().to_dict())
print(out.groupby("var")[[f"missing_{s}" for s in SPLITS]].mean().round(3))

# heavy-rain days in the holdout split: daily sum per rain gauge, then mean across gauges
rain = pd.concat({s: load("RAIN", "S_7", s).INTERPOLATED_VALUE for s in out[out["var"] == "RAIN"].station}, axis=1)
daily = rain.resample("D").sum()
print("\nTop 8 days by mean gauge rainfall, S_7 (units as in file, likely inches):")
print(pd.DataFrame({"mean": daily.mean(axis=1), "max": daily.max(axis=1), "gauges>2": (daily > 2).sum(axis=1)}).nlargest(8, "mean").round(2))
