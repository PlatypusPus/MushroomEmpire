"""Ingestion agent: feature vector per zone, using only rows available at issue time."""

from bisect import bisect_right
from statistics import stdev
from datetime import datetime, timedelta

from app.schemas import FeatureVector
from app.store import Snapshot

STALE_AFTER = timedelta(hours=6)


def visible(snap: Snapshot, station_ids: set[int], issue_ts: datetime) -> dict[int, list[dict]]:
    """The leakage guard: nothing whose availability_ts is after issue_ts."""
    idx = snap.by_station()
    out = {}
    for sid in station_ids:
        rs = idx.get(sid, [])
        cut = bisect_right(rs, issue_ts, key=lambda r: r["availability_ts"])
        out[sid] = sorted(rs[:cut], key=lambda r: r["ts"])
    return out


def history(rs: list[dict], thr: float) -> dict:
    """Level history of one gauge from its visible rows (same definitions as the training features; None = too few readings)."""
    now = rs[-1]["ts"]
    lv = [(r["ts"], r["value"] - thr) for r in rs if r["ts"] > now - timedelta(hours=72)]

    def at(h):  # latest level at or before now - h
        old = [v for t, v in lv if t <= now - timedelta(hours=h)]
        return old[-1] if old else None

    cur = lv[-1][1]
    d24 = [v for t, v in lv if t > now - timedelta(hours=24)]
    return {
        "level_change_6h": None if at(6) is None else cur - at(6),
        "level_change_24h": None if at(24) is None else cur - at(24),
        "level_max_24h": max(d24) if len(d24) >= 12 else None,
        "level_max_72h": max(v for _, v in lv) if len(lv) >= 36 else None,
        "level_std_24h": stdev(d24) if len(d24) >= 12 else None,
    }


def ingest(snap: Snapshot, zone_id: str, issue_ts: datetime) -> FeatureVector | None:
    """None means no usable water-level gauge (missing or stale); never treat that as low risk."""
    st = [s for s in snap.stations if s["zone_id"] == zone_id]
    water = {s["id"]: s["threshold"] for s in st if s["var"] == "WATER" and s["threshold"] is not None}
    rain_ids = {s["id"] for s in st if s["var"] == "RAIN"}
    rows = visible(snap, set(water) | rain_ids, issue_ts)

    # zone level = its worst gauge relative to that gauge's own train-only q95
    best = None
    for sid, thr in water.items():
        rs = rows.get(sid)
        if not rs or rs[-1]["ts"] < issue_ts - STALE_AFTER:
            continue
        now = rs[-1]
        before = [r for r in rs if r["ts"] <= now["ts"] - timedelta(hours=3)]
        trend = (now["value"] - before[-1]["value"]) / 3 if before else 0.0
        cand = (now["value"] - thr, trend, rs, thr)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is None:
        return None

    def rain(h):  # mean over the zone's rain gauges; None if the zone has none
        sums = [sum(r["value"] for r in rows.get(s, []) if r["ts"] > issue_ts - timedelta(hours=h)) for s in rain_ids]
        return sum(sums) / len(sums) if sums else None

    zone = snap.zone(zone_id)
    used = best[2] + [r for s in rain_ids for r in rows.get(s, [])]
    return FeatureVector(
        zone_id=zone_id, issue_ts=issue_ts, level_m=best[0], level_trend_m_per_h=best[1],
        rain_6h=rain(6), rain_24h=rain(24), rain_72h=rain(72),
        hand_m=zone["hand_m"], elevation_m=zone["elevation_m"],
        is_simulated=any(r["is_simulated"] for r in used), **history(best[2], best[3]),
    )
