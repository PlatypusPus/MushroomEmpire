"""LightGBM quantile forecaster behind the same call as the persistence baseline: FeatureVector -> DepthTrajectory.

One model per (lead hour, quantile). Targets are the stage above the gauge's train-only q95 (same unit as
FeatureVector.level_m, SF2Bench units, unverified). Steps between trained leads are linearly interpolated.
Drivers are LightGBM's exact per-feature contributions (pred_contrib, the TreeSHAP values) for the 24 h median.
"""
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app import calibration
from app.schemas import DepthQuantiles, DepthStep, DepthTrajectory, Driver, FeatureVector

FEATURES = ["level", "trend", "rain_6h", "rain_24h", "rain_72h", "hand_m", "elevation_m", "change_6h", "change_24h", "max_24h", "max_72h", "std_24h"]
LEADS = [1, 3, 6, 12, 18, 24]
QUANTILES = (0.1, 0.5, 0.9)
HORIZON_H = 24
DRIVER_NAME = {"level": "level_m", "trend": "level_trend", "change_6h": "level_change_6h", "change_24h": "level_change_24h",
               "max_24h": "level_max_24h", "max_72h": "level_max_72h", "std_24h": "level_std_24h"}  # names the Explainability agent has phrases for
MODEL_PATH = Path(__file__).resolve().parents[2] / "models_store" / "lightgbm_v2.joblib"
VERSION = "lightgbm-quantile-v2"


def to_row(fv: FeatureVector) -> pd.DataFrame:
    nan = float("nan")
    v = [fv.level_m, fv.level_trend_m_per_h, fv.rain_6h, fv.rain_24h, fv.rain_72h, fv.hand_m, fv.elevation_m,
         fv.level_change_6h, fv.level_change_24h, fv.level_max_24h, fv.level_max_72h, fv.level_std_24h]
    return pd.DataFrame([[nan if x is None else x for x in v]], columns=FEATURES)


class Forecaster:
    def __init__(self, models: dict[tuple[int, float], object]):
        self.models = models

    def predict_leads(self, X: pd.DataFrame) -> dict[float, np.ndarray]:
        """{quantile: (rows, len(LEADS))}, sorted across quantiles so q10 <= q50 <= q90."""
        out = np.stack([[self.models[(k, q)].predict(X) for k in LEADS] for q in QUANTILES])  # (q, lead, rows)
        out = np.sort(out, axis=0)
        return {q: out[i].T for i, q in enumerate(QUANTILES)}

    def forecast(self, fv: FeatureVector, horizon_h: int = HORIZON_H) -> DepthTrajectory:
        X = to_row(fv)
        by_q = self.predict_leads(X)
        ks = np.arange(1, horizon_h + 1)
        q = {p: np.interp(ks, LEADS, by_q[p][0]) for p in QUANTILES}
        w = calibration.widen(ks, LEADS)  # conformal widening fitted on S_6
        q[0.1], q[0.9] = q[0.1] - w, q[0.9] + w
        steps = [DepthStep(t=fv.issue_ts + timedelta(hours=int(k)),
                           depth_m=DepthQuantiles(q10=float(q[0.1][i]), q50=float(q[0.5][i]), q90=float(q[0.9][i])))
                 for i, k in enumerate(ks)]
        peak_lead = min(LEADS, key=lambda L: abs(L - (int(np.argmax(q[0.5])) + 1)))  # explain the step where the median peaks
        contrib = self.models[(peak_lead, 0.5)].predict(X, pred_contrib=True)[0][:-1]  # last column is the bias
        drivers = sorted((Driver(feature=DRIVER_NAME.get(f, f), contribution=float(c)) for f, c in zip(FEATURES, contrib)), key=lambda d: -abs(d.contribution))
        return DepthTrajectory(zone_id=fv.zone_id, issue_ts=fv.issue_ts, model=VERSION, is_simulated=fv.is_simulated, steps=steps, drivers=drivers)

    def save(self, path: Path = MODEL_PATH):
        path.parent.mkdir(exist_ok=True)
        joblib.dump(self.models, path)

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "Forecaster | None":
        return cls(joblib.load(path)) if path.exists() else None
