"""The Pipecat pipeline for one call.

   browser mic --WebRTC--> transport.input -> ElevenLabs STT -> transcript tap
        -> user aggregator (Silero VAD) -> Gemini (function calling) -> ElevenLabs TTS
        -> transport.output --WebRTC--> browser speaker -> assistant aggregator

Tools run server-side in ToolRuntime against SQLite. All pipecat imports are lazy.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from .. import database as db
from ..config import Settings
from ..repositories import logs
from ..tools.definitions import TOOLS
from ..tools.handlers import ToolRuntime
from ..utils.clock import Clock
from ..websocket.bus import EventBus
from .prompts import build_system_prompt
from .session import CallSession

log = logging.getLogger("medivoice.voice")


async def run_voice_bot(connection: Any, session: CallSession, *, settings: Settings, clock: Clock, runtime: ToolRuntime,
                        bus: EventBus, register_task: Callable[[Any], None], on_finished: Callable[[], Awaitable[None]]) -> None:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.frames.frames import EndFrame, TTSSpeakFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
    from pipecat.services.google.llm import GoogleLLMService
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    from . import compat
    from .taps import CallActivity, CallObserver, TranscriptTap

    cid = session.call_id
    activity = CallActivity()

    def _db(fn, *a):
        def run():
            with db.session(settings.database_path) as c:
                return fn(c, *a)
        return asyncio.to_thread(run)

    async def emit(role: str, text: str, final: bool) -> None:
        if final:
            try:
                await _db(lambda c: logs.add_transcript(c, cid, role, text, clock.utc_iso()))
            except Exception:
                log.exception("could not persist transcript")
        await bus.publish("transcript.final" if final else "transcript.partial",
                          {"role": role, "text": text}, call_id=cid, scope="call")

    # ---- services
    vad = SileroVADAnalyzer(params=VADParams(confidence=0.75, start_secs=0.2, stop_secs=0.6, min_volume=0.5))
    stt = compat.make_stt(settings.elevenlabs_api_key)
    llm = GoogleLLMService(api_key=settings.gemini_api_key, model=settings.gemini_model)
    tts = ElevenLabsTTSService(api_key=settings.elevenlabs_api_key, voice_id=settings.elevenlabs_voice_id,
                               model=settings.elevenlabs_tts_model)

    # ---- tools: LLM -> ToolRuntime (server injects the call session; the model cannot choose it)
    def make_handler(name: str):
        async def handler(*args: Any, **kwargs: Any) -> None:
            params = args[0] if args and hasattr(args[0], "arguments") else None
            if params is not None:
                arguments, done = params.arguments, params.result_callback
            else:                                              # legacy positional signature
                arguments, done = args[2], args[5]
            await bus.publish("tool.started", {"name": name}, call_id=cid, scope="call")
            result = await runtime.dispatch(name, session, dict(arguments or {}))
            await bus.publish("tool.finished", {"name": name, "status": result.get("status"), "ok": result.get("ok")},
                              call_id=cid, scope="call")
            await done(result)
        return handler

    for t in TOOLS:
        llm.register_function(t["name"], make_handler(t["name"]))

    # ---- context
    with db.session(settings.database_path) as c:
        from ..repositories import doctors as docs
        specs = docs.specialities(c)
    now = clock.now()
    messages = [{"role": "system", "content": build_system_prompt(
        settings.clinic_name, now.strftime("%A, %d %B %Y"), now.strftime("%H:%M"), settings.clinic_timezone, specs)}]
    context, user_agg, assistant_agg, vad_in_agg = compat.make_context(llm, messages, compat.make_tools_schema(TOOLS), vad)

    tparams: dict[str, Any] = {"audio_in_enabled": True, "audio_out_enabled": True}
    if not vad_in_agg:
        tparams["vad_analyzer"] = vad
    transport = SmallWebRTCTransport(webrtc_connection=connection, params=TransportParams(**tparams))

    tap = TranscriptTap(session, emit, activity)
    pipeline = Pipeline([transport.input(), stt, tap, user_agg, llm, tts, transport.output(), assistant_agg])
    observer = CallObserver(session, bus, emit, activity)
    try:
        task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True), observers=[observer])
    except TypeError:       # allow_interruptions removed in newer releases (interruptions are on by default)
        task = PipelineTask(pipeline, observers=[observer])
    register_task(task)

    @transport.event_handler("on_client_connected")
    async def _connected(_t, _c):
        now_iso = clock.utc_iso()
        await _db(lambda c: logs.update_call(c, cid, state="connected", connected_at=now_iso))
        await bus.publish("call.connected", {"call_id": cid})
        await compat.trigger_llm(task, user_agg)

    @transport.event_handler("on_client_disconnected")
    async def _disconnected(_t, _c):
        session.end_reason = "caller_hangup"
        await task.cancel()

    async def watchdog() -> None:
        prompted = False
        while not session.ended:
            await asyncio.sleep(1)
            if activity.bot_speaking or session.inflight_tools:
                continue
            idle = activity.idle_secs
            if idle < settings.silence_prompt_secs:
                prompted = False
            elif not prompted:
                prompted = True
                await task.queue_frames([TTSSpeakFrame("Are you still there?")])
            elif idle >= settings.silence_hangup_secs - settings.silence_prompt_secs + 2:
                session.end_reason = "silence_timeout"
                await task.queue_frames([TTSSpeakFrame("I haven't heard anything, so I'll end the call. Please call back any time. Goodbye."), EndFrame()])
                return

    wd = asyncio.create_task(watchdog())
    try:
        await PipelineRunner(handle_sigint=False).run(task)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.exception("pipeline crashed call=%s", cid[:8])
        session.end_reason = "pipeline_error"
        await bus.publish("system.error", {"message": f"Voice pipeline stopped: {type(exc).__name__}", "fatal": True}, call_id=cid)
    finally:
        wd.cancel()
        session.ended = True
        await on_finished()
