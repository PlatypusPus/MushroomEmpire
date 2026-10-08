"""Load subset WATER + RAIN hourly series (S_5..S_7) into one parquet with availability_ts.

Run from backend/: uv run python -m scripts.sf_hourly
Writes data/processed/sf_hourly.parquet.
"""
from pathlib import Path

import pandas as pd

from app.features import AVAIL_LAG

ROOT = Path(__file__).resolve().parents[2] / "data"
BASE = ROOT / "raw/sf2bench/data/Processed_hour"
st = pd.read_csv(ROOT / "processed/sf_subset_stations.csv")
st = st[st["var"].isin(["WATER", "RAIN"])]

parts = []
for var, name in zip(st["var"], st.station):
    for split in ["S_5", "S_6", "S_7"]:
        d = pd.read_csv(BASE / var / split / name / f"{name}.csv", parse_dates=["TIMESTAMP"])
        d.insert(0, "station", name), d.insert(1, "var", var), d.insert(2, "split", split)
        parts.append(d)
df = pd.concat(parts, ignore_index=True).rename(columns={"TIMESTAMP": "ts", "VALUE": "value", "CONFIDENCE": "confidence", "INTERPOLATED_VALUE": "interp"})
df["availability_ts"] = df.ts + AVAIL_LAG
df["var"] = df["var"].astype("category")
df.to_parquet(ROOT / "processed/sf_hourly.parquet", index=False)
print(len(df), "rows;", df.station.nunique(), "stations;", df.ts.min(), "to", df.ts.max())
print(df.groupby(["var", "split"], observed=True).size().unstack())
