"""FastAPI entrypoint.   uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import database as db
from . import seed
from .config import load_settings
from .middleware import errors
from .middleware.logging_setup import configure_logging
from .repositories import logs, slots
from .routers import api, voice
from .services import booking
from .services.rules import Rules
from .tools.handlers import ToolRuntime
from .utils.clock import Clock
from .voice.session import CallManager
from .websocket import router as ws_router
from .websocket.bus import EventBus

log = logging.getLogger("medivoice")


def bootstrap_database(settings, clock: Clock) -> None:
    """Create schema, seed once, roll slots forward, close out dangling state."""
    with db.session(settings.database_path) as c:
        db.init_schema(c)
        if not seed.is_seeded(c):
            seed.seed(c, clock, settings.booking_horizon_days)
            log.info("database seeded")
        slots.ensure_slots(c, clock.today(), settings.booking_horizon_days)
        booking.complete_past(c, clock)
        n = logs.end_dangling_calls(c, clock.utc_iso())
        if n:
            log.warning("closed %s calls left open by a previous run", n)


async def maintenance_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(600)
        try:
            s = app.state
            def work():
                with db.session(s.settings.database_path) as c:
                    slots.ensure_slots(c, s.clock.today(), s.settings.booking_horizon_days)
                    return booking.complete_past(c, s.clock)
            if await asyncio.to_thread(work):
                await s.bus.publish("availability.updated", {"reason": "maintenance"})
        except Exception:
            log.exception("maintenance failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    configure_logging(settings.log_level)
    clock = Clock(settings.clinic_timezone)
    rules = Rules(settings.booking_horizon_days, settings.min_lead_minutes, settings.phone_region)
    bootstrap_database(settings, clock)
    bus = EventBus()
    app.state.settings, app.state.clock, app.state.rules = settings, clock, rules
    app.state.bus, app.state.calls, app.state.active_calls = bus, CallManager(), {}
    app.state.runtime = ToolRuntime(settings.database_path, clock, rules, bus)
    task = asyncio.create_task(maintenance_loop(app))
    log.info("MediVoice API ready | voice_ready=%s | model=%s", settings.voice_ready, settings.gemini_model)
    yield
    task.cancel()
    for active in list(app.state.active_calls.values()):
        if active.pipeline_task is not None:
            await active.pipeline_task.cancel()


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="MediVoice AI", version="1.0.0", lifespan=lifespan,
                  description="Voice appointment assistant: REST API for the dashboard, WebRTC signalling for Pipecat, WebSocket events.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"], allow_credentials=False)
    errors.install(app)
    app.include_router(api.router)
    app.include_router(voice.router)
    app.include_router(ws_router.router)
    return app


app = create_app()
