import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router, ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the default tick, the top-zone briefing and the chat model once, so
    the first dashboard load, first zone click and first chat question are warm."""
    try:
        from app import replay
        from app.config import settings
        from app.schemas import Weights

        snap = await replay.snapshot(settings.default_event_id)
        # Same key the dashboard, briefing and assistant now share: default event,
        # event start, default slider weights. CPU-bound: run off the loop.
        await asyncio.to_thread(
            replay.tick, settings.default_event_id, snap.event["start_ts"], Weights()
        )
    except Exception:
        pass  # offline cache missing etc: every endpoint already handles it lazily

    async def _warm_llm():
        try:
            from app import replay
            from app.agents.briefing_llm import llm_brief
            from app.config import settings
            from app.llm.client import chat
            from app.schemas import Weights

            snap = await replay.snapshot(settings.default_event_id)
            top = next(
                (p for p in replay.tick(settings.default_event_id, snap.event["start_ts"], Weights())
                 if p.probability is not None),
                None,
            )
            if top is not None:
                from app import api as api_mod

                res = await llm_brief(top, snap.zone(top.zone_id)["name"])
                api_mod._briefs[(settings.default_event_id, top.zone_id, top.issue_ts)] = res
            else:  # no forecast zones: at least pull the model into memory
                await chat([{"role": "user", "content": "ok"}], max_tokens=4, timeout_s=20)
        except Exception:
            pass  # failures surface per-request with the template fallback

    try:
        asyncio.create_task(_warm_llm())
    except Exception:
        pass
    yield


app = FastAPI(title="KADAL", lifespan=lifespan)
app.include_router(router, prefix="/api")
app.include_router(ws_router)
