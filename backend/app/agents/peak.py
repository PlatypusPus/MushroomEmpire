"""Peak agent: replaces the trajectory's peak window with the dedicated peak model's (the trajectory argmax had no timing skill)."""
from app.models.peak_model import PeakModel, nearest_noaa, tide_timing, zone_centroid
from app.schemas import DepthTrajectory, FeatureVector, RiskOutput
from app.store import Snapshot

_peak = PeakModel.load()  # None if models_store/peak_v1.joblib is missing: keep the trajectory peak


def attach_peak(risk: RiskOutput, traj: DepthTrajectory, fv: FeatureVector, snap: Snapshot) -> RiskOutput:
    if _peak is None or risk.peak is None or not traj.model.startswith("lightgbm-quantile"):
        return risk
    lat, lon = zone_centroid(snap.zone(fv.zone_id)["geometry"])
    tide = tide_timing(snap.tides, nearest_noaa(lat, lon), fv.issue_ts)
    return risk.model_copy(update={"peak": _peak.window(fv, tide)})
