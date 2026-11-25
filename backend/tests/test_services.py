import os
import sqlite3
import threading
import unittest

from app import database as db
from app.services import availability as av
from app.services import booking, dashboard
from tests.helpers import (MAINTENANCE_DAY, MEHTA, NAIR, PHONE, SHARMA, TODAY, TOMORROW, DbCase)


class AvailabilityTests(DbCase, unittest.TestCase):
    def check(self, **kw):
        return av.check_availability(self.conn, self.clock, self.rules, **kw)

    def test_seed_shape(self):
        self.assertGreaterEqual(len(db.connect(self.path).execute("SELECT * FROM doctors").fetchall()), 12)
        n = self.conn.execute("SELECT COUNT(DISTINCT speciality) FROM doctors").fetchone()[0]
        self.assertGreaterEqual(n, 8)

    def test_by_speciality_alias(self):
        r = self.check(speciality="heart", date_iso=TOMORROW)
        self.assertEqual(r["status"], "OK")
        self.assertEqual({d["speciality"] for d in r["doctors"]}, {"Cardiologist"})
        self.assertTrue(all(d["slots"] for d in r["doctors"]))

    def test_by_doctor_name_fuzzy(self):
        r = self.check(doctor_name="doctor sharma", date_iso=TOMORROW)
        self.assertEqual(r["doctors"][0]["doctor_id"], SHARMA)
        r = self.check(doctor_name="Sharmaa", date_iso=TOMORROW)
        self.assertEqual(r["doctors"][0]["doctor_id"], SHARMA)

    def test_unknown_doctor_and_speciality(self):
        self.assertEqual(self.check(doctor_name="Zebediah Quux", date_iso=TOMORROW)["status"], "DOCTOR_NOT_FOUND")
        r = self.check(speciality="astrology", date_iso=TOMORROW)
        self.assertEqual(r["status"], "SPECIALITY_NOT_FOUND")
        self.assertIn("Cardiologist", r["available_specialities"])

    def test_invalid_doctor_id(self):
        self.assertEqual(self.check(doctor_id=999, date_iso=TOMORROW)["status"], "INVALID_DOCTOR")

    def test_missing_target(self):
        self.assertEqual(self.check(date_iso=TOMORROW)["status"], "NEED_DOCTOR_OR_SPECIALITY")

    def test_past_and_far_future_dates(self):
        self.assertEqual(self.check(doctor_id=SHARMA, date_iso="2026-11-20")["status"], "PAST_DATE")
        self.assertEqual(self.check(doctor_id=SHARMA, date_iso="2027-06-01")["status"], "DATE_OUT_OF_RANGE")
        self.assertEqual(self.check(doctor_id=SHARMA, date_iso="nonsense")["status"], "INVALID_DATE")

    def test_holiday_explained(self):
        r = self.check(doctor_id=SHARMA, date_iso=MAINTENANCE_DAY)
        self.assertEqual(r["status"], "HOLIDAY")
        self.assertIn("closed", r["message"])

    def test_doctor_does_not_work_that_day(self):
        # Sharma is Mon-Fri; 2026-11-28 is Saturday
        r = self.check(doctor_id=SHARMA, date_iso="2026-11-28")
        self.assertEqual(r["status"], "NO_SLOTS")
        self.assertTrue(r["alternatives"][0]["next_dates"])

    def test_weekend_doctor_available_sunday(self):
        r = self.check(speciality="ENT", date_iso="2026-11-29")   # Sunday: only Dr. Prasad works
        self.assertEqual([d["name"] for d in r["doctors"]], ["Dr. Lakshmi Prasad"])

    def test_today_hides_past_and_too_soon_slots(self):
        r = self.check(doctor_id=SHARMA, date_iso=TODAY, max_slots=50)
        times = [s["time"] for s in r["doctors"][0]["slots"]]
        self.assertTrue(times and min(times) >= "10:30")      # now=10:00, lead=30m

    def test_break_time_excluded(self):
        r = self.check(doctor_id=SHARMA, date_iso=TOMORROW, max_slots=50)
        times = [s["time"] for s in r["doctors"][0]["slots"]]
        self.assertNotIn("13:00", times)
        self.assertNotIn("13:30", times)
        self.assertIn("14:00", times)

    def test_preferred_time_ranking(self):
        r = self.check(doctor_id=SHARMA, date_iso=TOMORROW, preferred_time="3 pm")
        self.assertEqual(r["doctors"][0]["slots"][0]["time"], "15:00")
        self.assertTrue(r["doctors"][0]["preferred_time_available"])

    def test_earliest(self):
        r = self.check(speciality="Cardiologist", earliest=True)
        self.assertEqual(len(r["doctors"]), 1)
        self.assertEqual(r["doctors"][0]["date"], TODAY)

    def test_fully_booked_day_suggests_alternatives(self):
        self.conn.execute("UPDATE appointment_slots SET status='BOOKED' WHERE doctor_id=? AND slot_date=?", (SHARMA, TOMORROW))
        r = self.check(doctor_id=SHARMA, date_iso=TOMORROW)
        self.assertEqual(r["status"], "NO_SLOTS")
        self.assertTrue(r["alternatives"][0]["next_dates"])


class BookingTests(DbCase, unittest.TestCase):
    def test_happy_path(self):
        r = self.book()
        self.assertTrue(r["ok"], r)
        a = r["appointment"]
        self.assertEqual(a["status"], "BOOKED")
        self.assertRegex(a["appointment_ref"], r"^MV-\d{6}$")
        self.assertEqual(self.slot_status(), "BOOKED")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM activity_logs WHERE event_type='appointment.created'").fetchone()[0], 1)

    def test_slot_disappears_from_availability(self):
        self.book()
        r = av.check_availability(self.conn, self.clock, self.rules, doctor_id=SHARMA, date_iso=TOMORROW, max_slots=50)
        self.assertNotIn("11:00", [s["time"] for s in r["doctors"][0]["slots"]])

    def test_double_booking_other_caller_rejected_with_alternatives(self):
        self.assertTrue(self.book()["ok"])
        r = self.book(phone="9123456789")
        self.assertEqual(r["status"], "SLOT_TAKEN")
        self.assertTrue(r["alternatives"]["same_day_times"])

    def test_idempotent_retry_same_caller(self):
        first = self.book()
        again = self.book()
        self.assertEqual(again["status"], "ALREADY_BOOKED")
        self.assertEqual(again["appointment"]["appointment_ref"], first["appointment"]["appointment_ref"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM appointments WHERE patient_phone=?", (PHONE,)).fetchone()[0], 1)

    def test_same_number_two_appointments_distinct_ids(self):
        a = self.book(time="11:00")["appointment"]
        b = self.book(doctor=NAIR, time="10:00", date="2026-11-26")["appointment"]
        self.assertNotEqual(a["appointment_ref"], b["appointment_ref"])
        self.assertNotEqual(a["id"], b["id"])

    def test_same_number_same_time_two_doctors_conflict(self):
        self.assertTrue(self.book(doctor=SHARMA, time="11:00")["ok"])
        self.assertEqual(self.book(doctor=MEHTA, time="11:00")["status"], "PHONE_CONFLICT")

    def test_same_doctor_same_day_duplicate(self):
        self.assertTrue(self.book(time="11:00")["ok"])
        self.assertEqual(self.book(time="15:00")["status"], "DUPLICATE_SAME_DAY")

    def test_validation_errors(self):
        self.assertEqual(self.book(phone="12345")["status"], "INVALID_PHONE")
        self.assertEqual(self.book(doctor=999)["status"], "INVALID_DOCTOR")
        self.assertEqual(self.book(doctor="abc")["status"], "INVALID_DOCTOR")
        self.assertEqual(self.book(date="2026-11-01")["status"], "PAST_DATE")
        self.assertEqual(self.book(date="garbage")["status"], "INVALID_DATE")
        self.assertEqual(self.book(time="banana")["status"], "INVALID_TIME")
        self.assertEqual(self.book(date=MAINTENANCE_DAY)["status"], "HOLIDAY")

    def test_outside_clinic_hours_and_break(self):
        self.assertEqual(self.book(time="07:00")["status"], "OUTSIDE_HOURS")
        self.assertEqual(self.book(time="20:00")["status"], "OUTSIDE_HOURS")
        self.assertEqual(self.book(time="13:00")["status"], "NO_SUCH_SLOT")     # lunch break
        self.assertEqual(self.book(date="2026-11-28")["status"], "OUTSIDE_HOURS")  # Saturday, doctor off

    def test_too_soon_and_past_time_today(self):
        self.assertEqual(self.book(date=TODAY, time="10:00")["status"], "PAST_TIME")
        self.assertEqual(self.book(date=TODAY, time="09:00")["status"], "PAST_TIME")

    def test_doctor_on_leave_after_slots_were_shown(self):
        shown = av.check_availability(self.conn, self.clock, self.rules, doctor_id=SHARMA, date_iso=TOMORROW)
        self.assertEqual(shown["status"], "OK")
        self.conn.execute("INSERT INTO doctor_leave (doctor_id, date, reason) VALUES (?,?,?)", (SHARMA, TOMORROW, "emergency"))
        r = self.book()
        self.assertEqual(r["status"], "DOCTOR_UNAVAILABLE")
        self.assertEqual(self.slot_status(), "AVAILABLE")      # nothing was written

    def test_blocked_slot_cannot_be_booked(self):
        self.conn.execute("UPDATE appointment_slots SET status='BLOCKED' WHERE doctor_id=? AND slot_date=? AND slot_time='11:00'", (SHARMA, TOMORROW))
        self.assertEqual(self.book()["status"], "DOCTOR_UNAVAILABLE")

    def test_dry_run_writes_nothing(self):
        r = self.book(dry_run=True)
        self.assertEqual(r["status"], "VALID")
        self.assertEqual(self.slot_status(), "AVAILABLE")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM appointments WHERE patient_phone=?", (PHONE,)).fetchone()[0], 0)

    def test_rollback_when_failure_after_slot_reserved(self):
        def boom(stage):
            if stage == "after_slot_reserved":
                raise RuntimeError("disk on fire")
        r = self.book(fault=boom)
        self.assertEqual(r["status"], "DB_ERROR")
        self.assertFalse(r["ok"])
        self.assertEqual(self.slot_status(), "AVAILABLE")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM appointments WHERE patient_phone=?", (PHONE,)).fetchone()[0], 0)
        self.assertTrue(self.book()["ok"])        # slot still usable afterwards

    def test_rollback_when_failure_after_insert(self):
        def boom(stage):
            if stage == "after_appointment_inserted":
                raise RuntimeError("boom")
        self.assertEqual(self.book(fault=boom)["status"], "DB_ERROR")
        self.assertEqual(self.slot_status(), "AVAILABLE")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM appointments WHERE patient_phone=?", (PHONE,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM activity_logs WHERE event_type='appointment.created'").fetchone()[0], 0)

    def test_database_uniqueness_constraints(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO appointment_slots (doctor_id, slot_date, slot_time) VALUES (?,?,?)", (SHARMA, TOMORROW, "11:00"))
        with self.assertRaises(sqlite3.IntegrityError):         # invalid foreign key
            self.conn.execute("INSERT INTO appointment_slots (doctor_id, slot_date, slot_time) VALUES (999,?,?)", (TOMORROW, "11:00"))

    def test_two_live_appointments_for_one_slot_impossible(self):
        self.book()
        slot = self.conn.execute("SELECT id FROM appointment_slots WHERE doctor_id=? AND slot_date=? AND slot_time='11:00'", (SHARMA, TOMORROW)).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO appointments (appointment_ref, slot_id, doctor_id, patient_phone, appointment_date, appointment_time, status, created_at)"
                " VALUES ('MV-1', ?, ?, '9000000000', ?, '11:00', 'BOOKED', 'x')", (slot, SHARMA, TOMORROW))

    def test_concurrent_booking_only_one_wins(self):
        results, barrier = [], threading.Barrier(8)

        def worker(i):
            conn = db.connect(self.path)
            try:
                barrier.wait()
                results.append(booking.book_appointment(conn, self.clock, self.rules, doctor_id=SHARMA,
                               patient_phone=f"98000000{i:02d}", appointment_date=TOMORROW, appointment_time="14:00"))
            finally:
                conn.close()
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(1 for r in results if r["status"] == "BOOKED"), 1, [r["status"] for r in results])
        self.assertEqual(sum(1 for r in results if r["status"] == "SLOT_TAKEN"), 7)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date=? AND appointment_time='14:00' AND doctor_id=? AND status='BOOKED'", (TOMORROW, SHARMA)).fetchone()[0], 1)

    def test_persistence_after_restart(self):
        ref = self.book()["appointment"]["appointment_ref"]
        self.conn.close()
        reopened = db.connect(self.path)
        row = reopened.execute("SELECT status FROM appointments WHERE appointment_ref=?", (ref,)).fetchone()
        self.assertEqual(row[0], "BOOKED")
        reopened.close()
        self.conn = db.connect(self.path)


class CancellationTests(DbCase, unittest.TestCase):
    def test_cancel_releases_slot_and_keeps_history(self):
        ref = self.book()["appointment"]["appointment_ref"]
        r = self.cancel()
        self.assertEqual(r["status"], "CANCELLED")
        self.assertEqual(self.slot_status(), "AVAILABLE")
        row = self.conn.execute("SELECT status, cancelled_at FROM appointments WHERE appointment_ref=?", (ref,)).fetchone()
        self.assertEqual(row[0], "CANCELLED")
        self.assertIsNotNone(row[1])          # record kept, not deleted

    def test_slot_can_be_rebooked_after_cancel(self):
        first = self.book()["appointment"]
        self.cancel()
        r = self.book(phone="9123456789")
        self.assertEqual(r["status"], "BOOKED")
        slot_id = self.conn.execute("SELECT slot_id FROM appointments WHERE id=?", (first["id"],)).fetchone()[0]
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM appointments WHERE slot_id=?", (slot_id,)).fetchone()[0], 2)  # history kept

    def test_no_matching_appointments(self):
        self.assertEqual(self.cancel(phone="9111111111")["status"], "NO_APPOINTMENTS")

    def test_multiple_requires_selection(self):
        self.book(time="11:00")
        self.book(doctor=NAIR, time="10:00", date="2026-11-26")
        r = self.cancel()
        self.assertEqual(r["status"], "NEEDS_SELECTION")
        self.assertEqual(len(r["appointments"]), 2)

    def test_cancel_selected_by_ref_and_id(self):
        a = self.book(time="11:00")["appointment"]
        b = self.book(doctor=NAIR, time="10:00", date="2026-11-26")["appointment"]
        self.assertEqual(self.cancel(appointment_id=a["appointment_ref"])["status"], "CANCELLED")
        self.assertEqual(self.cancel(appointment_id=b["id"])["status"], "CANCELLED")

    def test_cancel_all(self):
        self.book(time="11:00")
        self.book(doctor=NAIR, time="10:00", date="2026-11-26")
        r = self.cancel(cancel_all=True)
        self.assertEqual(len(r["cancelled"]), 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM appointments WHERE patient_phone=? AND status='BOOKED'", (PHONE,)).fetchone()[0], 0)

    def test_already_cancelled(self):
        a = self.book()["appointment"]
        self.cancel()
        self.assertEqual(self.cancel(appointment_id=a["id"])["status"], "ALREADY_CANCELLED")
        self.assertEqual(self.cancel()["status"], "NO_ACTIVE_APPOINTMENTS")

    def test_completed_cannot_be_cancelled(self):
        # seed: 9123456780 has COMPLETED visits in the past
        r = self.cancel(phone="9123456780")
        self.assertEqual(r["status"], "NO_ACTIVE_APPOINTMENTS")
        done = self.conn.execute("SELECT id FROM appointments WHERE patient_phone='9123456780' AND status='COMPLETED'").fetchone()[0]
        self.assertEqual(self.cancel(phone="9123456780", appointment_id=done)["status"], "CANNOT_CANCEL_COMPLETED")

    def test_cannot_cancel_someone_elses_booking_by_id(self):
        a = self.book()["appointment"]
        r = self.cancel(phone="9123456789", appointment_id=a["id"])
        self.assertIn(r["status"], {"NO_APPOINTMENTS", "APPOINTMENT_NOT_FOUND"})
        self.assertEqual(self.conn.execute("SELECT status FROM appointments WHERE id=?", (a["id"],)).fetchone()[0], "BOOKED")
        # even when the other number has its own booking, the foreign id is refused
        self.book(doctor=NAIR, phone="9123456789", time="10:00", date="2026-11-26")
        self.assertEqual(self.cancel(phone="9123456789", appointment_id=a["id"])["status"], "APPOINTMENT_NOT_FOUND")

    def test_invalid_appointment_id(self):
        self.book()
        self.assertEqual(self.cancel(appointment_id="MV-000000")["status"], "APPOINTMENT_NOT_FOUND")
        self.assertEqual(self.cancel(appointment_id="12345678")["status"], "APPOINTMENT_NOT_FOUND")

    def test_book_then_immediately_cancel(self):
        self.book()
        self.assertEqual(self.cancel()["status"], "CANCELLED")

    def test_rollback_on_failure(self):
        a = self.book()["appointment"]

        def boom(stage):
            raise RuntimeError("x")
        self.assertEqual(self.cancel(fault=boom)["status"], "DB_ERROR")
        self.assertEqual(self.conn.execute("SELECT status FROM appointments WHERE id=?", (a["id"],)).fetchone()[0], "BOOKED")
        self.assertEqual(self.slot_status(), "BOOKED")

    def test_concurrent_cancel_only_one_succeeds(self):
        self.book()
        results, barrier = [], threading.Barrier(5)

        def worker():
            conn = db.connect(self.path)
            try:
                barrier.wait()
                results.append(booking.cancel_appointment(conn, self.clock, self.rules, patient_phone=PHONE, appointment_id=None))
            finally:
                conn.close()
        ts = [threading.Thread(target=worker) for _ in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(1 for r in results if r["status"] == "CANCELLED"), 1, [r["status"] for r in results])

    def test_past_booked_becomes_completed(self):
        from datetime import datetime, timezone
        a = self.book()["appointment"]
        later = type(self.clock)(fixed_utc=datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc))   # 17:30 IST next day
        n = booking.complete_past(self.conn, later)
        self.assertGreaterEqual(n, 1)
        self.assertEqual(self.conn.execute("SELECT status FROM appointments WHERE id=?", (a["id"],)).fetchone()[0], "COMPLETED")


class DashboardStatsTests(DbCase, unittest.TestCase):
    def test_stats_reflect_database(self):
        before = dashboard.stats(self.conn, self.clock, active_calls=2)
        self.book()
        after = dashboard.stats(self.conn, self.clock, active_calls=2)
        self.assertEqual(after["total_appointments"], before["total_appointments"] + 1)
        self.assertEqual(after["confirmed_appointments"], before["confirmed_appointments"] + 1)
        self.assertEqual(after["available_slots"], before["available_slots"] - 1)
        self.assertEqual(after["active_calls"], 2)
        self.assertEqual(after["total_doctors"], 12)
        self.cancel()
        final = dashboard.stats(self.conn, self.clock)
        self.assertEqual(final["cancelled_appointments"], before["cancelled_appointments"] + 1)
        self.assertEqual(final["available_slots"], before["available_slots"])


if __name__ == "__main__":
    unittest.main()
