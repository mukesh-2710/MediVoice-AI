"""Server-side tool execution. Every argument is untrusted (LLM output derived from speech).

Safety properties enforced here, not in the prompt:
  * phone must be read back AND the caller's next utterance must be affirmative before it is "verified";
  * booking/cancelling are two-phase: propose -> caller says yes (checked on the transcript) -> execute;
  * results are only ever produced from committed database state;
  * call_session_id comes from the server-side session, never from the model.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any, Callable

from .. import database as db
from ..repositories import logs
from ..services import availability as av
from ..services import booking as bk
from ..services.rules import Rules
from ..utils.clock import Clock
from ..utils.confirm import is_affirmative, is_negative
from ..utils.dates import normalize_spoken_date, parse_time_text, speak_date, to_12h
from ..utils.phone import speak_digits, validate_phone
from ..voice.session import CallSession
from ..websocket.bus import EventBus

log = logging.getLogger("medivoice.tools")


def _err(status: str, message: str, **extra: Any) -> dict:
    return {"ok": False, "status": status, "message": message, **extra}


def _s(args: dict, key: str) -> str | None:
    v = args.get(key)
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _b(args: dict, key: str) -> bool:
    v = args.get(key)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"true", "yes", "1"}


class ToolRuntime:
    def __init__(self, db_path: str, clock: Clock, rules: Rules, bus: EventBus,
                 fault_factory: Callable[[], Callable[[str], None] | None] | None = None):
        self.db_path, self.clock, self.rules, self.bus = db_path, clock, rules, bus
        self._fault = fault_factory or (lambda: None)

    # ------------------------------------------------------------ dispatch
    async def dispatch(self, name: str, session: CallSession, args: Any) -> dict:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return _err("UNKNOWN_TOOL", f"No tool named {name}.")
        if not isinstance(args, dict):
            return _err("INVALID_ARGUMENTS", "Tool arguments must be an object.")
        async with session.lock:              # serialise tools within one call (duplicate/delayed commands)
            session.inflight_tools += 1
            try:
                result = await handler(session, args)
            except Exception as exc:           # never leak a stack trace to the model
                log.exception("tool %s crashed", name)
                result = _err("TOOL_ERROR", "Something went wrong on our side. Nothing was changed. Apologise and offer to try again.", detail=type(exc).__name__)
            finally:
                session.inflight_tools -= 1
        if session.ended:
            await self._log("tool.completed_after_hangup", f"{name} finished after the call ended: {result.get('status')}", session)
        log.info("tool=%s call=%s status=%s", name, session.call_id[:8], result.get("status"))
        return result

    async def _db(self, fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
        def run() -> Any:
            with db.session(self.db_path) as conn:
                return fn(conn, *a, **kw)
        return await asyncio.to_thread(run)

    async def _log(self, type_: str, message: str, session: CallSession) -> None:
        await self._db(lambda c: logs.add_activity(c, self.clock.utc_iso(), type_, message, call_id=session.call_id))

    # ------------------------------------------------------------ phone
    async def tool_record_phone_number(self, session: CallSession, args: dict) -> dict:
        res = validate_phone(_s(args, "spoken_phone") or "", self.rules.phone_region)
        session.verified_phone = None
        session.pending_phone = None
        session.reset_pending()
        if not res.ok:
            return _err("INVALID_PHONE", res.message, reason=res.reason)
        session.pending_phone = res.digits
        return {"ok": True, "status": "READ_BACK_REQUIRED", "phone_digits": res.digits, "read_back": speak_digits(res.digits),
                "message": f"Read this back digit by digit: {speak_digits(res.digits)}. Ask if it is correct, then call confirm_phone_number."}

    async def tool_confirm_phone_number(self, session: CallSession, args: dict) -> dict:
        if not session.pending_phone:
            return _err("NO_PENDING_PHONE", "No phone number is waiting for confirmation. Ask for the number first.")
        if not _b(args, "is_correct") or is_negative(session.last_user_text):
            session.pending_phone = None
            return {"ok": False, "status": "PHONE_REJECTED", "message": "Number rejected. Ask the caller to say it again."}
        if not is_affirmative(session.last_user_text):
            return _err("CONFIRMATION_NOT_HEARD",
                        "The caller has not clearly said yes yet. Read the number back and wait for their answer.")
        session.verified_phone = session.pending_phone
        session.pending_phone = None
        await self._db(lambda c: c.execute("UPDATE call_sessions SET verified_phone=? WHERE id=?", (session.verified_phone, session.call_id)))
        return {"ok": True, "status": "PHONE_CONFIRMED", "message": "Phone number confirmed."}

    def _phone_gate(self, session: CallSession, spoken: str | None) -> dict | None:
        if not session.verified_phone:
            return _err("PHONE_NOT_CONFIRMED", "The caller's phone number is not confirmed yet. Use record_phone_number, read it back, and confirm it.")
        res = validate_phone(spoken or "", self.rules.phone_region)
        if not res.ok or res.digits != session.verified_phone:
            return _err("PHONE_MISMATCH", "patient_phone must be the number the caller confirmed. If they gave a new number, call record_phone_number again.")
        return None

    # ------------------------------------------------------------ availability
    async def tool_check_doctor_availability(self, session: CallSession, args: dict) -> dict:
        raw_date = _s(args, "requested_date")
        date_iso, extra = None, {}
        if raw_date:
            d = normalize_spoken_date(raw_date, self.clock.today())
            if d.reason == "AMBIGUOUS":
                return _err("AMBIGUOUS_DATE", d.message, options=d.options)
            if not d.ok:
                return _err("PAST_DATE" if d.reason == "PAST" else "INVALID_DATE", d.message)
            date_iso = d.value.isoformat()
            extra = {"resolved_date": date_iso, "resolved_date_spoken": speak_date(d.value, self.clock.today()),
                     "weekday": d.value.strftime("%A"),
                     "date_was_assumed": d.assumed}
            if d.assumed:
                extra["note"] = "Say the resolved date aloud and let the caller confirm it."
        doctor_id = args.get("doctor_id")
        try:
            doctor_id = int(doctor_id) if doctor_id not in (None, "") else None
        except (TypeError, ValueError):
            return _err("INVALID_ARGUMENTS", "doctor_id must be a number.")
        res = await self._db(av.check_availability, self.clock, self.rules, doctor_id=doctor_id,
                             doctor_name=_s(args, "doctor_name"), speciality=_s(args, "speciality"),
                             date_iso=date_iso, preferred_time=_s(args, "preferred_time"), earliest=_b(args, "earliest"))
        res.update(extra)
        return res

    async def tool_find_my_appointments(self, session: CallSession, args: dict) -> dict:
        if not session.verified_phone:
            return _err("PHONE_NOT_CONFIRMED", "Confirm the caller's phone number first.")
        rows = await self._db(bk.find_appointments, session.verified_phone)
        return {"ok": True, "status": "OK" if rows else "NO_APPOINTMENTS", "appointments": rows,
                "message": "Active appointments for the confirmed number." if rows else "No active appointments for this number."}

    # ------------------------------------------------------------ booking
    async def tool_book_appointment(self, session: CallSession, args: dict) -> dict:
        missing = [k for k in ("doctor_id", "patient_phone", "appointment_date", "appointment_time") if args.get(k) in (None, "")]
        if missing:
            return _err("INVALID_ARGUMENTS", f"Missing: {', '.join(missing)}. Ask the caller only for what is missing.")
        gate = self._phone_gate(session, _s(args, "patient_phone"))
        if gate:
            return gate
        d = normalize_spoken_date(str(args["appointment_date"]), self.clock.today())
        if not d.ok:
            return _err("PAST_DATE" if d.reason == "PAST" else "INVALID_DATE", d.message)
        iso = d.value.isoformat()
        hhmm = parse_time_text(str(args["appointment_time"]))
        if not hhmm:
            return _err("INVALID_TIME", "appointment_time must be like 11:00.")
        kw = dict(doctor_id=args["doctor_id"], patient_phone=session.verified_phone, appointment_date=iso,
                  appointment_time=hhmm, call_id=session.call_id)
        pre = await self._db(bk.book_appointment, self.clock, self.rules, dry_run=True, **kw)
        if pre["status"] == "ALREADY_BOOKED":
            return pre
        if not pre["ok"]:
            session.pending_booking = None
            return pre
        key = (int(args["doctor_id"]), iso, hhmm, session.verified_phone)
        if not _b(args, "details_confirmed") or session.pending_booking != key:
            session.pending_booking = key
            doc = pre["doctor"]
            return {"ok": False, "status": "NEEDS_CONFIRMATION",
                    "summary": {"doctor": doc["name"], "speciality": doc["speciality"], "date": speak_date(d.value, self.clock.today()),
                                "weekday": d.value.strftime("%A"), "time": to_12h(hhmm), "fee": doc["consultation_fee"],
                                "phone_read_back": speak_digits(session.verified_phone)},
                    "message": "Read this summary to the caller and ask 'Shall I book it?'. After a clear yes, call book_appointment again with details_confirmed=true."}
        if not is_affirmative(session.last_user_text):
            return _err("CONFIRMATION_NOT_HEARD", "The caller has not clearly said yes to the booking. Ask them and wait.")
        result = await self._db(bk.book_appointment, self.clock, self.rules, fault=self._fault(), **kw)
        session.pending_booking = None
        if result["ok"]:
            appt = result["appointment"]
            session.last_booking = appt
            if not result.get("already_booked"):
                await self.bus.publish("appointment.created", {"appointment": appt}, call_id=session.call_id)
                await self.bus.publish("availability.updated", {"doctor_id": appt["doctor_id"], "date": appt["appointment_date"]})
        return result

    # ------------------------------------------------------------ cancellation
    async def tool_cancel_appointment(self, session: CallSession, args: dict) -> dict:
        gate = self._phone_gate(session, _s(args, "patient_phone"))
        if gate:
            return gate
        kw = dict(patient_phone=session.verified_phone, appointment_id=_s(args, "appointment_id"),
                  cancel_all=_b(args, "cancel_all"), call_id=session.call_id)
        plan = await self._db(bk.cancel_appointment, self.clock, self.rules, dry_run=True, **kw)
        if plan["status"] != "WOULD_CANCEL":
            session.pending_cancel = None
            return plan
        ids = tuple(sorted(t["id"] for t in plan["targets"]))
        if not _b(args, "details_confirmed") or session.pending_cancel != ids:
            session.pending_cancel = ids
            return {"ok": False, "status": "NEEDS_CONFIRMATION", "appointments": plan["targets"],
                    "message": "Read the appointment(s) to the caller and ask 'Shall I cancel it?'. After a clear yes, call cancel_appointment again with the same appointment_id and details_confirmed=true."}
        if not is_affirmative(session.last_user_text):
            return _err("CONFIRMATION_NOT_HEARD", "The caller has not clearly said yes to cancelling. Ask them and wait. If they said no, leave it active.")
        result = await self._db(bk.cancel_appointment, self.clock, self.rules, fault=self._fault(), **kw)
        session.pending_cancel = None
        if result["ok"]:
            for a in result["cancelled"]:
                await self.bus.publish("appointment.cancelled", {"appointment": a}, call_id=session.call_id)
                await self.bus.publish("availability.updated", {"doctor_id": a["doctor_id"], "date": a["appointment_date"]})
        return result
