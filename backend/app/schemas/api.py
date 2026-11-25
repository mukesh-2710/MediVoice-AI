"""Pydantic request/response models for the REST API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class OfferRequest(BaseModel):
    sdp: str = Field(min_length=10, max_length=100_000)
    type: str = Field(pattern="^(offer|answer)$")
    pc_id: str | None = Field(default=None, max_length=100)
    restart_pc: bool = False


class OfferResponse(BaseModel):
    sdp: str
    type: str
    pc_id: str | None = None
    call_id: str


class HealthResponse(BaseModel):
    status: str
    database: str
    voice_ready: bool
    active_calls: int
    ws_subscribers: int
    server_time_utc: str


class ConfigStatus(BaseModel):
    """Only booleans and non-secret settings. API keys are never serialised."""
    gemini_configured: bool
    elevenlabs_configured: bool
    voice_ready: bool
    llm_model: str
    tts_model: str
    clinic_name: str
    clinic_timezone: str
    booking_horizon_days: int
    vad: str = "Silero"
    transport: str = "WebRTC (Pipecat SmallWebRTC)"


class AppointmentOut(BaseModel):
    id: int
    appointment_ref: str
    doctor_id: int
    doctor_name: str
    speciality: str
    consultation_fee: int
    patient_phone: str
    appointment_date: str
    appointment_time: str
    status: str
    call_session_id: str | None = None
    created_at: str
    cancelled_at: str | None = None
