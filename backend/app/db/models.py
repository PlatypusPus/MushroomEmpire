"""Schema from ROOT_CONTEXT section 8, adapted for South Florida (gauge-level features, Census-place zones).

is_simulated is a real column on events, forecasts and dynamic_features; it must reach the API and UI badge.
"""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(16))  # deep | transfer
    coverage_label: Mapped[str] = mapped_column(String(24))  # validated | experimental | simulation | insufficient


class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # Census place GEOID
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    name: Mapped[str] = mapped_column(String(80))
    county: Mapped[str] = mapped_column(String(40))
    geometry: Mapped[dict] = mapped_column(JSON)  # GeoJSON (WGS84)
    area_km2: Mapped[float] = mapped_column(Float)
    # direct = gauge inside, nearby = nearest water gauge within the coverage rule, insufficient otherwise
    coverage_class: Mapped[str] = mapped_column(String(16))
    nearest_water_km: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    hand_depth_m: Mapped[float | None] = mapped_column(Float)
    slope: Mapped[float | None] = mapped_column(Float)
    imperviousness: Mapped[float | None] = mapped_column(Float)


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (UniqueConstraint("var", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    var: Mapped[str] = mapped_column(String(8))  # WATER | RAIN | GATE | PUMP | WELL
    name: Mapped[str] = mapped_column(String(40))
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id"))  # place containing it, if any
    qc_ok: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")  # False = failed the gauge QC screen
    qc_reason: Mapped[str | None] = mapped_column(String(80))


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    name: Mapped[str] = mapped_column(String(120))
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_holdout: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32))  # real_gauge | labelled_simulation


class DynamicFeature(Base):
    """One hourly reading of one gauge, raw as in SF2Bench. Derived rolling sums live in the feature table."""

    __tablename__ = "dynamic_features"
    __table_args__ = (UniqueConstraint("station_id", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    availability_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # when it could first be known
    value: Mapped[float | None] = mapped_column(Float)  # hourly mean of raw points; NULL = missing
    confidence: Mapped[int] = mapped_column(Integer)  # SF2Bench: number of raw points in the hour
    interpolated_value: Mapped[float | None] = mapped_column(Float)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class FloodObservation(Base):
    """Real reported flooding (SFBench flood observation repository). Positives only."""

    __tablename__ = "flood_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    unique_id: Mapped[str] = mapped_column(String(40), unique=True)
    obs_date: Mapped[date] = mapped_column(Date, index=True)
    date_is_collection: Mapped[bool] = mapped_column(Boolean)  # no flooding date, collection date used
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id"), index=True)
    county: Mapped[str] = mapped_column(String(40))
    event_name: Mapped[str | None] = mapped_column(String(120))
    flood_depth: Mapped[str | None] = mapped_column(String(32))
    affected_area: Mapped[str | None] = mapped_column(String(32))
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(20))
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"))
    trained_on_splits: Mapped[list] = mapped_column(JSON)
    metrics_json: Mapped[dict] = mapped_column(JSON)


class Forecast(Base):
    __tablename__ = "forecasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    model_run_id: Mapped[int | None] = mapped_column(ForeignKey("model_runs.id"))
    issue_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    horizon_h: Mapped[int] = mapped_column(Integer)
    depth_q10: Mapped[float] = mapped_column(Float)
    depth_q50: Mapped[float] = mapped_column(Float)
    depth_q90: Mapped[float] = mapped_column(Float)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class RiskOutput(Base):
    __tablename__ = "risk_outputs"
    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_id: Mapped[int] = mapped_column(ForeignKey("forecasts.id"), unique=True)
    probability: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(12))  # low | moderate | high | severe
    onset_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onset_window: Mapped[dict | None] = mapped_column(JSON)  # {earliest, likely, latest}
    peak_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    peak_window: Mapped[dict | None] = mapped_column(JSON)


class Explanation(Base):
    __tablename__ = "explanations"
    id: Mapped[int] = mapped_column(primary_key=True)
    risk_output_id: Mapped[int] = mapped_column(ForeignKey("risk_outputs.id"), unique=True)
    driver_json: Mapped[list] = mapped_column(JSON)
    plain_text: Mapped[str] = mapped_column(Text)


class ExposureAsset(Base):
    __tablename__ = "exposure_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    osm_id: Mapped[str] = mapped_column(String(24))
    kind: Mapped[str] = mapped_column(String(16))  # road | building | hospital | shelter
    name: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[str] = mapped_column(String(12))  # confirmed | potential


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    risk_output_id: Mapped[int] = mapped_column(ForeignKey("risk_outputs.id"), unique=True)
    text: Mapped[str] = mapped_column(Text)
    rendered_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RankingRun(Base):
    __tablename__ = "ranking_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"))
    issue_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    weights_json: Mapped[dict] = mapped_column(JSON)
    ranked_zone_ids_json: Mapped[list] = mapped_column(JSON)


class ZoneStation(Base):
    """Which gauges serve which zone: inside the zone, else nearest within the 10 km coverage rule."""

    __tablename__ = "zone_stations"
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), primary_key=True)
    var: Mapped[str] = mapped_column(String(8))
    rank: Mapped[int] = mapped_column(Integer)  # 1 = nearest of its variable
    distance_km: Mapped[float] = mapped_column(Float)  # to the zone centroid; 0 if the gauge is inside the zone


class TidePrediction(Base):
    """NOAA astronomical tide prediction (hourly, metres NAVD). Known in advance, so it is legitimate input at issue time.

    ts is aligned to the SF2Bench clock (NOAA GMT shifted by -5 h, the assumed EST offset, ROOT_CONTEXT 2f/2i) and labelled UTC.
    """

    __tablename__ = "tide_predictions"
    noaa_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    oauth_sub: Mapped[str] = mapped_column(String(80), unique=True)  # "<provider>:<provider user id>"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    email_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Subscription(Base):
    __tablename__ = "subscriptions"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), primary_key=True)


class AlertDelivery(Base):
    """One row per alert a user was told about; (user_id, key) is unique so replays and polling never notify twice."""
    __tablename__ = "alert_deliveries"
    __table_args__ = (UniqueConstraint("user_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(12))  # replay | live
    zone_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12))  # sent | outbox | failed | muted
