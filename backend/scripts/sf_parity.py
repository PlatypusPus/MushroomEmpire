"""Train/serve parity: the features ingestion serves must equal the features the model was trained on.

Run from backend/: uv run python -m scripts.sf_parity
For Nicole issue times, each zone's served level features must match the training-frame row of one of its gauges.
"""
import asyncio
import datetime as dt

import numpy as np
import pandas as pd

from app.agents.ingestion import ingest
from app.store import from_db
from scripts.sf_train import build

COLS = {"level": "level_m", "trend": "level_trend_m_per_h", "change_6h": "level_change_6h", "change_24h": "level_change_24h",
        "max_24h": "level_max_24h", "max_72h": "level_max_72h", "std_24h": "level_std_24h"}


async def main(df):
    snap = await from_db(5)
    names = {}
    for s in snap.stations:
        names.setdefault(s["zone_id"], []).append(s["id"])
    # station id -> name
    from sqlalchemy import text
    from app.db.session import SessionLocal
    async with SessionLocal() as c:
        nm = {r.id: r.name for r in (await c.execute(text("select id, name from stations"))).all()}
    issues = [dt.datetime(2022, 11, d, h, tzinfo=dt.timezone.utc) for d in (8, 9, 10, 11) for h in (0, 12)]
    rows, bad, per = 0, [], {k: [] for k in COLS}
    for it in issues:
        key = pd.Timestamp(it.replace(tzinfo=None))
        frame = df.loc[key] if key in df.index else None
        for z in snap.zones:
            fv = ingest(snap, z["id"], it)
            if fv is None or frame is None:
                continue
            cand = frame[frame.station.isin([nm[i] for i in names[z["id"]] if i in nm])]
            served = np.array([getattr(fv, v) if getattr(fv, v) is not None else np.nan for v in COLS.values()], float)
            diffs = [np.nanmax(np.abs(c[list(COLS)].astype(float).values - served)) if not np.isnan(c[list(COLS)].astype(float).values).all() else np.inf
                     for _, c in cand.iterrows()]
            rows += 1
            if len(cand):
                best = min(range(len(cand)), key=lambda i: diffs[i])
                v = cand.iloc[best][list(COLS)].astype(float).values
                for k, a, b in zip(COLS, v, served):
                    if not (np.isnan(a) and np.isnan(b)):
                        per[k].append(abs(a - b) if not (np.isnan(a) or np.isnan(b)) else np.inf)
            if not diffs or min(diffs) > 1e-6:
                bad.append((it.isoformat(), z["name"], round(min(diffs), 4) if diffs else None))
    print(f"{rows} zone-times compared; exact match to a training row: {rows - len(bad)}; mismatches: {len(bad)}")
    for k, v in per.items():
        v = np.array(v)
        print(f"  {k:11} n={len(v):4} median diff {np.median(v):.4f}  p90 {np.percentile(v[np.isfinite(v)], 90):.4f}  exact {np.mean(v < 1e-6):.0%}  one side missing {np.mean(~np.isfinite(v)):.0%}")


asyncio.run(main(build()))  # build() runs its own event loop, so it must finish first
