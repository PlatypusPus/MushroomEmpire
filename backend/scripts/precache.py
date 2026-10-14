"""Cache every event's snapshot locally so the whole demo runs with the DB unreachable, then compute and save every replay
step, so the play button never waits on the model.

Run from backend/ while online, before the demo:  uv run python -m scripts.precache
  --no-ticks  snapshots only (fast); the steps then get computed and saved the first time each one is played
Writes backend/cache/snapshot_{event}.json and backend/cache/ticks/ (both git-ignored). Re-run after lane A reloads data;
saved steps from older data or an older model are never read again (app.replay fingerprints them).
"""
import asyncio
import sys
import time

from sqlalchemy import text

from app import replay
from app.db.session import SessionLocal
from app.schemas import Weights
from app.store import from_db

STEP_H = 3  # the dashboard's replay step (frontend api/hooks.ts STEP_H)


async def main(with_ticks: bool):
    async with SessionLocal() as s:
        ids = [r[0] for r in await s.execute(text("select id from events order by id"))]
    for eid in ids:
        snap = await from_db(eid)
        print(f"event {eid}: {len(snap.zones)} zones, {len(snap.rows)} rows, {len(snap.tides)} tide rows -> {snap.save()}")
        if not with_ticks:
            continue
        replay._snaps[eid] = snap
        steps, t0 = replay.ticks(snap, STEP_H), time.monotonic()
        for ts in steps:
            replay.tick(eid, ts, Weights())  # dashboard default weights: read from disk if already saved
        print(f"  {len(steps)} replay steps ready in {time.monotonic() - t0:.0f} s")


if __name__ == "__main__":
    asyncio.run(main("--no-ticks" not in sys.argv))
