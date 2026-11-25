"""REST endpoints used by the dashboard. Read-mostly: bookings happen through the voice agent."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, Response

from .. import database as db
from ..middleware.errors import ApiError
from ..repositories import appointments as appts
from ..repositories import doctors as docs
from ..repositories import logs, slots
from ..schemas.api import ConfigStatus, HealthResponse
from ..services import availability, dashboard
from ..utils.dates import to_12h

router = APIRouter(prefix="/api")


def get_conn(request: Request):
    with db.session(request.app.state.settings.database_path) as conn:
        yield conn


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    s = request.app.state
    try:
        with db.session(s.settings.database_path) as c:
            c.execute("SELECT 1").fetchone()
        dbs = "ok"
    except Exception:
        dbs = "error"
    return HealthResponse(status="ok" if dbs == "ok" else "degraded", database=dbs, voice_ready=s.settings.voice_ready,
                          active_calls=s.calls.active_count, ws_subscribers=s.bus.subscriber_count,
                          server_time_utc=datetime.now(timezone.utc).isoformat())


@router.get("/config/status", response_model=ConfigStatus)
def config_status(request: Request):
    st = request.app.state.settings
    return ConfigStatus(gemini_configured=bool(st.gemini_api_key), elevenlabs_configured=bool(st.elevenlabs_api_key),
                        voice_ready=st.voice_ready, llm_model=st.gemini_model, tts_model=st.elevenlabs_tts_model,
                        clinic_name=st.clinic_name, clinic_timezone=st.clinic_timezone, booking_horizon_days=st.booking_horizon_days)


@router.get("/doctors")
def list_doctors(conn=Depends(get_conn), speciality: str | None = None, q: str | None = None):
    out = docs.list_doctors(conn)
    if speciality:
        out = [d for d in out if d["speciality"].lower() == speciality.lower()]
    if q:
        ql = q.lower()
        out = [d for d in out if ql in d["name"].lower() or ql in d["speciality"].lower()]
    return out


@router.get("/doctors/{doctor_id}")
def get_doctor(doctor_id: int, conn=Depends(get_conn)):
    d = docs.get_doctor(conn, doctor_id)
    if not d:
        raise ApiError(404, "doctor_not_found", f"No doctor with id {doctor_id}.")
    return d


@router.get("/availability")
def availability_for_day(request: Request, date_: str = Query(alias="date"), doctor_id: int | None = None,
                         speciality: str | None = None, conn=Depends(get_conn)):
    """Free slots per doctor for one day (the same query the voice tool uses)."""
    s = request.app.state
    try:
        date.fromisoformat(date_)
    except ValueError:
        raise ApiError(422, "invalid_date", "date must be YYYY-MM-DD")
    targets = docs.list_doctors(conn)
    if doctor_id:
        targets = [d for d in targets if d["id"] == doctor_id]
    if speciality:
        targets = [d for d in targets if d["speciality"].lower() == speciality.lower()]
    hol = docs.holiday_on(conn, date_)
    rows = []
    for d in targets:
        times = [] if hol else availability.future_times(conn, s.clock, s.rules, d["id"], date_)
        if docs.leave_on(conn, d["id"], date_):
            times = []
        booked = [r[0] for r in conn.execute(
            "SELECT slot_time FROM appointment_slots WHERE doctor_id=? AND slot_date=? AND status='BOOKED' ORDER BY slot_time", (d["id"], date_))]
        rows.append({"doctor_id": d["id"], "name": d["name"], "speciality": d["speciality"],
                     "available": [{"time": t, "label": to_12h(t)} for t in times],
                     "booked": [{"time": t, "label": to_12h(t)} for t in booked],
                     "works_today": any(sc["weekday"] == date.fromisoformat(date_).weekday() for sc in d["schedule"])})
    return {"date": date_, "holiday": hol, "doctors": rows}


@router.get("/appointments")
def list_appointments(conn=Depends(get_conn), status: str | None = None, phone: str | None = None,
                      date_from: str | None = None, date_to: str | None = None, doctor_id: int | None = None,
                      q: str | None = None, limit: int = 500):
    if status and status.upper() not in {"BOOKED", "CANCELLED", "COMPLETED"}:
        raise ApiError(422, "invalid_status", "status must be BOOKED, CANCELLED or COMPLETED")
    return appts.search(conn, status=status, phone=phone, date_from=date_from, date_to=date_to,
                        doctor_id=doctor_id, text=q, limit=limit)


@router.get("/appointments/export.csv")
def export_csv(conn=Depends(get_conn), status: str | None = None):
    rows = appts.search(conn, status=status, limit=2000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["reference", "doctor", "speciality", "phone", "date", "time", "status", "created_at_utc", "cancelled_at_utc"])
    for r in rows:
        w.writerow([r["appointment_ref"], r["doctor_name"], r["speciality"], r["patient_phone"], r["appointment_date"],
                    r["appointment_time"], r["status"], r["created_at"], r["cancelled_at"] or ""])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="appointments.csv"'})


@router.get("/stats")
def stats(request: Request, conn=Depends(get_conn)):
    s = request.app.state
    return dashboard.stats(conn, s.clock, active_calls=s.calls.active_count)


@router.get("/calls")
def list_calls(conn=Depends(get_conn), limit: int = 100):
    return logs.list_calls(conn, limit)


@router.get("/calls/{call_id}/transcript")
def transcript(call_id: str, conn=Depends(get_conn)):
    return logs.get_transcript(conn, call_id)


@router.get("/calls/{call_id}/transcript.txt")
def transcript_txt(call_id: str, conn=Depends(get_conn)):
    rows = logs.get_transcript(conn, call_id)
    if not rows:
        raise ApiError(404, "transcript_not_found", "No transcript for this call.")
    body = "\n".join(f"[{r['created_at']}] {'Caller' if r['role'] == 'user' else 'Agent' if r['role'] == 'agent' else 'System'}: {r['text']}" for r in rows)
    return PlainTextResponse(body, headers={"Content-Disposition": f'attachment; filename="call-{call_id[:8]}.txt"'})


@router.get("/activity")
def activity(conn=Depends(get_conn), limit: int = 100):
    return logs.list_activity(conn, limit)


@router.get("/state")
def state(request: Request, conn=Depends(get_conn)):
    """Full snapshot used on first load and after every reconnect (database-backed resync)."""
    s = request.app.state
    return {
        "instance": s.bus.instance,
        "doctors": docs.list_doctors(conn),
        "appointments": appts.search(conn, limit=500),
        "stats": dashboard.stats(conn, s.clock, active_calls=s.calls.active_count),
        "calls": logs.list_calls(conn, 50),
        "activity": logs.list_activity(conn, 60),
        "active_call_ids": s.calls.active_ids(),
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }
