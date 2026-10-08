"""Gauge QC screen for WATER gauges (run before zone_stations and training).

Run from backend/: uv run python -m scripts.sf_gauge_qc
Fails a gauge if it is stuck > 2000 h, > 20% missing, or has a single-hour jump > 10 units (SF2Bench units).
Writes data/processed/sf_gauge_qc.csv and stations.qc_ok / qc_reason in Postgres.
"""
import asyncio
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

ROOT = Path(__file__).resolve().parents[2] / "data" / "processed"
FLAT_H, MISSING, JUMP = 2000, 0.20, 10

h = pd.read_parquet(ROOT / "sf_hourly.parquet", columns=["station", "var", "ts", "value", "interp"])
w = h[h["var"] == "WATER"]
V = w.pivot(index="ts", columns="station", values="value").sort_index()
I = w.pivot(index="ts", columns="station", values="interp").sort_index()
qc = pd.DataFrame({"missing_share": V.isna().mean(), "max_jump": I.diff().abs().max(),
                   "longest_flat_h": I.apply(lambda s: s.groupby((s != s.shift()).cumsum()).transform("size").max())})
reason = []
for r in qc.itertuples():
    why = [m for bad, m in ((r.longest_flat_h > FLAT_H, f"stuck {int(r.longest_flat_h)} h"), (r.missing_share > MISSING, f"{r.missing_share:.0%} missing"),
                            (r.max_jump > JUMP, f"jump {r.max_jump:.1f}")) if bad]
    reason.append("; ".join(why) or None)
qc["qc_reason"], qc["qc_ok"] = reason, [x is None for x in reason]
qc.round(3).to_csv(ROOT / "sf_gauge_qc.csv")
print(f"{(~qc.qc_ok).sum()} of {len(qc)} WATER gauges fail QC")
print(qc[~qc.qc_ok][["qc_reason"]].to_string())


async def push():
    eng = create_async_engine(settings.database_url)
    async with eng.begin() as c:
        await c.execute(text("update stations set qc_ok = true, qc_reason = null where var = 'WATER'"))
        await c.execute(text("update stations set qc_ok = false, qc_reason = :r where var = 'WATER' and name = :n"),
                        [{"n": n, "r": r} for n, r in qc.qc_reason.dropna().items()])
    await eng.dispose()

asyncio.run(push())
