"""Dashboard WebSocket. One socket per browser tab; call-scoped events need the call's secret id."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("medivoice.ws")
router = APIRouter()


@router.websocket("/ws/events")
async def events_socket(ws: WebSocket):
    app = ws.app
    origin = ws.headers.get("origin")
    allowed = app.state.settings.cors_origins
    if origin and origin not in allowed:           # browsers always send Origin; reject cross-site sockets
        await ws.close(code=4403)
        return
    await ws.accept()
    bus, calls = app.state.bus, app.state.calls
    sub = bus.subscribe(None)
    await ws.send_json({"type": "hello", "instance": bus.instance,
                        "server_time": datetime.now(timezone.utc).isoformat()})

    async def sender():
        while True:
            event = await sub.queue.get()
            if sub.overflowed:
                sub.overflowed = False
                await ws.send_json({"type": "resync.required"})
            await ws.send_json(event)

    async def receiver():
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif msg.get("type") == "subscribe":
                cid = msg.get("call_id")
                if isinstance(cid, str) and calls.get(cid):     # only live calls; id is an unguessable uuid
                    sub.call_id = cid
                    await ws.send_json({"type": "subscribed", "call_id": cid})
                else:
                    await ws.send_json({"type": "subscribe.rejected"})

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        bus.unsubscribe(sub)
