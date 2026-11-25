"""appointments table access."""
from __future__ import annotations

import secrets
import sqlite3

_SELECT = """
SELECT a.id, a.appointment_ref, a.slot_id, a.doctor_id, d.name AS doctor_name, d.speciality,
       d.consultation_fee, a.patient_phone, a.appointment_date, a.appointment_time, a.status,
       a.call_session_id, a.created_at, a.cancelled_at, a.cancelled_by_call_id
FROM appointments a JOIN doctors d ON d.id = a.doctor_id
"""


def new_ref(conn: sqlite3.Connection) -> str:
    """Short, speakable, unique reference such as MV-483920."""
    for _ in range(20):
        ref = f"MV-{secrets.randbelow(900000) + 100000}"
        if not conn.execute("SELECT 1 FROM appointments WHERE appointment_ref = ?", (ref,)).fetchone():
            return ref
    raise RuntimeError("could not allocate a unique appointment reference")


def get_by_id(conn: sqlite3.Connection, appt_id: int) -> dict | None:
    r = conn.execute(_SELECT + " WHERE a.id = ?", (appt_id,)).fetchone()
    return dict(r) if r else None


def get_by_ref(conn: sqlite3.Connection, ref: str) -> dict | None:
    r = conn.execute(_SELECT + " WHERE a.appointment_ref = ?", (ref.strip().upper(),)).fetchone()
    return dict(r) if r else None


def for_phone(conn: sqlite3.Connection, phone: str, statuses: tuple[str, ...] | None = None) -> list[dict]:
    q = _SELECT + " WHERE a.patient_phone = ?"
    args: list = [phone]
    if statuses:
        q += f" AND a.status IN ({','.join('?' * len(statuses))})"
        args += list(statuses)
    q += " ORDER BY a.appointment_date, a.appointment_time, a.id"
    return [dict(r) for r in conn.execute(q, args)]


def search(conn: sqlite3.Connection, *, status: str | None = None, phone: str | None = None,
           date_from: str | None = None, date_to: str | None = None, doctor_id: int | None = None,
           text: str | None = None, limit: int = 500) -> list[dict]:
    q, args = _SELECT + " WHERE 1=1", []
    if status:
        q += " AND a.status = ?"; args.append(status.upper())
    if phone:
        q += " AND a.patient_phone LIKE ?"; args.append(f"%{phone}%")
    if date_from:
        q += " AND a.appointment_date >= ?"; args.append(date_from)
    if date_to:
        q += " AND a.appointment_date <= ?"; args.append(date_to)
    if doctor_id:
        q += " AND a.doctor_id = ?"; args.append(doctor_id)
    if text:
        q += " AND (d.name LIKE ? OR d.speciality LIKE ? OR a.appointment_ref LIKE ?)"
        args += [f"%{text}%"] * 3
    q += " ORDER BY a.appointment_date DESC, a.appointment_time DESC, a.id DESC LIMIT ?"
    args.append(max(1, min(limit, 2000)))
    return [dict(r) for r in conn.execute(q, args)]


def live_for_slot(conn: sqlite3.Connection, slot_id: int) -> dict | None:
    r = conn.execute(_SELECT + " WHERE a.slot_id = ? AND a.status IN ('BOOKED','COMPLETED')", (slot_id,)).fetchone()
    return dict(r) if r else None
