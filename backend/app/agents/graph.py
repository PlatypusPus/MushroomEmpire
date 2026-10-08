"""Compatibility wrappers over app/pipeline.py (the single LangGraph workflow). Kept so older imports and tests keep working."""

from datetime import datetime

from app.pipeline import ZONE_GRAPH, ZoneState, run_tick as run_tick_graph  # noqa: F401
from app.store import Snapshot


def run_zone(snap: Snapshot, zone_id: str, issue_ts: datetime) -> ZoneState:
    """One zone through the zone subgraph. Missing fv (= unknown zone) ends after ingest + exposure."""
    return ZONE_GRAPH.invoke({"snap": snap, "issue_ts": issue_ts, "zone_id": zone_id, "trace": []})
