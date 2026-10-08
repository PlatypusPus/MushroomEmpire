"""Replay engine: steps an issue_ts clock through one event using only data available at each tick.

Ticks are computed by the same chain the live path uses and memoised, so scrubbing re-reads
instead of recomputing (ROOT_CONTEXT 15.2)."""

import threading
import uuid
from datetime import datetime, timedelta
from functools import lru_cache

from app.orchestrator import run_tick
from app.schemas import Weights, ZonePayload
from app.store import Snapshot, from_db

REFIRE_AFTER = timedelta(hours=24)  # a zone alerts again only after this long off alert
_feed_lock = threading.Lock()
_snaps: dict[int, Snapshot] = {}
sessions: dict[str, dict] = {}


async def snapshot(event_id: int) -> Snapshot:
    """Local cache file first (offline demo), else Postgres once, then saved locally."""
    if event_id not in _snaps:
        snap = Snapshot.load(event_id)
        if snap is None:
            snap = await from_db(event_id)
            snap.save()
        _snaps[event_id] = snap
    return _snaps[event_id]


def loaded(event_id: int) -> Snapshot:
    if event_id not in _snaps:
        raise KeyError(event_id)
    return _snaps[event_id]


def ticks(snap: Snapshot, step_h: int) -> list[datetime]:
    t, end, out = snap.event["start_ts"], snap.event["end_ts"], []
    while t <= end:
        out.append(t)
        t += timedelta(hours=step_h)
    return out


@lru_cache(maxsize=4096)
def tick(event_id: int, issue_ts: datetime, weights: Weights | None = None) -> tuple[ZonePayload, ...]:
    return tuple(run_tick(loaded(event_id), issue_ts, weights))



def alert_feed(session_id: str, upto: int) -> list[dict]:
    """Alerts that FIRED up to tick `upto`: a zone enters the feed on the tick it crosses into alert. Newest first."""
    sess = sessions[session_id]
    # computed once per session and only extended: scrubbing back just filters, never recomputes
    st = sess.setdefault("alerts", {"done": -1, "feed": [], "last_on": {}})  # last_on: zone -> last tick on alert
    with _feed_lock:  # requests run in worker threads; extend the feed one at a time
        _extend(sess, st, upto)
    now = sess["ticks"][min(upto, len(sess["ticks"]) - 1)]
    return [a for a in st["feed"] if a["issue_ts"] <= now][::-1]


def _extend(sess: dict, st: dict, upto: int) -> None:
    for i in range(st["done"] + 1, min(upto, len(sess["ticks"]) - 1) + 1):
        ts = sess["ticks"][i]
        for z in tick(sess["event_id"], ts):
            if not z.is_alert:
                continue
            # zones hover near the threshold; re-fire only after a full quiet period, not on every flicker
            if z.zone_id not in st["last_on"] or ts - st["last_on"][z.zone_id] > REFIRE_AFTER:
                st["feed"].append({"issue_ts": ts, "zone_id": z.zone_id, "alert_text": z.alert_text,
                                   "probability": z.probability, "severity": z.severity, "is_simulated": z.is_simulated})
            st["last_on"][z.zone_id] = ts
        st["done"] = i


async def start(event_id: int, step_h: int) -> dict:
    snap = await snapshot(event_id)
    sid = uuid.uuid4().hex[:12]
    sessions[sid] = {"event_id": event_id, "ticks": ticks(snap, step_h)}
    # warm every tick (and the alert feed) in the background so playback never waits on the model
    threading.Thread(target=alert_feed, args=(sid, len(sessions[sid]["ticks"]) - 1), daemon=True).start()
    return {"session_id": sid, "event_id": event_id, "ticks": sessions[sid]["ticks"]}
