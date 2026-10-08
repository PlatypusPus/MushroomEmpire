"""One-shot, resumable fetch of every extra dataset (run this when you have fast internet).

  uv run python -m scripts.fetch_all --list     # show what would be fetched and sizes (no download)
  uv run python -m scripts.fetch_all            # fetch everything missing; safe to re-run / interrupt

Already-present files are skipped. All sources below were reachability-checked on 2026-10-08.
Not included on purpose: GFF era5/s1/hand/dem zips (global, huge), CASPIAN and SFBench checkpoints (optional, unverified).
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

from scripts.download import fetch

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
UA = {"User-Agent": "coastguard-hackathon/0.1"}
S3 = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current"
FILES = [  # (url, destination, why)
    (f"{S3}/n26w081/USGS_13_n26w081.tif", "3dep/USGS_13_n26w081.tif", "USGS 3DEP 10 m lidar DEM (replaces the 30 m DSM for depth)"),
    (f"{S3}/n27w081/USGS_13_n27w081.tif", "3dep/USGS_13_n27w081.tif", "USGS 3DEP 10 m lidar DEM"),
    ("https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Florida.geojson.zip", "buildings/Florida.geojson.zip", "Microsoft building footprints, Florida"),
    ("https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_12_bg_500k.zip", "census/bg.zip", "Census block groups (for exposed population)"),
]
STATIONS = {"8722956": "South Port Everglades", "8723214": "Virginia Key", "8722670": "Lake Worth Pier"}
POINTS = {"miami": (25.78, -80.21), "fort_lauderdale": (26.12, -80.14), "hollywood": (26.01, -80.15), "homestead": (25.47, -80.48),
          "pompano": (26.24, -80.12), "doral": (25.82, -80.35), "miramar": (25.98, -80.32), "boca": (26.35, -80.10)}
YEARS = range(2010, 2024)


def tides():
    """NOAA CO-OPS hourly observed water level and predicted tide; surge = observed - predicted."""
    for sid in STATIONS:
        for product in ("hourly_height", "predictions"):
            out = RAW / "noaa" / f"{sid}_{product}.csv"
            if out.exists():
                continue
            rows = []
            for y in tqdm(YEARS, desc=f"NOAA {STATIONS[sid]} {product}"):
                for m in range(1, 13):
                    b = pd.Timestamp(y, m, 1)
                    e = b + pd.offsets.MonthEnd(0)
                    q = dict(product=product, station=sid, begin_date=b.strftime("%Y%m%d"), end_date=e.strftime("%Y%m%d"), datum="NAVD",
                             units="metric", time_zone="gmt", format="json", application="coastguard")
                    if product == "predictions":
                        q["interval"] = "h"
                    d = requests.get("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter", params=q, timeout=60).json()
                    rows += d.get("data") or d.get("predictions") or []
            out.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).to_csv(out, index=False)


def rain():
    """Open-Meteo ERA5 archive hourly precipitation (mm) at 8 points: an independent rain series, NOT a forecast."""
    for name, (lat, lon) in POINTS.items():
        out = RAW / "openmeteo" / f"{name}.csv"
        if out.exists():
            continue
        parts = []
        for y in tqdm(YEARS, desc=f"Open-Meteo {name}"):
            for _ in range(5):
                r = requests.get("https://archive-api.open-meteo.com/v1/archive", timeout=60, params=dict(
                    latitude=lat, longitude=lon, start_date=f"{y}-01-01", end_date=f"{y}-12-31", hourly="precipitation", timezone="GMT"))
                if r.ok:
                    break
                time.sleep(20)
            r.raise_for_status()
            h = r.json()["hourly"]
            parts.append(pd.DataFrame({"time": h["time"], "precip_mm": h["precipitation"]}))
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(parts).to_csv(out, index=False)


if __name__ == "__main__":
    if "--list" in sys.argv:
        total = 0
        for url, dest, why in FILES:
            n = int(requests.head(url, allow_redirects=True, timeout=30, headers=UA).headers.get("content-length", 0))
            total += n
            print(f"{n / 1e6:8.0f} MB  {'(have)' if (RAW / dest).exists() else '      '} {dest:34} {why}")
        print(f"{total / 1e6:8.0f} MB  files above\n   small  NOAA CO-OPS tide + prediction, 3 stations x 2010-2023 (about 1,000 API calls)\n   small  Open-Meteo ERA5 rain, 8 points x 2010-2023 (about 112 API calls)")
    else:
        for url, dest, _ in FILES:
            fetch(url, RAW / dest)
        tides()
        rain()
        print("done")
