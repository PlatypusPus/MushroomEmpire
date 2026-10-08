"""The tick as ONE LangGraph workflow (LangChain's orchestration layer): every zone through the agent chain, then ranking and assembly.

    START --fan-out (Send, one per zone)--> zone ----------------------> rank --> assemble --> END
                                              |
                  zone subgraph:  ingest -> forecast -> derive+peak -> (explain || exposure)
                                    \\-> (no usable gauge) -> exposure only      => "insufficient data", never low risk

* One compiled graph for the whole process (nodes read the snapshot from state, not from closures).
* Zones run in parallel; results are re-sorted into snapshot order before ranking, so output is deterministic.
* A zone whose agent raises is isolated: it becomes "insufficient data" with the error recorded; the tick still completes.
* Every node records wall time (`trace`), summarised per agent by `summarize()`; `astream_tick` yields progress as zones finish.
* `orchestrator.run_tick` and the replay engine call this, so there is a single code path. tests/reference_tick.py keeps the old
  plain loop to prove the payloads are identical.
"""
import logging
import operator
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from time import perf_counter
from typing import Annotated, Any, AsyncIterator, TypedDict

from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app import calibration
from app.agents.briefing import brief
from app.agents.explain import explain_zone
from app.agents.exposure import exposure
from app.agents.forecast import forecast
from app.agents.ingestion import ingest
from app.agents.peak import attach_peak
from app.agents.ranking import rank
from app.agents.risk import derive
from app.schemas import DepthTrajectory, ExposureItem, FeatureVector, RiskOutput, Weights, ZonePayload
from app.store import Snapshot

log = logging.getLogger("coastguard.pipeline")


class AgentError(RuntimeError):
    """An agent failed on one zone; carries which agent so the tick can isolate the zone and report it."""

    def __init__(self, agent: str, zone_id: str, cause: Exception):
        super().__init__(f"{agent} failed for zone {zone_id}: {type(cause).__name__}: {cause}")
        self.agent, self.zone_id, self.cause = agent, zone_id, cause


class ZoneState(TypedDict, total=False):
    snap: Snapshot
    issue_ts: datetime
    zone_id: str
    fv: FeatureVector | None
    traj: DepthTrajectory
    risk: RiskOutput
    drivers: tuple  # (phrases, reasons, sentence) from explain_zone
    exp: list[ExposureItem]
    trace: Annotated[list[dict], operator.add]


class TickState(TypedDict, total=False):
    snap: Snapshot
    issue_ts: datetime
    weights: Weights
    zone_results: Annotated[list[dict], operator.add]
    ordered: list[dict]  # zone results in snapshot order (zone_results arrive in any order and append)
    ranked: list[tuple]
    payloads: list[ZonePayload]


def _agent(name: str):
    """Wrap a node: time it, and re-raise failures as AgentError(name, zone)."""
    def deco(fn):
        @wraps(fn)
        def node(s: ZoneState) -> dict:
            t = perf_counter()
            try:
                out = fn(s)
            except Exception as e:
                raise AgentError(name, s["zone_id"], e) from e
            return {**out, "trace": [{"agent": name, "zone": s["zone_id"], "ms": round((perf_counter() - t) * 1000, 3)}]}
        return RunnableLambda(node).with_config(run_name=name)  # a LangChain Runnable: shows up by name in callbacks and astream_events
    return deco


@_agent("ingestion")
def n_ingest(s: ZoneState) -> dict:
    return {"fv": ingest(s["snap"], s["zone_id"], s["issue_ts"])}


@_agent("forecasting")
def n_forecast(s: ZoneState) -> dict:
    return {"traj": forecast(s["fv"])}


@_agent("risk+peak")
def n_derive(s: ZoneState) -> dict:
    return {"risk": attach_peak(derive(s["traj"]), s["traj"], s["fv"], s["snap"])}


@_agent("explainability")
def n_explain(s: ZoneState) -> dict:
    return {"drivers": explain_zone(s["traj"].drivers, s["fv"], s["risk"])}


@_agent("exposure")
def n_exposure(s: ZoneState) -> dict:
    return {"exp": exposure(s["zone_id"], s["snap"].assets)}


def _build_zone_graph():
    g = StateGraph(ZoneState)
    for name, fn in (("ingest", n_ingest), ("forecast", n_forecast), ("derive", n_derive), ("explain", n_explain), ("exposure", n_exposure)):
        g.add_node(name, fn)
    g.add_edge(START, "ingest")
    g.add_conditional_edges("ingest", lambda s: "forecast" if s.get("fv") is not None else "exposure", ["forecast", "exposure"])
    g.add_edge("forecast", "derive")
    g.add_edge("derive", "explain")  # fan-out: explain and exposure run in parallel
    g.add_edge("derive", "exposure")
    g.add_edge("explain", END)
    g.add_edge("exposure", END)
    return g.compile()


ZONE_GRAPH = _build_zone_graph()


def zone_node(s: dict) -> dict:
    """Run one zone through the subgraph; isolate any failure to this zone."""
    z = s["snap"].zone(s["zone_id"])
    try:
        out = ZONE_GRAPH.invoke({"snap": s["snap"], "issue_ts": s["issue_ts"], "zone_id": s["zone_id"], "trace": []})
        res = {"zone": z, "fv": out.get("fv"), "traj": out.get("traj"), "risk": out.get("risk"), "drivers": out.get("drivers"),
               "exp": out.get("exp", []), "trace": out["trace"], "error": None}
    except AgentError as e:
        log.warning("%s", e)
        res = {"zone": z, "fv": None, "exp": exposure(z["id"], s["snap"].assets), "trace": [], "error": {"agent": e.agent, "zone": z["id"], "message": str(e)}}
    return {"zone_results": [res]}


def fan_out(s: TickState):
    s["snap"].by_station()  # build the lazy per-station index once, before the zone threads share it
    return [Send("zone", {"snap": s["snap"], "issue_ts": s["issue_ts"], "zone_id": z["id"]}) for z in s["snap"].zones]


def rank_node(s: TickState) -> dict:
    order = {z["id"]: i for i, z in enumerate(s["snap"].zones)}  # parallel zones finish in any order: restore snapshot order
    res = sorted(s["zone_results"], key=lambda r: order[r["zone"]["id"]])
    known = [r for r in res if r["fv"] is not None]
    ranked = rank([(r["risk"], r["exp"]) for r in known], s.get("weights") or Weights())
    return {"ranked": ranked, "ordered": res}


def assemble_node(s: TickState) -> dict:
    snap, issue_ts = s["snap"], s["issue_ts"]
    region = snap.regions[0]
    by_id = {r["zone"]["id"]: r for r in s["ordered"]}
    out: list[ZonePayload] = []
    for i, (zid, _, reason) in enumerate(s["ranked"], 1):
        r = by_id[zid]
        z, fv, traj, risk = r["zone"], r["fv"], r["traj"], r["risk"]
        drivers, reasons, sentence = r["drivers"]
        simulated = fv.is_simulated or z["is_simulated"] or snap.event["is_simulated"]
        out.append(ZonePayload(
            zone_id=zid, issue_ts=issue_ts, coverage="simulation" if simulated else region["coverage"], is_simulated=simulated,
            probability=risk.probability, severity=risk.severity, onset=risk.onset, peak=risk.peak,
            drivers_text=drivers, reasons=reasons, explanation=sentence, exposure=r["exp"], rank=i, rank_reason=reason,
            alert_text=brief(z["name"], risk, drivers), model=traj.model,
            is_alert=risk.probability >= calibration.alert_threshold(),  # Lane B's validated alert rule
        ))
    # unknown is never low risk: ranked after, flagged, no probability
    for i, r in enumerate([r for r in s["ordered"] if r["fv"] is None], len(out) + 1):
        z = r["zone"]
        out.append(ZonePayload(
            zone_id=z["id"], issue_ts=issue_ts, coverage="insufficient_data", is_simulated=z["is_simulated"] or snap.event["is_simulated"],
            probability=None, severity=None, onset=None, peak=None, drivers_text=[], exposure=r["exp"], rank=i,
            rank_reason="Forecast failed for this zone, check manually" if r["error"] else "Insufficient or stale data, check manually",
            alert_text=f"Insufficient data, {z['name']}. Risk unknown.", model=None,
        ))
    return {"payloads": out}


def _build_tick_graph():
    g = StateGraph(TickState)
    g.add_node("zone", zone_node)
    g.add_node("rank", rank_node)
    g.add_node("assemble", assemble_node)
    g.add_conditional_edges(START, fan_out, ["zone"])
    g.add_edge("zone", "rank")  # waits for every zone, then ranks across them
    g.add_edge("rank", "assemble")
    g.add_edge("assemble", END)
    return g.compile()


TICK_GRAPH = _build_tick_graph()


@dataclass
class TickResult:
    payloads: list[ZonePayload]
    trace: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def _initial(snap: Snapshot, issue_ts: datetime, weights: Weights | None) -> dict:
    return {"snap": snap, "issue_ts": issue_ts, "weights": weights or Weights(), "zone_results": []}


MAX_PARALLEL_ZONES = 4  # zones are CPU-bound Python + LightGBM: more threads only add contention


def run_tick_traced(snap: Snapshot, issue_ts: datetime, weights: Weights | None = None) -> TickResult:
    out = TICK_GRAPH.invoke(_initial(snap, issue_ts, weights), config={"max_concurrency": MAX_PARALLEL_ZONES})
    res = out["zone_results"]
    return TickResult(payloads=out["payloads"], trace=[t for r in res for t in r["trace"]], errors=[r["error"] for r in res if r["error"]])


def run_tick(snap: Snapshot, issue_ts: datetime, weights: Weights | None = None) -> list[ZonePayload]:
    return run_tick_traced(snap, issue_ts, weights).payloads


async def astream_tick(snap: Snapshot, issue_ts: datetime, weights: Weights | None = None) -> AsyncIterator[dict]:
    """Progress events as zones finish: {"event": "zone", ...}, then {"event": "ranked"}, then {"event": "done", "payloads": [...]}."""
    total, done = len(snap.zones), 0
    async for chunk in TICK_GRAPH.astream(_initial(snap, issue_ts, weights), config={"max_concurrency": MAX_PARALLEL_ZONES}, stream_mode="updates"):
        for node, upd in chunk.items():
            if node == "zone":
                r = upd["zone_results"][0]
                done += 1
                yield {"event": "zone", "zone_id": r["zone"]["id"], "done": done, "total": total, "ok": r["error"] is None,
                       "usable": r["fv"] is not None, "ms": round(sum(t["ms"] for t in r["trace"]), 2)}
            elif node == "rank":
                yield {"event": "ranked", "zones": len(upd["ranked"])}
            elif node == "assemble":
                yield {"event": "done", "payloads": upd["payloads"]}


def summarize(trace: list[dict]) -> dict[str, dict]:
    """Per-agent calls and milliseconds from a tick's trace."""
    out: dict[str, dict[str, Any]] = {}
    for t in trace:
        a = out.setdefault(t["agent"], {"calls": 0, "total_ms": 0.0, "max_ms": 0.0})
        a["calls"] += 1
        a["total_ms"] = round(a["total_ms"] + t["ms"], 3)
        a["max_ms"] = max(a["max_ms"], t["ms"])
    for a in out.values():
        a["mean_ms"] = round(a["total_ms"] / a["calls"], 3)
    return out


def diagram() -> str:
    """Mermaid source of the two graphs, for docs and the UI."""
    return "%% tick\n" + TICK_GRAPH.get_graph().draw_mermaid() + "\n%% zone subgraph\n" + ZONE_GRAPH.get_graph().draw_mermaid()
