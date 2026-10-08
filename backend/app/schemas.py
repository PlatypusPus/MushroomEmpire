"""Frozen API contracts (ROOT_CONTEXT section 9). Change only by team agreement."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Coverage = Literal["validated", "experimental", "simulation", "insufficient_data"]
Severity = Literal["low", "moderate", "high", "severe"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Region(Strict):
    id: str
    name: str
    kind: Literal["deep", "transfer"]
    coverage: Coverage
    is_simulated: bool


class Zone(Strict):
    id: str
    region_id: str
    name: str
    county: str | None
    coverage_class: str | None  # lane A: direct | nearby | insufficient (gauge proximity)
    geometry: dict  # GeoJSON Polygon
    elevation_m: float | None
    hand_m: float | None
    is_simulated: bool


class Event(Strict):
    id: int
    region_id: str
    name: str
    start_ts: datetime
    end_ts: datetime
    is_simulated: bool
    is_holdout: bool
    source: str  # real_gauge | labelled_simulation


class TimeWindow(Strict):
    earliest: datetime
    likely: datetime
    latest: datetime


class ExposureItem(Strict):
    type: Literal["road", "building", "hospital", "shelter", "police", "fire_station"]
    name: str
    status: Literal["confirmed", "potentially_exposed"]


class FeatureVector(Strict):
    """Everything the forecaster may see for one zone at one issue time."""

    zone_id: str
    issue_ts: datetime
    level_m: float  # worst gauge's latest stage minus its train-only q95 (SF2Bench units, unverified, likely ft)
    level_trend_m_per_h: float
    rain_6h: float | None  # SF2Bench file units, unverified (ROOT_CONTEXT 20.10): never print. None = no rain gauge
    rain_24h: float | None
    rain_72h: float | None
    hand_m: float | None
    elevation_m: float | None
    is_simulated: bool
    # level history, same stage units as level_m (feature study: the biggest accuracy gain). None = not enough readings
    level_change_6h: float | None = None
    level_change_24h: float | None = None
    level_max_24h: float | None = None
    level_max_72h: float | None = None
    level_std_24h: float | None = None


class DepthQuantiles(Strict):
    q10: float
    q50: float
    q90: float


class DepthStep(Strict):
    t: datetime
    depth_m: DepthQuantiles  # metres above the zone threshold; > 0 means high-water episode


class Driver(Strict):
    feature: str
    contribution: float


class DepthTrajectory(Strict):
    zone_id: str
    issue_ts: datetime
    model: str
    is_simulated: bool
    steps: list[DepthStep]
    drivers: list[Driver]


class RiskOutput(Strict):
    zone_id: str
    issue_ts: datetime
    probability: float
    severity: Severity
    onset: TimeWindow | None
    peak: TimeWindow | None
    peak_level_m: float
    horizon_h: int


class ZonePayload(Strict):
    zone_id: str
    issue_ts: datetime
    coverage: Coverage
    is_simulated: bool
    probability: float | None  # None only when coverage is insufficient_data: unknown is never low
    severity: Severity | None
    onset: TimeWindow | None  # None = no episode expected in horizon
    peak: TimeWindow | None
    drivers_text: list[str]
    exposure: list[ExposureItem]
    rank: int
    rank_reason: str
    alert_text: str
    model: str | None


class Weights(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)  # hashable: keys the replay memo

    probability: float = 0.30
    severity: float = 0.20
    urgency: float = 0.25
    exposure: float = 0.10
    vulnerable: float = 0.15
    uncertainty: float = 0.0


class Metrics(Strict):
    model: str
    version: str
    region_id: str
    metrics: dict
