"""Statistics for the dashboard (real database values)."""
from __future__ import annotations

from datetime import timedelta

from ..repositories import slots as slot_repo
from ..utils.clock import Clock


def stats(conn, clock: Clock, active_calls: int = 0) -> dict:
    today = clock.today()
    iso = today.isoformat()
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    by_status = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status")}
    per_day = []
    for i in range(7):
        d = (today + timedelta(days=i)).isoformat()
        per_day.append({"date": d, "count": q("SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND status='BOOKED'", d)})
    by_spec = [{"speciality": r[0], "count": r[1]} for r in conn.execute(
        "SELECT d.speciality, COUNT(*) FROM appointments a JOIN doctors d ON d.id=a.doctor_id "
        "WHERE a.status IN ('BOOKED','COMPLETED') GROUP BY d.speciality ORDER BY 2 DESC")]
    return {
        "total_appointments": q("SELECT COUNT(*) FROM appointments"),
        "today_appointments": q("SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND status IN ('BOOKED','COMPLETED')", iso),
        "confirmed_appointments": by_status.get("BOOKED", 0),
        "cancelled_appointments": by_status.get("CANCELLED", 0),
        "completed_appointments": by_status.get("COMPLETED", 0),
        "available_slots": slot_repo.count_available(conn, iso, clock.now().strftime("%H:%M")),
        "active_calls": active_calls,
        "total_doctors": q("SELECT COUNT(*) FROM doctors WHERE active=1"),
        "per_day": per_day,
        "by_speciality": by_spec,
        "by_status": by_status,
    }
