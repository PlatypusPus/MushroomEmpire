"""LangGraph multi-agent chain: one per-zone graph over the existing agents.

Order mirrors orchestrator.run_tick: ingest -> forecast -> derive, then
explain and exposure fan out in parallel and rejoin. Cross-zone ranking and
briefing stay in the driver (they need every zone's output first), exactly as
in run_tick. The agents themselves are untouched pure functions; the graph
only sequences them, so `test_graph_parity` guards against drift.
"""

from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.briefing import brief
from app.agents.explain import explain_zone
from app.agents.peak import attach_peak
from app.agents.exposure import exposure
from app.agents.forecast import forecast
from app.agents.ingestion import ingest
from app.agents.ranking import rank
from app.agents.risk import derive
from app.schemas import (
    DepthTrajectory,
    ExposureItem,
    FeatureVector,
    RiskOutput,
    Weights,
    ZonePayload,
)
from app.store import Snapshot


class ZoneState(TypedDict, total=False):
    zone_id: str
    fv: FeatureVector | None
    traj: DepthTrajectory
    risk: RiskOutput
    drivers: tuple  # (phrases, reasons, sentence) from explain_zone
    exp: list[ExposureItem]


def build_zone_graph(snap: Snapshot, issue_ts: datetime):
    """Per-zone chain. snap/issue_ts ride in node closures (no checkpointer)."""

    def n_ingest(s: ZoneState) -> dict:
        return {"fv": ingest(snap, s["zone_id"], issue_ts)}

    def n_forecast(s: ZoneState) -> dict:
        assert s["fv"] is not None
        return {"traj": forecast(s["fv"])}

    def n_derive(s: ZoneState) -> dict:
        return {"risk": attach_peak(derive(s["traj"]), s["traj"], s["fv"], snap)}

    def n_explain(s: ZoneState) -> dict:
        return {"drivers": explain_zone(s["traj"].drivers, s["fv"], s["risk"])}

    def n_exposure(s: ZoneState) -> dict:
        return {"exp": exposure(s["zone_id"], snap.assets)}

    g = StateGraph(ZoneState)
    g.add_node("ingest", n_ingest)
    g.add_node("forecast", n_forecast)
    g.add_node("derive", n_derive)
    g.add_node("explain", n_explain)
    g.add_node("exposure", n_exposure)
    g.set_entry_point("ingest")
    g.add_conditional_edges(
        "ingest",
        lambda s: "forecast" if s.get("fv") is not None else "exposure",
    )
    g.add_edge("forecast", "derive")
    g.add_edge("derive", "explain")  # fan-out: explain and exposure run in parallel
    g.add_edge("derive", "exposure")
    g.add_edge("explain", END)
    g.add_edge("exposure", END)
    return g.compile()


def run_zone(snap: Snapshot, zone_id: str, issue_ts: datetime) -> ZoneState:
    """One zone through the graph. Missing fv (= unknown zone) ends after ingest."""
    return build_zone_graph(snap, issue_ts).invoke({"zone_id": zone_id})


def run_tick_graph(
    snap: Snapshot, issue_ts: datetime, weights: Weights | None = None
) -> list[ZonePayload]:
    """Same contract as orchestrator.run_tick, assembled from graph outputs."""
    region = snap.regions[0]
    known, unknown = [], []
    for z in snap.zones:
        out = run_zone(snap, z["id"], issue_ts)
        if out.get("fv") is None:
            unknown.append((z, out["exp"]))
        else:
            known.append((z, out["fv"], out["traj"], out["risk"], out["drivers"], out["exp"]))

    order = rank([(k[3], k[5]) for k in known], weights or Weights())
    by_id = {k[0]["id"]: k for k in known}
    payloads = []
    for i, (zid, _, reason) in enumerate(order, 1):
        z, fv, traj, risk, (drivers, reasons, sentence), exp = by_id[zid]
        simulated = fv.is_simulated or z["is_simulated"] or snap.event["is_simulated"]
        payloads.append(ZonePayload(
            zone_id=zid, issue_ts=issue_ts,
            coverage="simulation" if simulated else region["coverage"],
            is_simulated=simulated,
            probability=risk.probability, severity=risk.severity, onset=risk.onset, peak=risk.peak,
            drivers_text=drivers, reasons=reasons, explanation=sentence, exposure=exp, rank=i, rank_reason=reason,
            alert_text=brief(z["name"], risk, drivers), model=traj.model,
        ))
    for i, (z, exp) in enumerate(unknown, len(payloads) + 1):
        payloads.append(ZonePayload(
            zone_id=z["id"], issue_ts=issue_ts, coverage="insufficient_data",
            is_simulated=z["is_simulated"] or snap.event["is_simulated"],
            probability=None, severity=None, onset=None, peak=None, drivers_text=[], exposure=exp,
            rank=i, rank_reason="Insufficient or stale data, check manually",
            alert_text=f"Insufficient data, {z['name']}. Risk unknown.", model=None,
        ))
    return payloads
