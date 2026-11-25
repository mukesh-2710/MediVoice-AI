"""In-process pub/sub for dashboard events.

* Every event has a unique id (dashboard de-duplicates on it) and a monotonically increasing seq.
* scope="public": all dashboards (appointment/availability/call lifecycle).
* scope="call":   only subscribers that hold that call's unguessable call_id (transcripts, speaking state).
* Slow consumers never block publishers: on overflow the subscriber is told to resync via REST.
"""
from __future__ import annotations

import asyncio
import itertools
import uuid
from datetime import datetime, timezone
from typing import Any


class Subscription:
    def __init__(self, call_id: str | None):
        self.call_id = call_id
        self.queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=500)
        self.overflowed = False


class EventBus:
    def __init__(self) -> None:
        self.instance = uuid.uuid4().hex[:8]
        self._seq = itertools.count(1)
        self._subs: set[Subscription] = set()

    def subscribe(self, call_id: str | None = None) -> Subscription:
        sub = Subscription(call_id)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subs.discard(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    async def publish(self, type_: str, data: dict[str, Any] | None = None, *, call_id: str | None = None,
                      scope: str = "public") -> dict:
        seq = next(self._seq)
        event = {"id": f"{self.instance}-{seq}", "seq": seq, "type": type_, "call_id": call_id,
                 "ts": datetime.now(timezone.utc).isoformat(), "data": data or {}}
        for sub in list(self._subs):
            if scope == "call" and sub.call_id != call_id:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                sub.overflowed = True
        return event
