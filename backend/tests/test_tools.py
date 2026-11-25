"""Tool-layer tests: confirmation gating, untrusted arguments, events, hang-ups."""
import asyncio
import unittest

from app.tools.handlers import ToolRuntime
from app.voice.session import CallManager, CallSession
from app.websocket.bus import EventBus
from tests.helpers import MAINTENANCE_DAY, PHONE, SHARMA, TOMORROW, DbCase


class ToolCase(DbCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        DbCase.setUp(self)
        self.bus = EventBus()
        self.sub = self.bus.subscribe()
        self.fault = None
        self.rt = ToolRuntime(self.path, self.clock, self.rules, self.bus, fault_factory=lambda: self.fault)
        self.s = CallSession()
        from app.repositories import logs
        logs.create_call(self.conn, self.s.call_id, self.clock.utc_iso())

    async def asyncTearDown(self):
        pass

    def tearDown(self):
        DbCase.tearDown(self)

    async def say(self, text):
        self.s.last_user_text = text

    async def t(self, name, **args):
        return await self.rt.dispatch(name, self.s, args)

    async def verify_phone(self, number=PHONE):
        await self.say(number)
        r = await self.t("record_phone_number", spoken_phone=number)
        self.assertEqual(r["status"], "READ_BACK_REQUIRED", r)
        await self.say("yes that's right")
        r = await self.t("confirm_phone_number", is_correct=True)
        self.assertEqual(r["status"], "PHONE_CONFIRMED", r)

    def events(self):
        out = []
        while not self.sub.queue.empty():
            out.append(self.sub.queue.get_nowait())
        return out

    # ---------------------------------------------------------------- phone flow
    async def test_phone_readback_and_confirm(self):
        r = await self.t("record_phone_number", spoken_phone="98765 43210")
        self.assertEqual(r["read_back"], "9 8 7 6 5, 4 3 2 1 0")
        self.assertIsNone(self.s.verified_phone)
        await self.verify_phone()
        self.assertEqual(self.s.verified_phone, PHONE)

    async def test_invalid_numbers_are_rejected(self):
        for spoken, reason in [("12345", "TOO_SHORT"), ("98765432101", "TOO_LONG"), ("mumble", "UNCLEAR")]:
            r = await self.t("record_phone_number", spoken_phone=spoken)
            self.assertEqual((r["status"], r["reason"]), ("INVALID_PHONE", reason))
        self.assertIsNone(self.s.pending_phone)

    async def test_llm_cannot_self_confirm_phone(self):
        await self.say(PHONE)
        await self.t("record_phone_number", spoken_phone=PHONE)
        r = await self.t("confirm_phone_number", is_correct=True)       # caller has not answered yet
        self.assertEqual(r["status"], "CONFIRMATION_NOT_HEARD")
        self.assertIsNone(self.s.verified_phone)

    async def test_caller_says_no_to_readback(self):
        await self.t("record_phone_number", spoken_phone=PHONE)
        await self.say("no, that's wrong")
        r = await self.t("confirm_phone_number", is_correct=True)       # even if the LLM lies
        self.assertEqual(r["status"], "PHONE_REJECTED")
        self.assertIsNone(self.s.verified_phone)

    async def test_changing_number_resets_verification(self):
        await self.verify_phone()
        await self.t("record_phone_number", spoken_phone="9123456789")
        self.assertIsNone(self.s.verified_phone)
        self.assertEqual(self.s.pending_phone, "9123456789")

    # ---------------------------------------------------------------- availability
    async def test_availability_natural_dates(self):
        r = await self.t("check_doctor_availability", speciality="cardiologist", requested_date="tomorrow")
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["resolved_date"], TOMORROW)

    async def test_availability_bad_inputs(self):
        self.assertEqual((await self.t("check_doctor_availability", speciality="heart", requested_date="yesterday"))["status"], "PAST_DATE")
        self.assertEqual((await self.t("check_doctor_availability", speciality="heart", requested_date="03/04/2026"))["status"], "AMBIGUOUS_DATE")
        self.assertEqual((await self.t("check_doctor_availability", speciality="heart", requested_date="soonish"))["status"], "INVALID_DATE")
        self.assertEqual((await self.t("check_doctor_availability", doctor_id="abc"))["status"], "INVALID_ARGUMENTS")
        self.assertEqual((await self.t("check_doctor_availability", requested_date="tomorrow"))["status"], "NEED_DOCTOR_OR_SPECIALITY")

    async def test_availability_weekday_marked_assumed(self):
        r = await self.t("check_doctor_availability", doctor_id=SHARMA, requested_date="friday")
        self.assertTrue(r["date_was_assumed"])

    # ---------------------------------------------------------------- booking gates
    async def test_booking_requires_confirmed_phone(self):
        r = await self.t("book_appointment", doctor_id=SHARMA, patient_phone=PHONE, appointment_date=TOMORROW,
                         appointment_time="11:00", details_confirmed=True)
        self.assertEqual(r["status"], "PHONE_NOT_CONFIRMED")

    async def test_booking_rejects_a_different_phone(self):
        await self.verify_phone()
        r = await self.t("book_appointment", doctor_id=SHARMA, patient_phone="9123456789", appointment_date=TOMORROW,
                         appointment_time="11:00", details_confirmed=False)
        self.assertEqual(r["status"], "PHONE_MISMATCH")

    async def test_booking_missing_and_invalid_arguments(self):
        await self.verify_phone()
        r = await self.t("book_appointment", patient_phone=PHONE, details_confirmed=False)
        self.assertEqual(r["status"], "INVALID_ARGUMENTS")
        self.assertIn("doctor_id", r["message"])
        r = await self.rt.dispatch("book_appointment", self.s, "not-a-dict")
        self.assertEqual(r["status"], "INVALID_ARGUMENTS")
        self.assertEqual((await self.rt.dispatch("drop_tables", self.s, {}))["status"], "UNKNOWN_TOOL")
        r = await self.t("book_appointment", doctor_id="'; DROP TABLE appointments;--", patient_phone=PHONE,
                         appointment_date=TOMORROW, appointment_time="11:00", details_confirmed=False)
        self.assertEqual(r["status"], "INVALID_DOCTOR")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] > 0, True)

    async def book_flow(self, time="11:00"):
        args = dict(doctor_id=SHARMA, patient_phone=PHONE, appointment_date=TOMORROW, appointment_time=time)
        first = await self.t("book_appointment", details_confirmed=False, **args)
        self.assertEqual(first["status"], "NEEDS_CONFIRMATION", first)
        await self.say("yes please book it")
        return await self.t("book_appointment", details_confirmed=True, **args)

    async def test_full_booking_flow_emits_events(self):
        await self.verify_phone()
        r = await self.book_flow()
        self.assertEqual(r["status"], "BOOKED", r)
        types = [e["type"] for e in self.events()]
        self.assertIn("appointment.created", types)
        self.assertIn("availability.updated", types)
        self.assertEqual(self.slot_status(), "BOOKED")

    async def test_cannot_skip_the_proposal_step(self):
        await self.verify_phone()
        await self.say("yes")
        r = await self.t("book_appointment", doctor_id=SHARMA, patient_phone=PHONE, appointment_date=TOMORROW,
                         appointment_time="11:00", details_confirmed=True)
        self.assertEqual(r["status"], "NEEDS_CONFIRMATION")
        self.assertEqual(self.slot_status(), "AVAILABLE")

    async def test_no_booking_without_caller_yes(self):
        await self.verify_phone()
        args = dict(doctor_id=SHARMA, patient_phone=PHONE, appointment_date=TOMORROW, appointment_time="11:00")
        await self.t("book_appointment", details_confirmed=False, **args)
        await self.say("hmm, let me think")
        r = await self.t("book_appointment", details_confirmed=True, **args)
        self.assertEqual(r["status"], "CONFIRMATION_NOT_HEARD")
        await self.say("no, not that time")
        r = await self.t("book_appointment", details_confirmed=True, **args)
        self.assertEqual(r["status"], "CONFIRMATION_NOT_HEARD")
        self.assertEqual(self.slot_status(), "AVAILABLE")
        self.assertEqual([e for e in self.events() if e["type"] == "appointment.created"], [])

    async def test_changed_mind_midway_reproposes(self):
        await self.verify_phone()
        a = dict(doctor_id=SHARMA, patient_phone=PHONE, appointment_date=TOMORROW)
        await self.t("book_appointment", appointment_time="11:00", details_confirmed=False, **a)
        await self.t("book_appointment", appointment_time="15:00", details_confirmed=False, **a)   # changed mind
        await self.say("yes")
        r = await self.t("book_appointment", appointment_time="11:00", details_confirmed=True, **a)  # stale
        self.assertEqual(r["status"], "NEEDS_CONFIRMATION")
        self.assertEqual(self.slot_status(time="11:00"), "AVAILABLE")

    async def test_delayed_duplicate_command_is_idempotent(self):
        await self.verify_phone()
        first = await self.book_flow()
        self.events()
        again = await self.t("book_appointment", doctor_id=SHARMA, patient_phone=PHONE, appointment_date=TOMORROW,
                             appointment_time="11:00", details_confirmed=True)
        self.assertEqual(again["status"], "ALREADY_BOOKED")
        self.assertEqual(again["appointment"]["appointment_ref"], first["appointment"]["appointment_ref"])
        self.assertEqual(self.events(), [])        # no duplicate event emitted

    async def test_slot_taken_between_proposal_and_confirmation(self):
        await self.verify_phone()
        args = dict(doctor_id=SHARMA, patient_phone=PHONE, appointment_date=TOMORROW, appointment_time="11:00")
        await self.t("book_appointment", details_confirmed=False, **args)
        self.assertTrue(self.book(phone="9123456789")["ok"])          # another caller wins
        await self.say("yes")
        r = await self.t("book_appointment", details_confirmed=True, **args)
        self.assertEqual(r["status"], "SLOT_TAKEN")
        self.assertTrue(r["alternatives"]["same_day_times"])

    async def test_database_failure_is_never_reported_as_success(self):
        await self.verify_phone()

        def boom(stage):
            raise RuntimeError("db down")
        self.fault = boom
        r = await self.book_flow()
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "DB_ERROR")
        self.assertEqual([e for e in self.events() if e["type"].startswith("appointment")], [])
        self.assertEqual(self.slot_status(), "AVAILABLE")

    async def test_holiday_and_past_rejected_before_confirmation(self):
        await self.verify_phone()
        r = await self.t("book_appointment", doctor_id=SHARMA, patient_phone=PHONE, appointment_date=MAINTENANCE_DAY,
                         appointment_time="11:00", details_confirmed=False)
        self.assertEqual(r["status"], "HOLIDAY")
        r = await self.t("book_appointment", doctor_id=SHARMA, patient_phone=PHONE, appointment_date="2026-11-01",
                         appointment_time="11:00", details_confirmed=False)
        self.assertEqual(r["status"], "PAST_DATE")

    async def test_call_ended_during_tool_still_consistent(self):
        await self.verify_phone()
        args = dict(doctor_id=SHARMA, patient_phone=PHONE, appointment_date=TOMORROW, appointment_time="11:00")
        await self.t("book_appointment", details_confirmed=False, **args)
        await self.say("yes")
        task = asyncio.create_task(self.t("book_appointment", details_confirmed=True, **args))
        self.s.ended = True                       # hang-up while the tool is running
        r = await task
        self.assertEqual(r["status"], "BOOKED")   # transaction is atomic: either fully done or not at all
        n = self.conn.execute("SELECT COUNT(*) FROM activity_logs WHERE event_type='tool.completed_after_hangup'").fetchone()[0]
        self.assertEqual(n, 1)

    # ---------------------------------------------------------------- cancellation gates
    async def booked(self, time="11:00", doctor=SHARMA, date=TOMORROW):
        r = self.book(time=time, doctor=doctor, date=date)
        self.assertTrue(r["ok"], r)
        return r["appointment"]

    async def test_cancel_flow_requires_confirmation(self):
        await self.booked()
        await self.verify_phone()
        r = await self.t("cancel_appointment", patient_phone=PHONE, details_confirmed=False)
        self.assertEqual(r["status"], "NEEDS_CONFIRMATION")
        await self.say("yes cancel it")
        r = await self.t("cancel_appointment", patient_phone=PHONE, details_confirmed=True)
        self.assertEqual(r["status"], "CANCELLED")
        self.assertEqual(self.slot_status(), "AVAILABLE")
        types = [e["type"] for e in self.events()]
        self.assertIn("appointment.cancelled", types)

    async def test_caller_rejects_cancellation_keeps_appointment(self):
        a = await self.booked()
        await self.verify_phone()
        await self.t("cancel_appointment", patient_phone=PHONE, details_confirmed=False)
        await self.say("no, keep it")
        r = await self.t("cancel_appointment", patient_phone=PHONE, details_confirmed=True)
        self.assertEqual(r["status"], "CONFIRMATION_NOT_HEARD")
        self.assertEqual(self.conn.execute("SELECT status FROM appointments WHERE id=?", (a["id"],)).fetchone()[0], "BOOKED")

    async def test_cancel_unverified_phone_refused(self):
        await self.booked()
        r = await self.t("cancel_appointment", patient_phone=PHONE, details_confirmed=True)
        self.assertEqual(r["status"], "PHONE_NOT_CONFIRMED")

    async def test_cancel_multiple_requires_selection_then_confirmation(self):
        a = await self.booked()
        await self.booked(time="10:00", doctor=3, date="2026-11-26")
        await self.verify_phone()
        r = await self.t("cancel_appointment", patient_phone=PHONE, details_confirmed=False)
        self.assertEqual(r["status"], "NEEDS_SELECTION")
        r = await self.t("cancel_appointment", patient_phone=PHONE, appointment_id=a["appointment_ref"], details_confirmed=False)
        self.assertEqual(r["status"], "NEEDS_CONFIRMATION")
        await self.say("yes")
        r = await self.t("cancel_appointment", patient_phone=PHONE, appointment_id=a["appointment_ref"], details_confirmed=True)
        self.assertEqual(r["status"], "CANCELLED")
        self.assertEqual(len(r["cancelled"]), 1)

    async def test_cancel_confirmation_for_one_cannot_cancel_another(self):
        a = await self.booked()
        b = await self.booked(time="10:00", doctor=3, date="2026-11-26")
        await self.verify_phone()
        await self.t("cancel_appointment", patient_phone=PHONE, appointment_id=a["id"], details_confirmed=False)
        await self.say("yes")
        r = await self.t("cancel_appointment", patient_phone=PHONE, appointment_id=b["id"], details_confirmed=True)
        self.assertEqual(r["status"], "NEEDS_CONFIRMATION")      # different target -> must be proposed first
        self.assertEqual(self.conn.execute("SELECT status FROM appointments WHERE id=?", (b["id"],)).fetchone()[0], "BOOKED")

    async def test_cancel_all_after_confirmation(self):
        await self.booked()
        await self.booked(time="10:00", doctor=3, date="2026-11-26")
        await self.verify_phone()
        r = await self.t("cancel_appointment", patient_phone=PHONE, cancel_all=True, details_confirmed=False)
        self.assertEqual(r["status"], "NEEDS_CONFIRMATION")
        await self.say("yes")
        r = await self.t("cancel_appointment", patient_phone=PHONE, cancel_all=True, details_confirmed=True)
        self.assertEqual(len(r["cancelled"]), 2)

    async def test_find_my_appointments_scoped_to_verified_phone(self):
        await self.booked()
        self.book(phone="9123456789", doctor=3, time="10:00", date="2026-11-26")
        self.assertEqual((await self.t("find_my_appointments"))["status"], "PHONE_NOT_CONFIRMED")
        await self.verify_phone()
        r = await self.t("find_my_appointments")
        self.assertEqual(len(r["appointments"]), 1)
        self.assertTrue(all(a["patient_phone"] == PHONE for a in r["appointments"]))

    async def test_sessions_are_independent(self):
        other = CallSession()
        await self.verify_phone()
        r = await self.rt.dispatch("find_my_appointments", other, {})
        self.assertEqual(r["status"], "PHONE_NOT_CONFIRMED")      # verification never leaks across calls


class BusTests(unittest.IsolatedAsyncioTestCase):
    async def test_scoping_and_unique_ids(self):
        bus = EventBus()
        a, b = bus.subscribe("call-a"), bus.subscribe("call-b")
        await bus.publish("transcript.final", {"text": "hi"}, call_id="call-a", scope="call")
        e = await bus.publish("appointment.created", {}, call_id="call-a")
        self.assertEqual(a.queue.qsize(), 2)
        self.assertEqual(b.queue.qsize(), 1)                    # call-scoped transcript did not leak
        self.assertEqual(b.queue.get_nowait()["type"], "appointment.created")
        self.assertTrue(e["id"].startswith(bus.instance))
        self.assertGreater(e["seq"], 1)

    async def test_overflow_marks_resync(self):
        bus = EventBus()
        s = bus.subscribe()
        for _ in range(600):
            await bus.publish("x")
        self.assertTrue(s.overflowed)

    def test_call_manager(self):
        m = CallManager()
        s1, s2 = m.create(), m.create()
        self.assertNotEqual(s1.call_id, s2.call_id)
        self.assertEqual(m.active_count, 2)
        m.remove(s1.call_id)
        self.assertTrue(s1.ended)
        self.assertEqual(m.active_count, 1)


if __name__ == "__main__":
    unittest.main()
