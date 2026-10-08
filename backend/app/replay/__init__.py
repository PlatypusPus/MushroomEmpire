"""Replay engine: steps an issue_ts clock through one event using only data available at each tick.

Ticks are computed by the same chain the live path uses and memoised, so scrubbing re-reads
instead of recomputing (ROOT_CONTEXT 15.2)."""

import uuid
from datetime import datetime, timedelta
from functools import lru_cache

from app.orchestrator import run_tick
from app.schemas import Weights, ZonePayload
from app.store import Snapshot, from_db

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



async def start(event_id: int, step_h: int) -> dict:
    snap = await snapshot(event_id)
    sid = uuid.uuid4().hex[:12]
    sessions[sid] = {"event_id": event_id, "ticks": ticks(snap, step_h)}
    return {"session_id": sid, "event_id": event_id, "ticks": sessions[sid]["ticks"]}
