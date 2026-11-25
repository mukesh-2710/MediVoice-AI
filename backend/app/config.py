"""Central configuration. Everything comes from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no dependency). Real environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    # secrets - backend only, never sent to the browser
    gemini_api_key: str = ""
    elevenlabs_api_key: str = ""
    # models / voices
    gemini_model: str = "gemini-3.8-flash"
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    # clinic
    clinic_name: str = "Northwell Clinic"
    clinic_timezone: str = "Asia/Kolkata"
    phone_region: str = "IN"
    booking_horizon_days: int = 28
    min_lead_minutes: int = 30
    # storage / server
    database_path: str = "data/medivoice.db"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    # call behaviour
    silence_prompt_secs: int = 12
    silence_hangup_secs: int = 25
    log_level: str = "INFO"

    @property
    def voice_ready(self) -> bool:
        return bool(self.gemini_api_key and self.elevenlabs_api_key)


def load_settings() -> Settings:
    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    e = os.environ.get
    return Settings(
        gemini_api_key=e("GEMINI_API_KEY", ""),
        elevenlabs_api_key=e("ELEVENLABS_API_KEY", ""),
        gemini_model=e("GEMINI_MODEL", "gemini-3.8-flash"),
        elevenlabs_voice_id=e("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
        elevenlabs_tts_model=e("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
        clinic_name=e("CLINIC_NAME", "Northwell Clinic"),
        clinic_timezone=e("CLINIC_TIMEZONE", "Asia/Kolkata"),
        phone_region=e("PHONE_REGION", "IN").upper(),
        booking_horizon_days=int(e("BOOKING_HORIZON_DAYS", "28")),
        min_lead_minutes=int(e("MIN_LEAD_MINUTES", "30")),
        database_path=e("DATABASE_PATH", "data/medivoice.db"),
        cors_origins=_csv(e("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")),
        silence_prompt_secs=int(e("SILENCE_PROMPT_SECS", "12")),
        silence_hangup_secs=int(e("SILENCE_HANGUP_SECS", "25")),
        log_level=e("LOG_LEVEL", "INFO").upper(),
    )
