"""Orchestrator: runs the agent chain for every zone at one issue time."""

from datetime import datetime

from app import calibration
from app.agents.briefing import brief
from app.agents.explain import explain_zone
from app.agents.peak import attach_peak
from app.agents.exposure import exposure
from app.agents.forecast import forecast
from app.agents.ingestion import ingest
from app.agents.ranking import rank
from app.agents.risk import derive
from app.schemas import Weights, ZonePayload
from app.store import Snapshot


def run_tick(snap: Snapshot, issue_ts: datetime, weights: Weights | None = None) -> list[ZonePayload]:
    """-> one payload per zone, ordered by rank. Ingestion -> forecast -> risk -> explain, exposure -> rank -> brief."""
    region = snap.regions[0]
    known, unknown = [], []
    for z in snap.zones:
        exp = exposure(z["id"], snap.assets)
        fv = ingest(snap, z["id"], issue_ts)
        if fv is None:
            unknown.append((z, exp))
            continue
        traj = forecast(fv)
        risk = attach_peak(derive(traj), traj, fv, snap)
        known.append((z, fv, traj, risk, explain_zone(traj.drivers, fv, risk), exp))

    order = rank([(k[3], k[5]) for k in known], weights or Weights())
    by_id = {k[0]["id"]: k for k in known}
    out = []
    for i, (zid, _, reason) in enumerate(order, 1):
        z, fv, traj, risk, (drivers, reasons, sentence), exp = by_id[zid]
        simulated = fv.is_simulated or z["is_simulated"] or snap.event["is_simulated"]
        out.append(ZonePayload(
            zone_id=zid, issue_ts=issue_ts,
            coverage="simulation" if simulated else region["coverage"],
            is_simulated=simulated,
            probability=risk.probability, severity=risk.severity, onset=risk.onset, peak=risk.peak,
            drivers_text=drivers, reasons=reasons, explanation=sentence, exposure=exp, rank=i, rank_reason=reason,
            alert_text=brief(z["name"], risk, drivers), model=traj.model,
            is_alert=risk.probability >= calibration.alert_threshold(),
        ))
    # unknown is never low risk: ranked after, flagged, no probability
    for i, (z, exp) in enumerate(unknown, len(out) + 1):
        out.append(ZonePayload(
            zone_id=z["id"], issue_ts=issue_ts, coverage="insufficient_data",
            is_simulated=z["is_simulated"] or snap.event["is_simulated"],
            probability=None, severity=None, onset=None, peak=None, drivers_text=[], exposure=exp,
            rank=i, rank_reason="Insufficient or stale data, check manually",
            alert_text=f"Insufficient data, {z['name']}. Risk unknown.", model=None,
        ))
    return out
