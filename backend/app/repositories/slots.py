"""appointment_slots queries and slot generation."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta


def _t(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def generate_times(start: str, end: str, step: int, break_start: str | None, break_end: str | None) -> list[str]:
    out, cur = [], _t(start)
    bs = _t(break_start) if break_start else None
    be = _t(break_end) if break_end else None
    while cur + step <= _t(end):
        in_break = bs is not None and be is not None and cur < be and cur + step > bs
        if not in_break:
            out.append(_fmt(cur))
        cur += step
    return out


def ensure_slots(conn: sqlite3.Connection, start: date, days: int) -> int:
    """Idempotently create slots for [start, start+days). Holidays and doctor leave become BLOCKED
    only if the slot is created fresh; existing BOOKED slots are never touched."""
    created = 0
    holidays = {r[0] for r in conn.execute("SELECT date FROM holidays")}
    leave = {(r[0], r[1]) for r in conn.execute("SELECT doctor_id, date FROM doctor_leave")}
    scheds: dict[int, dict[int, sqlite3.Row]] = {}
    for s in conn.execute("SELECT * FROM doctor_schedules"):
        scheds.setdefault(s["doctor_id"], {})[s["weekday"]] = s
    docs = conn.execute("SELECT id, slot_minutes FROM doctors WHERE active = 1").fetchall()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for d in docs:
            for offset in range(days):
                day = start + timedelta(days=offset)
                iso = day.isoformat()
                if iso in holidays:
                    continue
                s = scheds.get(d["id"], {}).get(day.weekday())
                if not s:
                    continue
                status = "BLOCKED" if (d["id"], iso) in leave else "AVAILABLE"
                for t in generate_times(s["start_time"], s["end_time"], d["slot_minutes"], s["break_start"], s["break_end"]):
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO appointment_slots (doctor_id, slot_date, slot_time, status) VALUES (?,?,?,?)",
                        (d["id"], iso, t, status))
                    created += cur.rowcount
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return created


def get_slot(conn: sqlite3.Connection, doctor_id: int, iso_date: str, hhmm: str) -> dict | None:
    r = conn.execute("SELECT * FROM appointment_slots WHERE doctor_id=? AND slot_date=? AND slot_time=?",
                     (doctor_id, iso_date, hhmm)).fetchone()
    return dict(r) if r else None


def available_times(conn: sqlite3.Connection, doctor_id: int, iso_date: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT slot_time FROM appointment_slots WHERE doctor_id=? AND slot_date=? AND status='AVAILABLE' ORDER BY slot_time",
        (doctor_id, iso_date))]


def available_dates(conn: sqlite3.Connection, doctor_id: int, from_iso: str, limit: int = 60) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT slot_date FROM appointment_slots WHERE doctor_id=? AND slot_date>=? AND status='AVAILABLE' ORDER BY slot_date LIMIT ?",
        (doctor_id, from_iso, limit))]


def count_available(conn: sqlite3.Connection, from_iso: str, now_hhmm_today: str | None = None) -> int:
    q = "SELECT COUNT(*) FROM appointment_slots WHERE status='AVAILABLE' AND slot_date > ?"
    n = conn.execute(q, (from_iso,)).fetchone()[0]
    args: tuple = (from_iso,)
    q2 = "SELECT COUNT(*) FROM appointment_slots WHERE status='AVAILABLE' AND slot_date = ?"
    if now_hhmm_today:
        q2 += " AND slot_time > ?"
        args = (from_iso, now_hhmm_today)
    return n + conn.execute(q2, args).fetchone()[0]


def block_available_slots(conn: sqlite3.Connection, doctor_id: int, iso_date: str) -> int:
    return conn.execute("UPDATE appointment_slots SET status='BLOCKED' WHERE doctor_id=? AND slot_date=? AND status='AVAILABLE'",
                        (doctor_id, iso_date)).rowcount


def upcoming_slots_for_day(conn: sqlite3.Connection, iso_date: str) -> list[dict]:
    rows = conn.execute(
        """SELECT s.doctor_id, s.slot_date, s.slot_time, s.status FROM appointment_slots s
           WHERE s.slot_date = ? ORDER BY s.doctor_id, s.slot_time""", (iso_date,)).fetchall()
    return [dict(r) for r in rows]
