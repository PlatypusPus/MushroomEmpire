"""Load NOAA predicted tide (data/raw/noaa/*_predictions.csv) into tide_predictions, aligned to the SF2Bench clock.

Run from backend/: uv run python -m scripts.sf_load_tide     (idempotent: replaces the table contents)
"""
import asyncio
from datetime import timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tqdm import tqdm

from app.config import settings

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "noaa"
TZ_SHIFT_H = -5  # SF2Bench clock minus NOAA GMT (assumed fixed EST, ROOT_CONTEXT item 2i)


async def main():
    eng = create_async_engine(settings.database_url)
    async with eng.begin() as c:
        await c.execute(text("TRUNCATE tide_predictions"))
        raw = await c.get_raw_connection()
        for f in sorted(RAW.glob("*_predictions.csv")):
            sid = f.name.split("_")[0]
            d = pd.read_csv(f, usecols=["t", "v"])
            d["t"] = pd.to_datetime(d.t) + pd.Timedelta(hours=TZ_SHIFT_H)
            d = d.drop_duplicates("t")
            recs = [(sid, t.to_pydatetime().replace(tzinfo=timezone.utc), None if pd.isna(v) else float(v)) for t, v in zip(d.t, pd.to_numeric(d.v, errors="coerce"))]
            for i in tqdm(range(0, len(recs), 50000), desc=sid):
                await raw.driver_connection.copy_records_to_table("tide_predictions", records=recs[i:i + 50000], columns=["noaa_id", "ts", "value"])
            print(sid, len(recs), "rows")
    await eng.dispose()

asyncio.run(main())
