"""MCP server (stdio) so Claude can query CoastGuard directly. Run: uv run python -m app.mcp_server

Add to Claude Code: claude mcp add coastguard -- uv run --directory E:/Project/backend python -m app.mcp_server
Read-only; reuses the same replay/tick/assistant/context code as the API, so answers match the dashboard.
"""
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from app import assistant, context, replay

mcp = FastMCP("coastguard")


async def _payloads(event_id: int, issue_ts: str | None):
    snap = await replay.snapshot(event_id)
    ts = datetime.fromisoformat(issue_ts) if issue_ts else snap.event["start_ts"]
    return snap, list(replay.tick(event_id, ts))  # ponytail: replay.tick is lru_cached, first call per hour runs the full pipeline


@mcp.tool()
async def top_zones(event_id: int, issue_ts: str | None = None, n: int = 10) -> list[dict]:
    """Top-n responder-priority zones at issue_ts (ISO time, default event start): probability, severity, onset, peak, rank reason."""
    snap, ps = await _payloads(event_id, issue_ts)
    names = {z["id"]: z["name"] for z in snap.zones}
    return [{"zone": names[p.zone_id], **p.model_dump(include={"zone_id", "rank", "probability", "severity", "onset", "peak", "is_alert", "coverage", "rank_reason", "explanation"}, mode="json")}
            for p in ps[:n]]


@mcp.tool()
async def zone_detail(event_id: int, zone_id: str, issue_ts: str | None = None) -> dict:
    """Full payload for one zone: risk, reasons, exposure, alert text."""
    _, ps = await _payloads(event_id, issue_ts)
    p = next((p for p in ps if p.zone_id == zone_id), None)
    return p.model_dump(mode="json") if p else {"error": f"unknown zone {zone_id}"}


@mcp.tool()
async def ask(question: str, event_id: int, issue_ts: str | None = None, zone_id: str | None = None) -> dict:
    """Ask the grounded assistant (numbers are checked against the payloads; falls back to a template if the LLM is down)."""
    snap, ps = await _payloads(event_id, issue_ts)
    return await assistant.ask(question, ps, snap.zones, snap.model_runs, zone_id, context.get_context)


@mcp.tool()
async def live_context() -> dict:
    """Live NWS alerts, NHC cyclones and weather outlook with the 0-4 hazard level (None = unavailable, never 'none')."""
    return await context.get_context()


@mcp.tool()
async def model_metrics(event_id: int) -> list[dict]:
    """Stored model runs and validation metrics for the event's region."""
    snap = await replay.snapshot(event_id)
    return [{"model": m["model_name"], "version": m["version"], "metrics": m["metrics_json"]} for m in snap.model_runs]


if __name__ == "__main__":
    mcp.run()
