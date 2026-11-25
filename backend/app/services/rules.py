from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rules:
    horizon_days: int = 28
    min_lead_minutes: int = 30
    phone_region: str = "IN"
