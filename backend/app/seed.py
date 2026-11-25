"""Seed data: 12 doctors, 8 specialities, schedules (incl. weekends), holidays, sample appointments."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .repositories import appointments as appt_repo
from .repositories import logs, slots
from .utils.clock import Clock

MON_FRI, MON_SAT, ALL = [0, 1, 2, 3, 4], [0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5, 6]

# (name, speciality, years, fee, slot_min, bio, [(weekdays, start, end, break_start, break_end)])
DOCTORS = [
    ("Dr. Anika Sharma", "Cardiologist", 14, 1200, 30, "Preventive cardiology and heart failure care.",
     [(MON_FRI, "09:00", "17:00", "13:00", "14:00")]),
    ("Dr. Rohan Mehta", "Cardiologist", 9, 900, 30, "Interventional cardiology; also sees patients on Saturdays.",
     [([1, 2, 3, 4, 5], "10:00", "18:00", "13:30", "14:30")]),
    ("Dr. Priya Nair", "General Physician", 11, 500, 20, "Family medicine, fevers, diabetes and BP follow-ups.",
     [(MON_SAT, "09:00", "17:00", "13:00", "14:00")]),
    ("Dr. Imran Qureshi", "General Physician", 6, 400, 20, "Evening and weekend clinic for working patients.",
     [(MON_FRI, "16:00", "20:00", None, None), ([5, 6], "10:00", "14:00", None, None)]),
    ("Dr. Kavya Reddy", "Dermatologist", 8, 800, 30, "Acne, eczema, hair and skin allergy care.",
     [([0, 2, 4], "10:00", "16:00", "13:00", "14:00")]),
    ("Dr. Arjun Iyer", "Orthopedic", 16, 1000, 30, "Sports injuries, joint pain and fracture follow-up.",
     [(MON_FRI, "09:00", "15:00", "12:30", "13:30")]),
    ("Dr. Sneha Kulkarni", "Neurologist", 12, 1500, 30, "Migraine, epilepsy and neuropathy.",
     [([1, 3, 5], "10:00", "16:00", "13:00", "14:00")]),
    ("Dr. Vikram Singh", "Pediatrician", 10, 600, 20, "Newborn care, vaccinations and growth checks.",
     [(MON_SAT, "09:00", "13:00", None, None)]),
    ("Dr. Meera Joshi", "Pediatrician", 5, 450, 20, "Afternoon paediatric clinic.",
     [(MON_FRI, "14:00", "19:00", None, None), ([5], "09:00", "13:00", None, None)]),
    ("Dr. Farah Khan", "Dentist", 7, 700, 30, "Root canals, scaling and cosmetic dentistry.",
     [(MON_SAT, "10:00", "18:00", "13:00", "14:00")]),
    ("Dr. Suresh Rao", "ENT", 13, 850, 30, "Sinus, hearing and throat conditions.",
     [(MON_FRI, "11:00", "17:00", "13:30", "14:30")]),
    ("Dr. Lakshmi Prasad", "ENT", 4, 600, 30, "Works Wednesday to Sunday.",
     [([2, 3, 4, 5, 6], "09:00", "15:00", None, None)]),
]


def is_seeded(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] > 0


def seed(conn: sqlite3.Connection, clock: Clock, horizon_days: int = 28, with_samples: bool = True) -> None:
    today = clock.today()
    conn.execute("BEGIN IMMEDIATE")
    for name, spec, yrs, fee, mins, bio, blocks in DOCTORS:
        cur = conn.execute(
            "INSERT INTO doctors (name, speciality, experience_years, consultation_fee, slot_minutes, bio) VALUES (?,?,?,?,?,?)",
            (name, spec, yrs, fee, mins, bio))
        for weekdays, start, end, bs, be in blocks:
            for wd in weekdays:
                conn.execute(
                    "INSERT INTO doctor_schedules (doctor_id, weekday, start_time, end_time, break_start, break_end) VALUES (?,?,?,?,?,?)",
                    (cur.lastrowid, wd, start, end, bs, be))
    for d, n in [(today + timedelta(days=8), "Clinic maintenance day"), (date(2026, 12, 25), "Christmas Day"),
                 (date(2027, 1, 1), "New Year's Day"), (date(2027, 1, 26), "Republic Day")]:
        conn.execute("INSERT OR IGNORE INTO holidays (date, name) VALUES (?,?)", (d.isoformat(), n))
    conn.execute("COMMIT")
    slots.ensure_slots(conn, today, horizon_days)
    if with_samples:
        _samples(conn, clock)


def _samples(conn: sqlite3.Connection, clock: Clock) -> None:
    today, now = clock.today(), clock.utc_iso()

    def put(doctor: str, offset: int, hhmm: str, phone: str, status: str) -> None:
        d = (today + timedelta(days=offset)).isoformat()
        did = conn.execute("SELECT id FROM doctors WHERE name = ?", (doctor,)).fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO appointment_slots (doctor_id, slot_date, slot_time, status) VALUES (?,?,?,?)",
                     (did, d, hhmm, "AVAILABLE"))
        sid = conn.execute("SELECT id, status FROM appointment_slots WHERE doctor_id=? AND slot_date=? AND slot_time=?",
                           (did, d, hhmm)).fetchone()
        if status != "CANCELLED":
            if sid["status"] != "AVAILABLE":
                return
            conn.execute("UPDATE appointment_slots SET status='BOOKED' WHERE id=?", (sid["id"],))
        conn.execute(
            """INSERT INTO appointments (appointment_ref, slot_id, doctor_id, patient_phone, appointment_date,
               appointment_time, status, created_at, cancelled_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (appt_repo.new_ref(conn), sid["id"], did, phone, d, hhmm, status, now, now if status == "CANCELLED" else None))

    conn.execute("BEGIN IMMEDIATE")
    put("Dr. Priya Nair", -5, "10:00", "9123456780", "COMPLETED")
    put("Dr. Anika Sharma", -3, "11:00", "9988776655", "COMPLETED")
    put("Dr. Farah Khan", -2, "15:00", "9123456780", "COMPLETED")
    put("Dr. Kavya Reddy", 3, "11:00", "9876501234", "BOOKED")
    put("Dr. Arjun Iyer", 4, "09:30", "9876501234", "BOOKED")
    put("Dr. Priya Nair", 2, "10:20", "9012345678", "BOOKED")
    put("Dr. Suresh Rao", 5, "12:00", "8899001122", "CANCELLED")
    put("Dr. Vikram Singh", 6, "09:40", "7007007007", "CANCELLED")
    conn.execute("COMMIT")
    logs.add_activity(conn, now, "system.seeded", "Sample appointments created")
