"""SQLite access: schema, connections, transactions.

Every operation opens its own short-lived connection (WAL mode + busy timeout). Writes use
BEGIN IMMEDIATE so competing writers queue instead of interleaving - this is what makes
booking and cancellation safe under concurrent calls.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    speciality       TEXT    NOT NULL,
    experience_years INTEGER NOT NULL CHECK (experience_years >= 0),
    consultation_fee INTEGER NOT NULL CHECK (consultation_fee >= 0),
    slot_minutes     INTEGER NOT NULL DEFAULT 30 CHECK (slot_minutes BETWEEN 10 AND 120),
    bio              TEXT    NOT NULL DEFAULT '',
    active           INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_doctors_speciality ON doctors (speciality);

CREATE TABLE IF NOT EXISTS doctor_schedules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id   INTEGER NOT NULL REFERENCES doctors (id) ON DELETE CASCADE,
    weekday     INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),   -- Monday = 0
    start_time  TEXT    NOT NULL,
    end_time    TEXT    NOT NULL,
    break_start TEXT,
    break_end   TEXT,
    UNIQUE (doctor_id, weekday)
);

CREATE TABLE IF NOT EXISTS holidays (
    date TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctor_leave (
    doctor_id INTEGER NOT NULL REFERENCES doctors (id) ON DELETE CASCADE,
    date      TEXT    NOT NULL,
    reason    TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (doctor_id, date)
);

CREATE TABLE IF NOT EXISTS appointment_slots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL REFERENCES doctors (id) ON DELETE CASCADE,
    slot_date TEXT    NOT NULL,
    slot_time TEXT    NOT NULL,
    status    TEXT    NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE', 'BOOKED', 'BLOCKED')),
    UNIQUE (doctor_id, slot_date, slot_time)
);
CREATE INDEX IF NOT EXISTS idx_slots_date_status   ON appointment_slots (slot_date, status);
CREATE INDEX IF NOT EXISTS idx_slots_doctor_date   ON appointment_slots (doctor_id, slot_date, status);

CREATE TABLE IF NOT EXISTS call_sessions (
    id             TEXT PRIMARY KEY,
    state          TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    connected_at   TEXT,
    ended_at       TEXT,
    end_reason     TEXT,
    verified_phone TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_started ON call_sessions (started_at DESC);

CREATE TABLE IF NOT EXISTS appointments (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_ref       TEXT    NOT NULL UNIQUE,
    slot_id               INTEGER NOT NULL REFERENCES appointment_slots (id),
    doctor_id             INTEGER NOT NULL REFERENCES doctors (id),
    patient_phone         TEXT    NOT NULL,
    appointment_date      TEXT    NOT NULL,
    appointment_time      TEXT    NOT NULL,
    status                TEXT    NOT NULL CHECK (status IN ('BOOKED', 'CANCELLED', 'COMPLETED')),
    call_session_id       TEXT REFERENCES call_sessions (id),
    created_at            TEXT    NOT NULL,
    cancelled_at          TEXT,
    cancelled_by_call_id  TEXT REFERENCES call_sessions (id)
);
-- A slot can have many CANCELLED rows (history) but only one live appointment.
CREATE UNIQUE INDEX IF NOT EXISTS uq_appointments_live_slot
    ON appointments (slot_id) WHERE status IN ('BOOKED', 'COMPLETED');
CREATE INDEX IF NOT EXISTS idx_appt_phone  ON appointments (patient_phone, status);
CREATE INDEX IF NOT EXISTS idx_appt_date   ON appointments (appointment_date, status);
CREATE INDEX IF NOT EXISTS idx_appt_doctor ON appointments (doctor_id, appointment_date);

CREATE TABLE IF NOT EXISTS call_transcripts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id    TEXT NOT NULL REFERENCES call_sessions (id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'agent', 'system')),
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcripts_call ON call_transcripts (call_id, id);

CREATE TABLE IF NOT EXISTS activity_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type     TEXT NOT NULL,
    call_id        TEXT,
    appointment_id INTEGER,
    message        TEXT NOT NULL,
    payload        TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_logs (id DESC);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a connection in autocommit mode (we manage transactions explicitly)."""
    p = str(path)
    if p != ":memory:":
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    if p != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def session(path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT, ROLLBACK on any error."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
