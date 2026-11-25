"""Call lifecycle: WebRTC signalling (/api/offer) and hang-up."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Request

from .. import database as db
from ..middleware.errors import ApiError
from ..repositories import logs, slots
from ..schemas.api import OfferRequest, OfferResponse

log = logging.getLogger("medivoice.calls")
router = APIRouter(prefix="/api")

MAX_CONCURRENT_CALLS = 5
STUN = ["stun:stun.l.google.com:19302"]


@dataclass
class ActiveCall:
    connection: Any
    pipeline_task: Any = None
    runner: asyncio.Task | None = None
    extra: dict = field(default_factory=dict)


@router.post("/offer", response_model=OfferResponse)
async def offer(body: OfferRequest, request: Request):
    app = request.app
    st, bus, calls = app.state.settings, app.state.bus, app.state.calls
    if not st.voice_ready:
        missing = [k for k, v in (("GEMINI_API_KEY", st.gemini_api_key), ("ELEVENLABS_API_KEY", st.elevenlabs_api_key)) if not v]
        raise ApiError(503, "voice_not_configured", f"Missing {', '.join(missing)} in backend/.env")
    if calls.active_count >= MAX_CONCURRENT_CALLS:
        raise ApiError(429, "too_many_calls", "Too many calls are active. Try again shortly.")
    try:
        from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
    except ImportError:
        raise ApiError(503, "pipecat_missing", "pipecat-ai[webrtc] is not installed. See README.")

    from ..voice.pipeline import run_voice_bot

    session = calls.create()
    cid = session.call_id
    clock = app.state.clock

    def prepare(c):
        logs.create_call(c, cid, clock.utc_iso())
        slots.ensure_slots(c, clock.today(), st.booking_horizon_days)
    try:
        with db.session(st.database_path) as c:
            await asyncio.to_thread(prepare, c)
        connection = SmallWebRTCConnection(STUN)
        await connection.initialize(sdp=body.sdp, type=body.type)
        answer = connection.get_answer()
    except Exception:
        calls.remove(cid)
        log.exception("offer failed call=%s", cid[:8])
        raise ApiError(500, "offer_failed", "Could not establish the audio connection.")

    active = ActiveCall(connection=connection)
    app.state.active_calls[cid] = active

    async def finished() -> None:
        now = clock.utc_iso()
        try:
            with db.session(st.database_path) as c:
                await asyncio.to_thread(lambda: logs.update_call(c, cid, state="ended", ended_at=now, end_reason=session.end_reason))
                await asyncio.to_thread(lambda: logs.add_activity(c, now, "call.ended", f"Call {cid[:8]} ended ({session.end_reason})", call_id=cid))
        except Exception:
            log.exception("could not finalise call")
        calls.remove(cid)
        app.state.active_calls.pop(cid, None)
        await bus.publish("call.ended", {"call_id": cid, "reason": session.end_reason})

    @connection.event_handler("closed")
    async def _closed(_conn):
        if active.pipeline_task is not None:
            session.end_reason = session.end_reason if session.end_reason != "completed" else "caller_hangup"
            await active.pipeline_task.cancel()

    def register(task: Any) -> None:
        active.pipeline_task = task

    active.runner = asyncio.create_task(run_voice_bot(
        connection, session, settings=st, clock=clock, runtime=app.state.runtime, bus=bus,
        register_task=register, on_finished=finished))
    await bus.publish("call.started", {"call_id": cid})
    return OfferResponse(sdp=answer["sdp"], type=answer["type"], pc_id=answer.get("pc_id"), call_id=cid)


@router.post("/calls/{call_id}/end")
async def end_call(call_id: str, request: Request):
    active = request.app.state.active_calls.get(call_id)
    session = request.app.state.calls.get(call_id)
    if not active or not session:
        return {"status": "already_ended"}
    session.end_reason = "caller_hangup"
    if active.pipeline_task is not None:
        await active.pipeline_task.cancel()
    return {"status": "ending"}
