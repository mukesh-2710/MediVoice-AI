"""Clinic-local time helpers. Timestamps are stored in UTC; slots are clinic-local wall time."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


class Clock:
    """Injectable clock so tests can freeze 'now'."""

    def __init__(self, tz_name: str = "Asia/Kolkata", fixed_utc: datetime | None = None):
        self.tz = ZoneInfo(tz_name)
        self._fixed = fixed_utc

    def utcnow(self) -> datetime:
        return self._fixed or datetime.now(timezone.utc)

    def now(self) -> datetime:
        """Timezone-aware 'now' in the clinic timezone."""
        return self.utcnow().astimezone(self.tz)

    def today(self) -> date:
        return self.now().date()

    def utc_iso(self) -> str:
        return self.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def slot_dt(self, d: date | str, hhmm: str) -> datetime:
        if isinstance(d, str):
            d = date.fromisoformat(d)
        h, m = (int(x) for x in hhmm.split(":"))
        return datetime(d.year, d.month, d.day, h, m, tzinfo=self.tz)
