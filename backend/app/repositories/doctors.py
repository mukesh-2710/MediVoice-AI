"""Doctor, schedule, holiday and leave queries."""
from __future__ import annotations

import difflib
import re
import sqlite3

SPECIALITY_ALIASES = {
    "heart": "Cardiologist", "cardio": "Cardiologist", "cardiology": "Cardiologist", "cardiologist": "Cardiologist",
    "gp": "General Physician", "general": "General Physician", "physician": "General Physician", "family doctor": "General Physician",
    "fever": "General Physician", "cold": "General Physician", "general practitioner": "General Physician",
    "skin": "Dermatologist", "derma": "Dermatologist", "dermatology": "Dermatologist", "dermatologist": "Dermatologist",
    "bone": "Orthopedic", "ortho": "Orthopedic", "orthopedic": "Orthopedic", "orthopaedic": "Orthopedic",
    "orthopedist": "Orthopedic", "joint": "Orthopedic",
    "brain": "Neurologist", "neuro": "Neurologist", "neurology": "Neurologist", "neurologist": "Neurologist",
    "child": "Pediatrician", "children": "Pediatrician", "kids": "Pediatrician", "baby": "Pediatrician",
    "pediatric": "Pediatrician", "paediatrician": "Pediatrician", "pediatrician": "Pediatrician",
    "teeth": "Dentist", "tooth": "Dentist", "dental": "Dentist", "dentist": "Dentist",
    "ent": "ENT", "ear": "ENT", "nose": "ENT", "throat": "ENT", "ear nose throat": "ENT",
}


def _row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


def list_doctors(conn: sqlite3.Connection, include_inactive: bool = False) -> list[dict]:
    q = "SELECT * FROM doctors" + ("" if include_inactive else " WHERE active = 1") + " ORDER BY speciality, name"
    docs = [dict(r) for r in conn.execute(q)]
    sched: dict[int, list[dict]] = {}
    for s in conn.execute("SELECT * FROM doctor_schedules ORDER BY doctor_id, weekday"):
        sched.setdefault(s["doctor_id"], []).append(dict(s))
    for d in docs:
        d["schedule"] = sched.get(d["id"], [])
    return docs


def get_doctor(conn: sqlite3.Connection, doctor_id: int) -> dict | None:
    d = _row(conn.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,)).fetchone())
    if d:
        d["schedule"] = [dict(r) for r in conn.execute(
            "SELECT * FROM doctor_schedules WHERE doctor_id = ? ORDER BY weekday", (doctor_id,))]
    return d


def specialities(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT speciality FROM doctors WHERE active = 1 ORDER BY 1")]


def _norm_name(s: str) -> str:
    s = re.sub(r"\b(dr|doctor|mr|ms|mrs)\b\.?", " ", s.lower())
    return re.sub(r"[^a-z ]+", " ", s).strip()


def find_doctors_by_name(conn: sqlite3.Connection, name: str) -> list[dict]:
    """Exact / substring / fuzzy match on a spoken doctor name (STT often mangles names)."""
    target = _norm_name(name)
    if not target:
        return []
    docs = list_doctors(conn)
    scored: list[tuple[float, dict]] = []
    for d in docs:
        full = _norm_name(d["name"])
        parts = full.split()
        score = 0.0
        if target == full:
            score = 1.0
        elif target in full or any(p == target for p in parts):
            score = 0.92
        else:
            score = max([difflib.SequenceMatcher(None, target, full).ratio()]
                        + [difflib.SequenceMatcher(None, target, p).ratio() for p in parts])
        if score >= 0.78:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.92:
        top = scored[0][0]
        return [d for s, d in scored if s >= top - 0.001]
    return [d for _, d in scored]


def resolve_speciality(conn: sqlite3.Connection, text: str) -> str | None:
    t = re.sub(r"[^a-z ]+", " ", (text or "").lower()).strip()
    if not t:
        return None
    known = {s.lower(): s for s in specialities(conn)}
    if t in known:
        return known[t]
    if t in SPECIALITY_ALIASES and SPECIALITY_ALIASES[t] in known.values():
        return SPECIALITY_ALIASES[t]
    for word in t.split():
        if word in SPECIALITY_ALIASES and SPECIALITY_ALIASES[word] in known.values():
            return SPECIALITY_ALIASES[word]
    keys = list(known) + list(SPECIALITY_ALIASES)
    close = difflib.get_close_matches(t, keys, n=1, cutoff=0.8)
    if close:
        k = close[0]
        return known.get(k) or SPECIALITY_ALIASES.get(k)
    return None


def doctors_in_speciality(conn: sqlite3.Connection, speciality: str) -> list[dict]:
    return [d for d in list_doctors(conn) if d["speciality"] == speciality]


def schedule_for(conn: sqlite3.Connection, doctor_id: int, weekday: int) -> dict | None:
    return _row(conn.execute("SELECT * FROM doctor_schedules WHERE doctor_id=? AND weekday=?", (doctor_id, weekday)).fetchone())


def holiday_on(conn: sqlite3.Connection, iso_date: str) -> str | None:
    r = conn.execute("SELECT name FROM holidays WHERE date = ?", (iso_date,)).fetchone()
    return r[0] if r else None


def leave_on(conn: sqlite3.Connection, doctor_id: int, iso_date: str) -> str | None:
    r = conn.execute("SELECT reason FROM doctor_leave WHERE doctor_id=? AND date=?", (doctor_id, iso_date)).fetchone()
    return (r[0] or "on leave") if r else None
