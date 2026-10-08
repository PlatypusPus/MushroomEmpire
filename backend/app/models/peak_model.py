"""Dedicated peak-time model (scripts/sf_peak.py): when, within the next 24 h, does the stage peak, given a high-water event.

A LightGBM multiclass over the 24 hours. Inputs: the served level features, the issue clock (hour, month) and the timing of the
PREDICTED astronomical tide (hours to the next two highs and next low, tide shape over the next 24 h; NOAA predictions are known in
advance, so this is not leakage). Output: the median hour as `likely` and a central window tuned to cover 80% on S_6.
Held-out S_7, event rows: mean error 3.9 h vs 5.1 h for an issue-hour prior; the old argmax-of-median had no skill.
"""
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.schemas import FeatureVector, TimeWindow

MODEL_PATH = Path(__file__).resolve().parents[2] / "models_store" / "peak_v1.joblib"
NOAA = {"8723214": (25.7314, -80.1618), "8722956": (26.0817, -80.1167), "8722670": (26.6128, -80.0342)}  # (lat, lon): Virginia Key, Port Everglades, Lake Worth
TIDE_STEPS = (3, 6, 9, 12, 15, 18, 21, 24)


def nearest_noaa(lat: float, lon: float) -> str:
    return min(NOAA, key=lambda s: (NOAA[s][0] - lat) ** 2 + (NOAA[s][1] - lon) ** 2)


def zone_centroid(geometry: dict) -> tuple[float, float]:
    """(lat, lon) of a GeoJSON polygon / multipolygon by vertex mean: good enough to pick the nearest of three tide stations."""
    def pts(g):
        return g if isinstance(g[0][0], float | int) else [p for part in g for p in pts(part)]
    xy = np.array(pts(geometry["coordinates"]), float)
    return float(xy[:, 1].mean()), float(xy[:, 0].mean())


def tide_timing(rows: list[dict], noaa_id: str, issue_ts) -> dict:
    """Same definitions as scripts/sf_peak.tide_timing, computed from the snapshot's predicted-tide rows. NaN if unavailable."""
    nan = float("nan")
    out = {"hi1": nan, "hi2": nan, "lo1": nan, **{f"tide_rel_{k}": nan for k in TIDE_STEPS}}
    pts = [(r["ts"], r["value"]) for r in rows if r["noaa_id"] == noaa_id and r["value"] is not None]
    if len(pts) < 30:
        return out
    s = pd.Series([v for _, v in pts], index=pd.DatetimeIndex([t for t, _ in pts]))
    s = s[~s.index.duplicated()]
    idx = pd.date_range(s.index.min(), s.index.max(), freq="h")
    p = s.reindex(idx).interpolate(limit=3)
    pos = idx.get_indexer([pd.Timestamp(issue_ts)])[0]
    if pos < 1:
        return out
    v = p.to_numpy()
    hi = np.where((v[1:-1] > v[:-2]) & (v[1:-1] >= v[2:]))[0] + 1
    lo = np.where((v[1:-1] < v[:-2]) & (v[1:-1] <= v[2:]))[0] + 1
    j, jl = np.searchsorted(hi, pos + 1), np.searchsorted(lo, pos + 1)
    if j < len(hi):
        out["hi1"] = float(hi[j] - pos)
    if j + 1 < len(hi):
        out["hi2"] = float(hi[j + 1] - pos)
    if jl < len(lo):
        out["lo1"] = float(lo[jl] - pos)
    fwd = p.iloc[pos + 1:pos + 25]
    if len(fwd.dropna()) >= 12:
        m = float(fwd.mean())
        for k in TIDE_STEPS:
            if pos + k < len(v) and not np.isnan(v[pos + k]):
                out[f"tide_rel_{k}"] = float(v[pos + k] - m)
    return out


class PeakModel:
    def __init__(self, bundle: dict):
        self.m, self.features, self.alpha = bundle["model"], bundle["features"], bundle["window_alpha"]

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "PeakModel | None":
        return cls(joblib.load(path)) if path.exists() else None

    def row(self, fv: FeatureVector, tide: dict) -> pd.DataFrame:
        nan = float("nan")
        v = {"level": fv.level_m, "trend": fv.level_trend_m_per_h, "rain_6h": fv.rain_6h, "rain_24h": fv.rain_24h, "rain_72h": fv.rain_72h, "hand_m": fv.hand_m,
             "elevation_m": fv.elevation_m, "change_6h": fv.level_change_6h, "change_24h": fv.level_change_24h, "max_24h": fv.level_max_24h,
             "max_72h": fv.level_max_72h, "std_24h": fv.level_std_24h, "hour": fv.issue_ts.hour, "month": fv.issue_ts.month, **tide}
        return pd.DataFrame([[nan if v.get(f) is None else v.get(f, nan) for f in self.features]], columns=self.features)

    def window(self, fv: FeatureVector, tide: dict) -> TimeWindow:
        P = np.zeros(24)
        P[self.m.classes_] = self.m.predict_proba(self.row(fv, tide))[0]
        cdf = P.cumsum()
        q = lambda a: int(np.argmax(cdf >= a)) + 1  # noqa: E731
        lo, mid, hi = q(self.alpha), q(0.5), q(1 - self.alpha)
        t = lambda k: fv.issue_ts + timedelta(hours=k)  # noqa: E731
        return TimeWindow(earliest=t(lo), likely=t(mid), latest=t(hi))
