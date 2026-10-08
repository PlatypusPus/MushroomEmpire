"""Zonal stats per Census place: elevation (Copernicus GLO-30 DSM), HAND, slope, land cover (ESA WorldCover).

Run from backend/: uv run python -m scripts.sf_static
Tiles are in data/raw/static (curl from the public AWS buckets). Writes data/processed/sf_static.csv.
Caveats: GLO-30 is a surface model (includes buildings and trees) with ~1-2 m vertical error, which is the
same order as flood depth on flat South Florida; HAND is derived from it and inherits that error.
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge

ROOT = Path(__file__).resolve().parents[2] / "data"
S = ROOT / "raw/static"
places = gpd.read_file(ROOT / "processed/sf_places.geojson")  # WGS84

def mosaic(prefix):
    files = [rasterio.open(f) for f in sorted(S.glob(f"{prefix}_*.tif"))]
    arr, tf = merge(files, nodata=-9999)
    prof = files[0].profile | {"height": arr.shape[1], "width": arr.shape[2], "transform": tf, "count": 1, "nodata": -9999, "driver": "GTiff"}
    out = S / f"{prefix}_mosaic.tif"
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(arr)
    return out

dem_p, hand_p = mosaic("dem"), mosaic("hand")

def zonal(path, geom):
    with rasterio.open(path) as src:
        a, tf = mask(src, [geom], crop=True, nodata=src.nodata or -9999)
        v = a[0].astype("float64")
        v[v == (src.nodata or -9999)] = np.nan
        return v, tf, src.res

rows = []
for r in places.itertuples():
    o = {"zone_id": r.GEOID}
    dem, tf, res = zonal(dem_p, r.geometry)
    hand, _, _ = zonal(hand_p, r.geometry)
    lat = r.geometry.centroid.y
    dy, dx = res[1] * 111_320, res[0] * 111_320 * np.cos(np.radians(lat))
    gy, gx = np.gradient(dem, dy, dx)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    o.update(elev_mean_m=np.nanmean(dem), elev_p10_m=np.nanpercentile(dem, 10), elev_min_m=np.nanmin(dem),
             hand_mean_m=np.nanmean(hand), hand_p50_m=np.nanmedian(hand), hand_p10_m=np.nanpercentile(hand, 10),
             slope_deg=np.nanmean(slope), pixels=int(np.isfinite(dem).sum()))
    with rasterio.open(S / "worldcover.tif") as src:
        lc, _ = mask(src, [r.geometry], crop=True, nodata=0)
    lc = lc[0][lc[0] > 0]
    o.update(builtup_share=float((lc == 50).mean()), wetland_share=float(np.isin(lc, [90, 95]).mean()),
             water_share=float((lc == 80).mean()), tree_share=float((lc == 10).mean()))
    rows.append(o)
t = pd.DataFrame(rows).round(3)
t.to_csv(ROOT / "processed/sf_static.csv", index=False)
print(t.describe().loc[["min", "50%", "max"]].T)
print("zones with NaN stats:", int(t.isna().any(axis=1).sum()))
