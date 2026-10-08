"""In-memory snapshot of one event's rows. Filled from Postgres once, saved to a local file,
so the replay and every API read run with the DB (and network) gone.

Reads lane A's schema: gauges reach a zone through zone_stations (inside the zone, else nearest within 10 km)."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"
TIME_KEYS = {"ts", "availability_ts", "start_ts", "end_ts"}
LOOKBACK = timedelta(hours=72)  # longest rain window the ingestion agent needs
TRAIN_END = datetime(2015, 1, 1, tzinfo=timezone.utc)  # S_5 = train; thresholds never see S_6/S_7


@dataclass
class Snapshot:
    event: dict
    regions: list[dict] = field(default_factory=list)
    zones: list[dict] = field(default_factory=list)
    stations: list[dict] = field(default_factory=list)  # {id, var, zone_id, threshold}
    rows: list[dict] = field(default_factory=list)  # {station_id, ts, availability_ts, value, is_simulated}
    assets: list[dict] = field(default_factory=list)  # {zone_id, kind, name, confidence}
    model_runs: list[dict] = field(default_factory=list)
    tides: list[dict] = field(default_factory=list)  # predicted tide {noaa_id, ts, value}: astronomical, known in advance

    def zone(self, zone_id: str) -> dict:
        return next(z for z in self.zones if z["id"] == zone_id)

    def by_station(self) -> dict[int, list[dict]]:
        """Rows per station sorted by availability_ts (built once; ingestion bisects it)."""
        if not hasattr(self, "_idx"):
            idx: dict[int, list[dict]] = {}
            for r in self.rows:
                if r["value"] is not None:
                    idx.setdefault(r["station_id"], []).append(r)
            for rs in idx.values():
                rs.sort(key=lambda r: r["availability_ts"])
            self._idx = idx
        return self._idx

    def save(self) -> Path:
        CACHE_DIR.mkdir(exist_ok=True)
        path = CACHE_DIR / f"snapshot_{self.event['id']}.json"
        path.write_text(json.dumps(asdict(self), default=lambda o: o.isoformat()))
        return path

    @classmethod
    def load(cls, event_id) -> "Snapshot | None":
        path = CACHE_DIR / f"snapshot_{event_id}.json"
        if not path.exists():
            return None

        def hook(d):
            return {k: datetime.fromisoformat(v) if k in TIME_KEYS and v else v for k, v in d.items()}

        return cls(**json.loads(path.read_text(), object_hook=hook))


SQL = {
    "event": "select id, region_id, name, start_ts, end_ts, is_simulated, is_holdout, source from events where id = :e",
    "regions": "select id::text as id, name, kind, coverage_label as coverage, false as is_simulated from regions where id = :r",
    "zones": """select id, name, county, geometry, elevation_m, hand_depth_m as hand_m, coverage_class,
                       false as is_simulated from zones where region_id = :r order by id""",
    # lane A's zone_stations links each zone to its nearest gauges (not only gauges inside it); QC-failed gauges skipped
    "stations": """with linked as (
                       select zs.zone_id, s.id, s.var from zone_stations zs
                       join stations s on s.id = zs.station_id join zones z on z.id = zs.zone_id
                       where z.region_id = :r and s.qc_ok),
                   thr as (
                       select d.station_id, percentile_cont(0.95) within group (order by d.interpolated_value) as threshold  -- matches training (train/serve parity)
                       from dynamic_features d
                       where d.station_id in (select id from linked where var = 'WATER') and d.ts < :train_end
                       group by d.station_id)
                   select l.id, l.var, l.zone_id, thr.threshold from linked l left join thr on thr.station_id = l.id""",
    "rows": """select station_id, ts, availability_ts, value, is_simulated from dynamic_features
               where station_id = any(:ids) and ts >= :a and ts <= :b""",
    "assets": """select a.zone_id, a.kind, coalesce(a.name, a.kind) as name, a.confidence
                 from exposure_assets a join zones z on z.id = a.zone_id where z.region_id = :r""",
    "tides": "select noaa_id, ts, value from tide_predictions where ts >= :a and ts <= :b order by noaa_id, ts",
    "model_runs": "select model_name, version, region_id::text as region_id, metrics_json from model_runs where region_id = :r",
}


async def from_db(event_id: int) -> Snapshot:
    from sqlalchemy import text

    from app.db.session import SessionLocal

    async with SessionLocal() as s:
        async def q(name, **kw):
            res = await s.execute(text(SQL[name]), kw)
            return [dict(r._mapping) for r in res]

        ev = await q("event", e=event_id)
        if not ev:
            raise KeyError(event_id)
        ev = ev[0]
        r = ev["region_id"]
        ev["region_id"] = str(r)
        stations = await q("stations", r=r, train_end=TRAIN_END)
        zones = await q("zones", r=r)
        for z in zones:
            if isinstance(z["geometry"], str):
                z["geometry"] = json.loads(z["geometry"])
        return Snapshot(
            event=ev,
            regions=await q("regions", r=r),
            zones=zones,
            stations=stations,
            rows=await q("rows", ids=sorted({x["id"] for x in stations}), a=ev["start_ts"] - LOOKBACK, b=ev["end_ts"]),
            assets=await q("assets", r=r),
            model_runs=await q("model_runs", r=r),
            tides=await q("tides", a=ev["start_ts"] - timedelta(days=2), b=ev["end_ts"] + timedelta(days=3)),
        )
