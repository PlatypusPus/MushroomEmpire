"""Cache every event's snapshot locally so the whole demo runs with the DB unreachable.

Run from backend/ while online, before the demo:  uv run python -m scripts.precache
Writes backend/cache/snapshot_{event}.json (git-ignored). Re-run after lane A reloads data.
"""
import asyncio

from sqlalchemy import text

from app.db.session import SessionLocal
from app.store import from_db


async def main():
    async with SessionLocal() as s:
        ids = [r[0] for r in await s.execute(text("select id from events order by id"))]
    for eid in ids:
        snap = await from_db(eid)
        print(f"event {eid}: {len(snap.zones)} zones, {len(snap.rows)} rows, {len(snap.tides)} tide rows -> {snap.save()}")


if __name__ == "__main__":
    asyncio.run(main())
