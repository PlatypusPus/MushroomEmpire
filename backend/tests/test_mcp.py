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
    assert names == {"top_zones", "zone_detail", "ask", "live_context", "model_metrics"}
    assert len(json.loads(json.dumps(out))["result"]) == 2
