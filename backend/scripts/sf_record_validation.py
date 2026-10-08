"""Attach the validation and calibration results to the live model_runs row (read by GET /api/models/{region}/metrics).

Run from backend/: uv run python -m scripts.sf_record_validation
"""
import asyncio
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

PROC = Path(__file__).resolve().parents[2] / "data" / "processed"


async def main():
    parts = {"validation": PROC / "metrics_validation_v2.json", "spatial": PROC / "metrics_spatial_v2.json", "features": PROC / "metrics_feature_study.json", "horizons": PROC / "metrics_horizons_v2.json"}
    eng = create_async_engine(settings.database_url)
    async with eng.begin() as c:
        row = (await c.execute(text("select id, metrics_json from model_runs where model_name = 'lightgbm-quantile' and version = 'v2'"))).first()
        m = row.metrics_json if isinstance(row.metrics_json, dict) else json.loads(row.metrics_json)
        for k, p in parts.items():
            if p.exists():
                m[k] = json.loads(p.read_text())
        await c.execute(text("update model_runs set metrics_json = cast(:m as json) where id = :i"), {"m": json.dumps(m), "i": row.id})
    print("updated model_runs", row.id, "with", [k for k in parts if (PROC / parts[k].name).exists()])
    await eng.dispose()

asyncio.run(main())
