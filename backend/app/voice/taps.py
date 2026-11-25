"""Pipeline-side taps. The transcript tap lives INSIDE the frame flow (not an observer) so that
`session.last_user_text` is guaranteed to be updated before the LLM can call a tool."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from pipecat.frames.frames import (BotStartedSpeakingFrame, BotStoppedSpeakingFrame, ErrorFrame, Frame,
                                   InterimTranscriptionFrame, LLMFullResponseEndFrame, LLMTextFrame,
                                   TranscriptionFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .compat import interruption_frame_types
from .session import CallSession

log = logging.getLogger("medivoice.voice")


class CallActivity:
    """Shared timestamps for the silence watchdog."""

    def __init__(self) -> None:
        self.last_user = time.monotonic()
        self.last_bot = time.monotonic()
        self.bot_speaking = False

    def user(self) -> None:
        self.last_user = time.monotonic()

    def bot(self, speaking: bool) -> None:
        self.bot_speaking = speaking
        self.last_bot = time.monotonic()

    @property
    def idle_secs(self) -> float:
        return time.monotonic() - max(self.last_user, self.last_bot)


class TranscriptTap(FrameProcessor):
    """Sits right after STT. Records final transcripts, merges split segments of one utterance."""

    def __init__(self, session: CallSession, emit, activity: CallActivity, **kw):
        super().__init__(**kw)
        self._s, self._emit, self._act = session, emit, activity
        self._last_ts = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and (frame.text or "").strip():
            text, now = frame.text.strip(), time.monotonic()
            self._s.last_user_text = f"{self._s.last_user_text} {text}" if now - self._last_ts < 1.5 else text
            self._last_ts = now
            self._act.user()
            asyncio.create_task(self._emit("user", text, True))
        elif isinstance(frame, InterimTranscriptionFrame) and (frame.text or "").strip():
            self._act.user()
            asyncio.create_task(self._emit("user", frame.text.strip(), False))
        await self.push_frame(frame, direction)


class CallObserver:
    """Observer for speaking state, agent text and errors. De-duplicates frames seen at several hops."""

    def __init__(self, session: CallSession, bus, emit, activity: CallActivity):
        self._s, self._bus, self._emit, self._act = session, bus, emit, activity
        self._seen: deque[int] = deque(maxlen=4000)
        self._seen_set: set[int] = set()
        self._buf: list[str] = []
        self._interrupts = interruption_frame_types()

    async def on_pipeline_started(self) -> None:
        pass

    async def on_process_frame(self, _data) -> None:
        pass

    def _first_time(self, frame: Frame) -> bool:
        if frame.id in self._seen_set:
            return False
        if len(self._seen) == self._seen.maxlen:
            self._seen_set.discard(self._seen[0])
        self._seen.append(frame.id)
        self._seen_set.add(frame.id)
        return True

    async def _flush(self, interrupted: bool = False) -> None:
        text = "".join(self._buf).strip()
        self._buf.clear()
        if text:
            await self._emit("agent", text + (" …" if interrupted else ""), True)

    async def on_push_frame(self, *args, **kwargs):
        data = args[0] if args and hasattr(args[0], "frame") else None
        frame = data.frame if data else (args[2] if len(args) > 2 else kwargs.get("frame"))
        if frame is None or not self._first_time(frame):
            return
        cid = self._s.call_id
        pub = lambda t, d: self._bus.publish(t, d, call_id=cid, scope="call")
        if isinstance(frame, UserStartedSpeakingFrame):
            self._act.user()
            await pub("caller.speaking", {"speaking": True})
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._act.user()
            await pub("caller.speaking", {"speaking": False})
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._act.bot(True)
            await pub("agent.speaking", {"speaking": True})
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._act.bot(False)
            await pub("agent.speaking", {"speaking": False})
        elif isinstance(frame, LLMTextFrame):
            self._buf.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._flush()
        elif self._interrupts and isinstance(frame, self._interrupts):
            await self._flush(interrupted=True)
            await pub("agent.speaking", {"speaking": False})
        elif isinstance(frame, ErrorFrame):
            log.error("pipeline error call=%s: %s", cid[:8], frame.error)
            note = None
            if self._s.last_booking:
                note = f"Booking {self._s.last_booking['appointment_ref']} was saved even though the voice reply failed."
            await self._bus.publish("system.error", {"message": str(frame.error)[:300], "fatal": bool(getattr(frame, "fatal", False)),
                                                     "note": note}, call_id=cid)
