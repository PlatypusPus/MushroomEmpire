"""Replay engine: steps an issue_ts clock through one event using only data available at each tick.

Ticks are computed by the same chain the live path uses and memoised, so scrubbing re-reads
instead of recomputing (ROOT_CONTEXT 15.2)."""

import re
import threading
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
    upto = min(upto, len(sess["ticks"]) - 1)
    while st["done"] < upto:
        i = st["done"] + 1
        zones = tick(sess["event_id"], sess["ticks"][i])  # the slow model work, outside the lock (memoised)
        with _feed_lock:  # held only to append, so a request never starves behind the warm-up thread
            if st["done"] == i - 1:
                _append(sess, st, i, zones)
    now = sess["ticks"][upto]
    return [a for a in st["feed"] if a["issue_ts"] <= now][::-1]


def _append(sess: dict, st: dict, i: int, zones: tuple[ZonePayload, ...]) -> None:
    ts = sess["ticks"][i]
    for z in zones:
        if not z.is_alert:
            continue
        # zones hover near the threshold; re-fire only after a full quiet period, not on every flicker
        if z.zone_id not in st["last_on"] or ts - st["last_on"][z.zone_id] > REFIRE_AFTER:
            st["feed"].append({"issue_ts": ts, "zone_id": z.zone_id, "alert_text": z.alert_text,
                               "probability": z.probability, "severity": z.severity, "is_simulated": z.is_simulated})
        st["last_on"][z.zone_id] = ts
    st["done"] = i


async def start(event_id: int, step_h: int) -> dict:
    """Session id is derived from (event, step), so a browser tab survives a backend restart and repeat starts share one warm-up."""
    sid = f"e{event_id}-s{step_h}"
    if sid not in sessions:
        snap = await snapshot(event_id)
        sessions[sid] = {"event_id": event_id, "ticks": ticks(snap, step_h)}
        # warm every tick (and the alert feed) in the background so playback never waits on the model
        threading.Thread(target=alert_feed, args=(sid, len(sessions[sid]["ticks"]) - 1), daemon=True).start()
    return {"session_id": sid, "event_id": event_id, "ticks": sessions[sid]["ticks"]}


async def ensure(session_id: str) -> bool:
    """Recreate a session from its id after a restart (ids look like e5-s3). False if the id is not ours."""
    if session_id in sessions:
        return True
    m = re.fullmatch(r"e(\d+)-s(\d+)", session_id)
    if not m:
        return False
    try:
        await start(int(m[1]), int(m[2]))
    except KeyError:  # unknown event
        return False
    return True
