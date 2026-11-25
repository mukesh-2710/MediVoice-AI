"""Transactional booking / cancellation. A successful LLM reply is never proof of success:
only a committed row, returned from here, is."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Callable

from .. import database as db
from ..repositories import appointments as appts
from ..repositories import doctors as docs
from ..repositories import logs, slots
from ..utils.clock import Clock
from ..utils.dates import parse_time_text, to_12h
from ..utils.phone import validate_phone
from . import availability
from .rules import Rules

ACTIVE = ("BOOKED",)


def _fail(code: str, message: str, **extra) -> dict:
    return {"ok": False, "status": code, "message": message, **extra}


def _alternatives(conn, clock: Clock, rules: Rules, doctor_id: int, iso: str) -> dict:
    same_day = availability.future_times(conn, clock, rules, doctor_id, iso)[:4]
    d = docs.get_doctor(conn, doctor_id)
    others = []
    if d:
        for o in docs.doctors_in_speciality(conn, d["speciality"]):
            if o["id"] != doctor_id and not docs.leave_on(conn, o["id"], iso):
                t = availability.future_times(conn, clock, rules, o["id"], iso)[:3]
                if t:
                    others.append({"doctor_id": o["id"], "name": o["name"], "times": [to_12h(x) for x in t]})
    return {"same_day_times": [to_12h(t) for t in same_day],
            "next_dates": availability.next_dates(conn, clock, rules, doctor_id, iso, 3),
            "other_doctors_same_speciality": others}


def _public(a: dict) -> dict:
    return {k: a[k] for k in ("id", "appointment_ref", "doctor_id", "doctor_name", "speciality", "consultation_fee",
                              "patient_phone", "appointment_date", "appointment_time", "status", "created_at", "cancelled_at")}


def book_appointment(conn: sqlite3.Connection, clock: Clock, rules: Rules, *, doctor_id, patient_phone: str,
                     appointment_date: str, appointment_time: str, call_id: str | None = None,
                     dry_run: bool = False, fault: Callable[[str], None] | None = None) -> dict:
    """`dry_run` validates without writing. `fault(stage)` is a test hook used to simulate failures inside the transaction."""
    ph = validate_phone(patient_phone, rules.phone_region)
    if not ph.ok:
        return _fail("INVALID_PHONE", ph.message)
    try:
        doctor_id = int(doctor_id)
    except (TypeError, ValueError):
        return _fail("INVALID_DOCTOR", "doctor_id must be a number from check_doctor_availability.")
    doctor = docs.get_doctor(conn, doctor_id)
    if not doctor or not doctor["active"]:
        return _fail("INVALID_DOCTOR", f"No doctor with id {doctor_id}.")
    try:
        day = date.fromisoformat(appointment_date)
    except (TypeError, ValueError):
        return _fail("INVALID_DATE", "appointment_date must be YYYY-MM-DD.")
    hhmm = parse_time_text(appointment_time) if appointment_time else None
    if not hhmm:
        return _fail("INVALID_TIME", "appointment_time must be a time such as 11:00.")
    iso = day.isoformat()
    if day < clock.today():
        return _fail("PAST_DATE", "That date is in the past.")
    hol = docs.holiday_on(conn, iso)
    if hol:
        return _fail("HOLIDAY", f"The clinic is closed on {iso} ({hol}).")
    leave = docs.leave_on(conn, doctor_id, iso)
    if leave:
        return _fail("DOCTOR_UNAVAILABLE", f"{doctor['name']} is unavailable on {iso}.", alternatives=_alternatives(conn, clock, rules, doctor_id, iso))
    sched = docs.schedule_for(conn, doctor_id, day.weekday())
    if not sched or not (sched["start_time"] <= hhmm < sched["end_time"]):
        return _fail("OUTSIDE_HOURS", f"{doctor['name']} does not see patients at {to_12h(hhmm)} on {day.strftime('%A')}.",
                     alternatives=_alternatives(conn, clock, rules, doctor_id, iso))
    if clock.slot_dt(iso, hhmm) < clock.now() + timedelta(minutes=rules.min_lead_minutes):
        return _fail("PAST_TIME", "That time is too soon or already passed.", alternatives=_alternatives(conn, clock, rules, doctor_id, iso))

    phone = ph.digits
    try:
        with db.transaction(conn):
            slot = slots.get_slot(conn, doctor_id, iso, hhmm)
            if not slot:
                raise _Abort(_fail("NO_SUCH_SLOT", f"{doctor['name']} has no slot at {to_12h(hhmm)}.",
                                   alternatives=_alternatives(conn, clock, rules, doctor_id, iso)))
            if slot["status"] == "BLOCKED":
                raise _Abort(_fail("DOCTOR_UNAVAILABLE", "That slot is no longer available.",
                                   alternatives=_alternatives(conn, clock, rules, doctor_id, iso)))
            if slot["status"] == "BOOKED":
                live = appts.live_for_slot(conn, slot["id"])
                if live and live["patient_phone"] == phone and live["status"] == "BOOKED":   # idempotent retry
                    raise _Abort({"ok": True, "status": "ALREADY_BOOKED", "already_booked": True,
                                  "message": "This exact appointment was already booked for this number.",
                                  "appointment": _public(live)})
                raise _Abort(_fail("SLOT_TAKEN", "Someone else just took that slot.",
                                   alternatives=_alternatives(conn, clock, rules, doctor_id, iso)))
            clash = conn.execute(
                "SELECT appointment_ref, doctor_id FROM appointments WHERE patient_phone=? AND appointment_date=? "
                "AND appointment_time=? AND status='BOOKED'", (phone, iso, hhmm)).fetchone()
            if clash:
                raise _Abort(_fail("PHONE_CONFLICT", f"This number already has an appointment at {to_12h(hhmm)} on that day ({clash[0]}).",
                                   existing_ref=clash[0]))
            same_doc = conn.execute(
                "SELECT appointment_ref, appointment_time FROM appointments WHERE patient_phone=? AND doctor_id=? "
                "AND appointment_date=? AND status='BOOKED'", (phone, doctor_id, iso)).fetchone()
            if same_doc:
                raise _Abort(_fail("DUPLICATE_SAME_DAY",
                                   f"This number already sees {doctor['name']} that day at {to_12h(same_doc[1])} ({same_doc[0]}).",
                                   existing_ref=same_doc[0]))
            if dry_run:
                raise _Abort({"ok": True, "status": "VALID", "message": "Slot is free and the request is valid.",
                              "doctor": {"id": doctor["id"], "name": doctor["name"], "speciality": doctor["speciality"],
                                         "consultation_fee": doctor["consultation_fee"]},
                              "appointment_date": iso, "appointment_time": hhmm, "patient_phone": phone})
            moved = conn.execute("UPDATE appointment_slots SET status='BOOKED' WHERE id=? AND status='AVAILABLE'", (slot["id"],)).rowcount
            if moved != 1:
                raise _Abort(_fail("SLOT_TAKEN", "Someone else just took that slot.", alternatives=_alternatives(conn, clock, rules, doctor_id, iso)))
            if fault:
                fault("after_slot_reserved")
            ref = appts.new_ref(conn)
            cur = conn.execute(
                """INSERT INTO appointments (appointment_ref, slot_id, doctor_id, patient_phone, appointment_date,
                   appointment_time, status, call_session_id, created_at) VALUES (?,?,?,?,?,?,'BOOKED',?,?)""",
                (ref, slot["id"], doctor_id, phone, iso, hhmm, call_id, clock.utc_iso()))
            if fault:
                fault("after_appointment_inserted")
            log_id = logs.add_activity(conn, clock.utc_iso(), "appointment.created",
                                       f"{ref} booked with {doctor['name']} on {iso} at {to_12h(hhmm)}",
                                       call_id=call_id, appointment_id=cur.lastrowid,
                                       payload={"ref": ref, "doctor_id": doctor_id})
        created = appts.get_by_id(conn, cur.lastrowid)
        return {"ok": True, "status": "BOOKED", "message": "Appointment booked and saved.",
                "appointment": _public(created), "activity_id": log_id}
    except _Abort as a:
        return a.result
    except sqlite3.IntegrityError:
        return _fail("SLOT_TAKEN", "That slot was just taken or the data was invalid. Nothing was booked.",
                     alternatives=_alternatives(conn, clock, rules, doctor_id, iso))
    except sqlite3.Error as e:
        return _fail("DB_ERROR", "A database error occurred. Nothing was booked. Do not tell the caller it succeeded.", detail=str(e))
    except Exception as e:   # fault-injection or unexpected failure: transaction already rolled back
        return _fail("DB_ERROR", "Booking failed and was rolled back. Nothing was booked.", detail=str(e))


class _Abort(Exception):
    def __init__(self, result: dict):
        self.result = result


# ------------------------------------------------------------------ cancellation
def find_appointments(conn: sqlite3.Connection, phone: str, include_history: bool = False) -> list[dict]:
    statuses = None if include_history else ACTIVE
    return [_public(a) for a in appts.for_phone(conn, phone, statuses)]


def cancel_appointment(conn: sqlite3.Connection, clock: Clock, rules: Rules, *, patient_phone: str,
                       appointment_id: int | str | None = None, cancel_all: bool = False,
                       call_id: str | None = None, dry_run: bool = False,
                       fault: Callable[[str], None] | None = None) -> dict:
    ph = validate_phone(patient_phone, rules.phone_region)
    if not ph.ok:
        return _fail("INVALID_PHONE", ph.message)
    phone = ph.digits
    complete_past(conn, clock)
    history = appts.for_phone(conn, phone)
    if not history:
        return _fail("NO_APPOINTMENTS", "There are no appointments for this phone number.")

    target: list[dict]
    if appointment_id not in (None, ""):
        row = None
        if str(appointment_id).isdigit():
            row = appts.get_by_id(conn, int(appointment_id))
        if row is None:
            row = appts.get_by_ref(conn, str(appointment_id))
        if row is None or row["patient_phone"] != phone:      # never reveal other numbers' bookings
            return _fail("APPOINTMENT_NOT_FOUND", "No appointment with that ID exists for this phone number.",
                         appointments=[_public(a) for a in history if a["status"] == "BOOKED"])
        if row["status"] == "CANCELLED":
            return _fail("ALREADY_CANCELLED", f"{row['appointment_ref']} was already cancelled.", appointment=_public(row))
        if row["status"] == "COMPLETED":
            return _fail("CANNOT_CANCEL_COMPLETED", f"{row['appointment_ref']} has already taken place and cannot be cancelled.", appointment=_public(row))
        target = [row]
    else:
        live = [a for a in history if a["status"] == "BOOKED"]
        if not live:
            cancelled = [a for a in history if a["status"] == "CANCELLED"]
            msg = "All appointments for this number are already cancelled or completed."
            return _fail("NO_ACTIVE_APPOINTMENTS", msg, appointments=[_public(a) for a in history][:5], cancelled_count=len(cancelled))
        if cancel_all:
            target = live
        elif len(live) > 1:
            return {"ok": False, "status": "NEEDS_SELECTION", "message": "Several active appointments. Ask which one to cancel.",
                    "appointments": [_public(a) for a in live]}
        else:
            target = live

    if dry_run:
        return {"ok": True, "status": "WOULD_CANCEL", "targets": [_public(a) for a in target]}
    try:
        with db.transaction(conn):
            done = []
            for a in target:
                n = conn.execute("UPDATE appointments SET status='CANCELLED', cancelled_at=?, cancelled_by_call_id=? "
                                 "WHERE id=? AND status='BOOKED'", (clock.utc_iso(), call_id, a["id"])).rowcount
                if n != 1:     # lost a race with a concurrent cancel
                    continue
                leave = docs.leave_on(conn, a["doctor_id"], a["appointment_date"])
                hol = docs.holiday_on(conn, a["appointment_date"])
                conn.execute("UPDATE appointment_slots SET status=? WHERE id=?", ("BLOCKED" if (leave or hol) else "AVAILABLE", a["slot_id"]))
                if fault:
                    fault("after_cancel_update")
                logs.add_activity(conn, clock.utc_iso(), "appointment.cancelled",
                                  f"{a['appointment_ref']} with {a['doctor_name']} on {a['appointment_date']} cancelled",
                                  call_id=call_id, appointment_id=a["id"], payload={"ref": a["appointment_ref"]})
                done.append(a["id"])
        if not done:
            return _fail("ALREADY_CANCELLED", "That appointment was just cancelled by another request.")
        out = [_public(appts.get_by_id(conn, i)) for i in done]
        return {"ok": True, "status": "CANCELLED", "message": "Appointment cancelled and the slot released.", "cancelled": out}
    except sqlite3.Error as e:
        return _fail("DB_ERROR", "A database error occurred. Nothing was cancelled.", detail=str(e))
    except Exception as e:
        return _fail("DB_ERROR", "Cancellation failed and was rolled back. Nothing was cancelled.", detail=str(e))


def complete_past(conn: sqlite3.Connection, clock: Clock) -> int:
    """BOOKED appointments whose slot has ended become COMPLETED (and can no longer be cancelled)."""
    now = clock.now()
    n = 0
    rows = conn.execute(
        """SELECT a.id, a.appointment_date, a.appointment_time, d.slot_minutes FROM appointments a
           JOIN doctors d ON d.id = a.doctor_id WHERE a.status='BOOKED' AND a.appointment_date <= ?""",
        (now.date().isoformat(),)).fetchall()
    for r in rows:
        if clock.slot_dt(r["appointment_date"], r["appointment_time"]) + timedelta(minutes=r["slot_minutes"]) <= now:
            n += conn.execute("UPDATE appointments SET status='COMPLETED' WHERE id=? AND status='BOOKED'", (r["id"],)).rowcount
    return n
