"""Calibration fitted on S_6 by scripts/sf_validate.py (models_store/calibration_v2.json); evaluated on S_7, never fitted there."""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

PATH = Path(__file__).resolve().parents[1] / "models_store" / "calibration_v2.json"
SEVERITIES = ("low", "moderate", "high", "severe")


@lru_cache
def load() -> dict | None:
    return json.loads(PATH.read_text()) if PATH.exists() else None


def alert_threshold(default: float = 0.3) -> float:
    c = load()
    return c["alert_threshold"] if c else default


def widen(ks: np.ndarray, leads: list[int]) -> np.ndarray:
    """Per-step half-width added to q10 and q90 so the interval covers about 80% (split conformal)."""
    c = load()
    return np.interp(ks, leads, [c["widen"][str(k)] for k in leads]) if c else np.zeros(len(ks))


def probability(p: float) -> float:
    c = load()
    return float(np.interp(p, c["iso_x"], c["iso_y"])) if c else p


def severity(prob: float, peak: float) -> str:
    """Below the alert threshold = low. Otherwise the predicted peak (median) is cut at the S_6 tertile-like cuts."""
    c = load()
    d1, d2 = c["severity_cuts_pred"]
    if prob < c["alert_threshold"]:
        return "low"
    return "moderate" if peak < d1 else "high" if peak < d2 else "severe"
