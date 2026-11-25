"""activity_logs, call_sessions and call_transcripts."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def add_activity(conn: sqlite3.Connection, now_iso: str, event_type: str, message: str, *,
                 call_id: str | None = None, appointment_id: int | None = None,
                 payload: dict[str, Any] | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO activity_logs (event_type, call_id, appointment_id, message, payload, created_at) VALUES (?,?,?,?,?,?)",
        (event_type, call_id, appointment_id, message, json.dumps(payload or {}, default=str), now_iso))
    return int(cur.lastrowid)


def list_activity(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"] or "{}")
        out.append(d)
    return out


# ------------------------------------------------------------------ calls
def create_call(conn: sqlite3.Connection, call_id: str, now_iso: str) -> None:
    conn.execute("INSERT INTO call_sessions (id, state, started_at) VALUES (?,?,?)", (call_id, "connecting", now_iso))


def update_call(conn: sqlite3.Connection, call_id: str, **fields: Any) -> None:
    allowed = {"state", "connected_at", "ended_at", "end_reason", "verified_phone"}
    cols = [k for k in fields if k in allowed]
    if not cols:
        return
    conn.execute(f"UPDATE call_sessions SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                 [fields[c] for c in cols] + [call_id])


def list_calls(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """SELECT c.*, (SELECT COUNT(*) FROM call_transcripts t WHERE t.call_id = c.id) AS message_count
           FROM call_sessions c ORDER BY c.started_at DESC LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]


def add_transcript(conn: sqlite3.Connection, call_id: str, role: str, text: str, now_iso: str) -> int:
    cur = conn.execute("INSERT INTO call_transcripts (call_id, role, text, created_at) VALUES (?,?,?,?)",
                       (call_id, role, text, now_iso))
    return int(cur.lastrowid)


def get_transcript(conn: sqlite3.Connection, call_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, role, text, created_at FROM call_transcripts WHERE call_id = ? ORDER BY id", (call_id,))]


def end_dangling_calls(conn: sqlite3.Connection, now_iso: str) -> int:
    """After a crash/restart no call can still be live."""
    cur = conn.execute(
        "UPDATE call_sessions SET state='ended', ended_at=?, end_reason='server_restart' WHERE state IN ('connecting','connected')",
        (now_iso,))
    return cur.rowcount
