"""Regenerate samples/zone_payloads_nicole.json from the live pipeline (needs the DB): uv run python -m scripts.sf_samples"""
import asyncio
import datetime as dt
import json

from app import calibration
from app.agents.briefing_io import briefing_input
from app.agents.forecast import forecast
from app.agents.ingestion import ingest
from app.agents.risk import derive
from app.orchestrator import run_tick
from app.schemas import ZonePayload
from app.store import from_db


async def main():
    snap = await from_db(5)
    issue = dt.datetime(2022, 11, 9, 12, tzinfo=dt.timezone.utc)
    zn = {x["id"]: x["name"] for x in snap.zones}
    pl = run_tick(snap, issue)
    d = [p.model_dump(mode="json") for p in pl]
    by_status = {}
    for p in sorted(d, key=lambda p: p["rank"]):
        st = briefing_input(ZonePayload(**p), zn[p["zone_id"]])["status"]
        by_status.setdefault(st, p)
    top = sorted(d, key=lambda p: p["rank"])[0]
    fv = ingest(snap, top["zone_id"], issue)
    t = forecast(fv)
    out = {"issue_ts": issue.isoformat(), "event": snap.event["name"], "alert_threshold": calibration.alert_threshold(),
           "counts": {"zones": len(d), "forecast": sum(p["probability"] is not None for p in d)},
           "example_top_zone": {"zone_name": zn[top["zone_id"]], "feature_vector": fv.model_dump(mode="json"),
                                "trajectory_first_and_last_steps": [t.steps[0].model_dump(mode="json"), t.steps[-1].model_dump(mode="json")],
                                "trajectory_model": t.model, "drivers_raw": [x.model_dump() for x in t.drivers[:5]],
                                "risk": derive(t).model_dump(mode="json"), "zone_payload": top},
           "by_status": {st: {"zone_name": zn[p["zone_id"]], "zone_payload": p} for st, p in by_status.items()}}
    json.dump(out, open("samples/zone_payloads_nicole.json", "w"), indent=1)
    print({st: (v["zone_name"], v["zone_payload"]["probability"]) for st, v in out["by_status"].items()})


asyncio.run(main())
