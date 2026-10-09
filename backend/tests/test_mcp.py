import asyncio
import json

from test_backend import synthetic_snapshot

from app import mcp_server, replay


def test_mcp_tools_listed_and_top_zones_work():
    replay._snaps[995] = synthetic_snapshot()

    async def go():
        names = {t.name for t in await mcp_server.mcp.list_tools()}
        _, out = await mcp_server.mcp.call_tool("top_zones", {"event_id": 995, "n": 2})
        return names, out

    names, out = asyncio.run(go())
    assert names == {"top_zones", "zone_detail", "ask", "live_context", "model_metrics", "live_priority", "live_forecast", "advice_at"}
    assert len(json.loads(json.dumps(out))["result"]) == 2


def test_mcp_live_priority_reports_progress_without_blocking(monkeypatch):
    from app import live_priority as lp
    from app.config import settings

    replay._snaps[995] = synthetic_snapshot()
    monkeypatch.setattr(settings, "default_event_id", 995)
    monkeypatch.setattr("app.accounts.spawn", lambda coro: coro.close())  # no network in tests
    monkeypatch.setattr(lp, "_state", {"at": 0.0, "issued": None, "running": False, "done": 0, "total": 0, "results": {}})
    out = asyncio.run(mcp_server.mcp.call_tool("live_priority", {"n": 3}))
    res = out[1] if isinstance(out, tuple) else json.loads(out[0].text)  # dict-returning tools come back as text content
    assert res["status"] == "computing" and res["top"] == [] and res["total"] == 3
