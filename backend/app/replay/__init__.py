"""Replay engine: steps an issue_ts clock through one event using only data available at each tick.

Ticks are computed by the same chain the live path uses and memoised, so scrubbing re-reads
instead of recomputing (ROOT_CONTEXT 15.2). Each computed tick is also saved to backend/cache/ticks/ (gzip JSON), so a
backend restart, or the next demo, plays back instantly instead of recomputing every step while the play button runs ahead.
The file name carries a fingerprint of everything that shapes the output (snapshot, model, calibration, exposure data,
weights, CACHE_VERSION): change any of them and the old file is simply never read again."""

import gzip
import hashlib
import json
import re
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from app.orchestrator import run_tick
from app.schemas import Weights, ZonePayload
from app.store import CACHE_DIR, Snapshot, from_db

TICK_DIR = CACHE_DIR / "ticks"
CACHE_VERSION = 1  # bump when pipeline code changes what a tick contains (data and model changes are caught by the fingerprint)
_INPUTS = [Path(__file__).resolve().parents[1] / rel for rel in (
    "../models_store/lightgbm_v2.joblib", "../models_store/peak_v1.joblib", "../models_store/calibration_v2.json",
    "agents/place_exposure.json", "agents/facilities.json")]
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


def _tick_path(event_id: int, issue_ts: datetime, weights: Weights | None) -> Path:
    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    key = json.dumps([CACHE_VERSION, [mtime(p) for p in _INPUTS], mtime(CACHE_DIR / f"snapshot_{event_id}.json"),
                      (weights or Weights()).model_dump()], sort_keys=True)
    return TICK_DIR / str(event_id) / f"{issue_ts:%Y%m%dT%H%M}_{hashlib.sha1(key.encode()).hexdigest()[:12]}.json.gz"


@lru_cache(maxsize=4096)
def tick(event_id: int, issue_ts: datetime, weights: Weights | None = None) -> tuple[ZonePayload, ...]:
    path = _tick_path(event_id, issue_ts, weights)
    try:
        return tuple(ZonePayload.model_validate(d) for d in json.loads(gzip.decompress(path.read_bytes())))
    except (OSError, ValueError):
        pass  # not cached yet (or unreadable): compute it
    out = tuple(run_tick(loaded(event_id), issue_ts, weights))
    try:  # write then rename, so a crash never leaves a half file that later reads as a tick
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_bytes(gzip.compress(json.dumps([p.model_dump(mode="json") for p in out]).encode(), compresslevel=6))
        tmp.replace(path)
    except OSError:
        pass  # read-only disk: still works, just recomputes after a restart
    return out



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
