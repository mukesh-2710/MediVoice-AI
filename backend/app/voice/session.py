"""Per-call state. Lives only on the server; the LLM can never read or forge it."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field


@dataclass
class CallSession:
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    pending_phone: str | None = None
    verified_phone: str | None = None
    pending_booking: tuple | None = None        # (doctor_id, date, time, phone)
    pending_cancel: tuple | None = None         # sorted appointment ids
    last_user_text: str = ""
    ended: bool = False
    end_reason: str = "completed"
    muted: bool = False
    inflight_tools: int = 0
    last_booking: dict | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def reset_pending(self) -> None:
        self.pending_booking = None
        self.pending_cancel = None


class CallManager:
    def __init__(self) -> None:
        self._sessions: dict[str, CallSession] = {}

    def create(self) -> CallSession:
        s = CallSession()
        self._sessions[s.call_id] = s
        return s

    def get(self, call_id: str) -> CallSession | None:
        return self._sessions.get(call_id)

    def remove(self, call_id: str) -> None:
        s = self._sessions.pop(call_id, None)
        if s:
            s.ended = True

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def active_ids(self) -> list[str]:
        return list(self._sessions)
