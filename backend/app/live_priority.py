"""Live response priority: rank South Florida's places right now, using our experimental forecast at each place's nearest live
USGS gauge (app.live_model, the model that keeps learning), then the same risk, explanation, exposure and ranking steps the
replay uses. Places with no usable gauge nearby are listed last as unknown, never as low risk.

The first run downloads each gauge's year of history (a few minutes); it runs in the background and the endpoint reports
progress. Results are reused for REFRESH_S, then recomputed in the background while the last ranking stays on screen.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from shapely.geometry import shape

from app import calibration, live_model
from app.agents.briefing import brief
from app.agents.explain import explain_zone
from app.agents.exposure import exposure
from app.agents.ranking import rank
from app.agents.risk import derive
from app.context import UA
from app.schemas import Weights, ZonePayload
from app.store import Snapshot

log = logging.getLogger("coastguard.live_priority")
PLACE_KM = 15  # a gauge further than this says little about the place
REFRESH_S = 15 * 60
PARALLEL = 4
_state: dict = {"at": 0.0, "issued": None, "running": False, "done": 0, "total": 0, "results": {}}


async def _one(c: httpx.AsyncClient, z: dict) -> dict | None:
    """Live forecast for one place, or None when no gauge within PLACE_KM has fresh readings and a usual high mark."""
    p = shape(z["geometry"]).representative_point()
    for site in (await live_model.sites_near(c, p.y, p.x, PLACE_KM))[:3]:
        thr = await live_model.threshold(c, site["id"])
        if thr is None:
            continue
        rows = await live_model.levels(c, site["id"], 4)
        rain, elev = await live_model.rain_in(c, site["lat"], site["lon"]), await live_model.elevation_m(c, site["lat"], site["lon"])
        now = datetime.now(timezone.utc)
        fv = live_model.features(site["id"], rows, rain, thr, now, elev)
        if fv is None:
            continue
        fv = fv.model_copy(update={"zone_id": z["id"], "issue_ts": now, "hand_m": z.get("hand_m")})  # the place's own height
        model, meta = live_model.champion("sf")
        traj = model.forecast(fv)
        risk = derive(traj)
        live_model.track(site)
        return {"fv": fv, "traj": traj, "risk": risk, "drivers": explain_zone(traj.drivers, fv, risk), "site": site, "version": meta.get("version")}
    return None


async def refresh(snap: Snapshot) -> None:
    if _state["running"]:
        return
    _state.update(running=True, done=0, total=len(snap.zones))
    results = {}
    try:
        sem = asyncio.Semaphore(PARALLEL)  # all 109 at once gets throttled by USGS / Open-Meteo, and every place ends up "unknown"
        async with httpx.AsyncClient(timeout=120, headers=UA, follow_redirects=True) as c:
            async def run(z):
                async with sem:
                    for attempt in range(2):  # one retry after a pause: these public services shed load now and then
                        try:
                            results[z["id"]] = await _one(c, z)
                            break
                        except (httpx.HTTPError, KeyError, ValueError) as e:
                            results[z["id"]] = None
                            log.warning("live priority: %s attempt %d failed (%s)", z["id"], attempt + 1, type(e).__name__)
                            await asyncio.sleep(3)
                _state["done"] += 1
            await asyncio.gather(*(run(z) for z in snap.zones))
        _state.update(results=results, at=time.monotonic(), issued=datetime.now(timezone.utc))
    finally:
        _state["running"] = False


def payloads(snap: Snapshot, weights: Weights) -> list[ZonePayload]:
    """Same assembly as the replay pipeline (rank known places, then unknown ones last)."""
    res, issued = _state["results"], _state["issued"]
    known = [(z, res[z["id"]]) for z in snap.zones if res.get(z["id"])]
    exp = {z["id"]: exposure(z["id"], snap.assets) for z in snap.zones}
    ranked = rank([(r["risk"], exp[z["id"]]) for z, r in known], weights)
    by = {z["id"]: (z, r) for z, r in known}
    out = []
    for i, (zid, _, reason) in enumerate(ranked, 1):
        z, r = by[zid]
        drivers, reasons, sentence = r["drivers"]
        risk, site = r["risk"], r["site"]
        out.append(ZonePayload(
            zone_id=zid, issue_ts=issued, coverage="experimental", is_simulated=False,
            probability=risk.probability, severity=risk.severity, onset=risk.onset, peak=risk.peak,
            drivers_text=drivers, reasons=reasons, explanation=sentence, exposure=exp[zid], rank=i, rank_reason=reason,
            alert_text=brief(z["name"], risk, drivers), model=f"{r['version']} · USGS {site['id']} ({site['km']} km)",
            is_alert=risk.probability >= calibration.alert_threshold(),
        ))
    for i, z in enumerate([z for z in snap.zones if not res.get(z["id"])], len(out) + 1):
        out.append(ZonePayload(
            zone_id=z["id"], issue_ts=issued, coverage="insufficient_data", is_simulated=False, probability=None, severity=None,
            onset=None, peak=None, drivers_text=[], exposure=exp[z["id"]], rank=i,
            rank_reason=f"No live water gauge within {PLACE_KM} km, check manually",
            alert_text=f"No live gauge near {z['name']}. Risk unknown.", model=None,
        ))
    return out


def status(snap: Snapshot, weights: Weights) -> dict:
    """Start a background refresh when stale; always answer at once with progress and the last ranking."""
    stale = not _state["issued"] or time.monotonic() - _state["at"] > REFRESH_S
    if stale and not _state["running"]:
        from app.accounts import spawn
        spawn(refresh(snap))
    have = _state["issued"] is not None
    return {
        "status": "ready" if have and not _state["running"] else "computing",
        "done": _state["done"], "total": _state["total"] or len(snap.zones),
        "issued": _state["issued"].isoformat() if have else None,
        "rows": [p.model_dump(mode="json") for p in payloads(snap, weights)] if have else [],
    }
