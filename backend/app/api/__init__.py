import asyncio
import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import replay
from app.config import settings
from app.llm.client import LLMUnavailable, chat as llm_chat, chat_stream as llm_chat_stream
from app.schemas import Event, ExposureItem, Metrics, Region, Weights, Zone, ZonePayload

router = APIRouter()
ws_router = APIRouter()


async def active(event_id: int | None):
    """The event whose snapshot answers reads; defaults to settings.default_event_id."""
    eid = event_id or settings.default_event_id
    try:
        return eid, await replay.snapshot(eid)
    except KeyError:
        raise HTTPException(404, f"unknown event {eid}")


async def payloads(event_id: int | None, issue_ts: datetime | None, weights: Weights | None = None):
    eid, snap = await active(event_id)
    ts = issue_ts or snap.event["start_ts"]
    return replay.tick(eid, ts, weights)


async def payload(zone_id: str, event_id: int | None, issue_ts: datetime | None) -> ZonePayload:
    for p in await payloads(event_id, issue_ts):
        if p.zone_id == zone_id:
            return p
    raise HTTPException(404, f"unknown zone {zone_id}")


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/regions")
async def regions(event_id: int | None = None) -> list[Region]:
    _, snap = await active(event_id)
    return [Region(**r) for r in snap.regions]


@router.get("/regions/{region_id}/zones")
async def region_zones(region_id: str, event_id: int | None = None) -> list[Zone]:
    _, snap = await active(event_id)
    if region_id != snap.event["region_id"]:
        raise HTTPException(404, f"unknown region {region_id}")
    return [Zone(region_id=region_id, **z) for z in snap.zones]


@router.get("/events")
async def events() -> list[Event]:
    from sqlalchemy import text

    from app.db.session import SessionLocal

    try:
        async with SessionLocal() as s:
            res = await s.execute(text("select id, region_id::text as region_id, name, start_ts, end_ts, "
                                       "is_simulated, is_holdout, source from events order by start_ts"))
            return [Event(**dict(r._mapping)) for r in res]
    except OSError:  # DB unreachable: fall back to whatever is cached locally
        return [Event(**s.event) for s in replay._snaps.values()]


class ReplayStart(BaseModel):
    session_id: str
    event_id: int
    ticks: list[datetime]


@router.post("/replay/{event_id}/start")
async def replay_start(event_id: int, step_h: Annotated[int, Query(ge=1, le=24)] = 1) -> ReplayStart:
    try:
        return ReplayStart(**await replay.start(event_id, step_h))
    except KeyError:
        raise HTTPException(404, f"unknown event {event_id}")


@ws_router.websocket("/ws/replay/{session_id}")
async def replay_ws(ws: WebSocket, session_id: str, interval_s: float = 1.0, start: int = 0):
    """Pushes {issue_ts, zones:[ZonePayload]} per tick, in order."""
    await ws.accept()
    sess = replay.sessions.get(session_id)
    if sess is None:
        await ws.close(code=4404, reason="unknown session")
        return
    try:
        for ts in sess["ticks"][start:]:
            zones = replay.tick(sess["event_id"], ts)
            await ws.send_json({"issue_ts": ts.isoformat(), "zones": [z.model_dump(mode="json") for z in zones]})
            await asyncio.sleep(interval_s)
        await ws.close()
    except WebSocketDisconnect:
        pass


@router.get("/zones/{zone_id}")
async def zone(zone_id: str, issue_ts: datetime | None = None, event_id: int | None = None) -> ZonePayload:
    return await payload(zone_id, event_id, issue_ts)


class Risk(BaseModel):
    zone_id: str
    coverage: str
    is_simulated: bool
    probability: float | None
    severity: str | None
    onset: dict | None
    peak: dict | None


@router.get("/zones/{zone_id}/risk")
async def zone_risk(zone_id: str, issue_ts: datetime | None = None, event_id: int | None = None) -> Risk:
    p = await payload(zone_id, event_id, issue_ts)
    return Risk(**p.model_dump(include=set(Risk.model_fields)))


@router.get("/zones/{zone_id}/explanation")
async def zone_explanation(zone_id: str, issue_ts: datetime | None = None, event_id: int | None = None) -> dict:
    p = await payload(zone_id, event_id, issue_ts)
    return {"zone_id": zone_id, "drivers_text": p.drivers_text, "reasons": [r.model_dump() for r in p.reasons], "explanation": p.explanation, "model": p.model}


@router.get("/zones/{zone_id}/exposure")
async def zone_exposure(zone_id: str, event_id: int | None = None) -> list[ExposureItem]:
    return (await payload(zone_id, event_id, None)).exposure


@router.get("/zones/{zone_id}/alert")
async def zone_alert(zone_id: str, issue_ts: datetime | None = None, event_id: int | None = None) -> dict:
    p = await payload(zone_id, event_id, issue_ts)
    return {"zone_id": zone_id, "alert_text": p.alert_text, "onset": p.onset, "peak": p.peak, "is_simulated": p.is_simulated}


_briefs: dict[tuple, dict] = {}


@router.get("/zones/{zone_id}/briefing")
async def zone_briefing(zone_id: str, issue_ts: datetime | None = None, event_id: int | None = None) -> dict:
    """Local-LLM narration of one zone, number-checked; falls back to the template (`source` says which)."""
    from app.agents.briefing_llm import llm_brief

    eid, snap = await active(event_id)
    p = await payload(zone_id, eid, issue_ts)
    key = (eid, zone_id, p.issue_ts)
    if key not in _briefs or _briefs[key]["source"] != "llm":  # retry template fallbacks, keep good answers
        _briefs[key] = await llm_brief(p, snap.zone(zone_id)["name"])
    return _briefs[key]


@router.get("/pipeline")
async def pipeline_status(issue_ts: datetime | None = None, event_id: int | None = None) -> dict:
    """Run one tick through the LangGraph pipeline and report how it went: per-agent timing, failed zones, and the graph."""
    from time import perf_counter

    from app import pipeline

    eid, snap = await active(event_id)
    ts = issue_ts or snap.event["start_ts"]
    t = perf_counter()
    r = await asyncio.to_thread(pipeline.run_tick_traced, snap, ts)
    return {"event_id": eid, "issue_ts": ts, "zones": len(r.payloads), "forecast": sum(p.probability is not None for p in r.payloads),
            "insufficient_data": sum(p.probability is None for p in r.payloads), "failed": r.errors,
            "agents": pipeline.summarize(r.trace), "total_ms": round((perf_counter() - t) * 1000), "graph_mermaid": pipeline.diagram()}


@router.get("/tick/stream")
async def tick_stream(issue_ts: datetime | None = None, event_id: int | None = None):
    """SSE progress of one tick: {"event":"zone",done,total,...} per zone, {"event":"ranked"}, then {"event":"done","payloads":[...]}."""
    from app import pipeline

    eid, snap = await active(event_id)
    ts = issue_ts or snap.event["start_ts"]

    async def events():
        async for e in pipeline.astream_tick(snap, ts):
            if e["event"] == "done":
                e = {"event": "done", "payloads": [p.model_dump(mode="json") for p in e["payloads"]]}
            yield f"data: {json.dumps(e, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/ranking")
async def ranking(
    weights: Annotated[Weights, Depends()], issue_ts: datetime | None = None, event_id: int | None = None
) -> list[ZonePayload]:
    return list(await payloads(event_id, issue_ts, weights))


class RankingRequest(BaseModel):
    weights: Weights
    issue_ts: datetime | None = None
    event_id: int | None = None


@router.post("/ranking/weights")
async def ranking_weights(req: RankingRequest) -> list[ZonePayload]:
    # ponytail: not persisted to ranking_runs yet; add when the sensitivity view needs history
    return list(await payloads(req.event_id, req.issue_ts, req.weights))


@router.get("/models/{region_id}/metrics")
async def metrics(region_id: str, event_id: int | None = None) -> list[Metrics]:
    _, snap = await active(event_id)
    return [Metrics(model=m["model_name"], version=m["version"], region_id=m["region_id"], metrics=m["metrics_json"])
            for m in snap.model_runs if m["region_id"] == region_id]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    system: str | None = None


class ChatResponse(BaseModel):
    message: str
    model: str


@router.post("/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    """Simple chat with the local model. Ungrounded: the model only sees this
    conversation, never zone data, so its answers are not validated output."""
    if not req.messages or not any(m.content.strip() for m in req.messages):
        raise HTTPException(422, "at least one non-empty message is required")
    try:
        res = await llm_chat([m.model_dump() for m in req.messages], system=req.system)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))
    return ChatResponse(message=res.text, model=res.model)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Token stream (SSE) for the same chat. Events: {"token": str},
    then {"done": true, "model": str}, or {"error": str} when the model
    cannot answer. <think> spans are stripped server-side, chunk by chunk."""
    if not req.messages or not any(m.content.strip() for m in req.messages):
        raise HTTPException(422, "at least one non-empty message is required")
    messages = [m.model_dump() for m in req.messages]

    async def events():
        try:
            async for token in llm_chat_stream(messages, system=req.system):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except LLMUnavailable as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return
        yield f"data: {json.dumps({'done': True, 'model': settings.llm_model})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
