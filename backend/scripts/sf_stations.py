"""Station inventory for SF2Bench: id, variable, split, lon/lat (EPSG:2236 X/Y COORD).

Run from backend/: uv run python scripts/sf_stations.py
Writes data/processed/sf2bench_stations.csv.
"""
import json
from pathlib import Path

import pandas as pd
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2] / "data"
BASE = ROOT / "raw/sf2bench/data/Processed_hour"
to_ll = Transformer.from_crs(2236, 4326, always_xy=True)  # see ROOT_CONTEXT decision 9

rows = []
for loc in BASE.glob("*/S_*/*/*loc_info.json"):
    var, split, station = loc.parts[-4], loc.parts[-3], loc.parts[-2]
    j = json.loads(loc.read_text())
    lon, lat = to_ll.transform(j["X COORD"], j["Y COORD"])
    rows.append((station, var, split, lon, lat))
df = pd.DataFrame(rows, columns=["station", "var", "split", "lon", "lat"])
(ROOT / "processed").mkdir(exist_ok=True)
df.to_csv(ROOT / "processed/sf2bench_stations.csv", index=False)
print(df.groupby(["var", "split"]).size().unstack())
