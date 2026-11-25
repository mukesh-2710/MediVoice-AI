import os
import shutil
import tempfile
from datetime import datetime, timezone

from app import database as db
from app import seed
from app.services.rules import Rules
from app.utils.clock import Clock

# Tuesday 24 Nov 2026, 10:00 IST (04:30 UTC)
FROZEN = datetime(2026, 11, 24, 4, 30, tzinfo=timezone.utc)
TODAY, TOMORROW = "2026-11-24", "2026-11-25"
MAINTENANCE_DAY = "2026-12-02"      # seeded holiday (today + 8)
SHARMA, MEHTA, NAIR = 1, 2, 3       # doctor ids from seed order
PHONE = "9876543210"


class DbCase:
    """Mixin: fresh seeded temp database per test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "t.db")
        self.clock = Clock(fixed_utc=FROZEN)
        self.rules = Rules()
        self.conn = db.connect(self.path)
        db.init_schema(self.conn)
        seed.seed(self.conn, self.clock)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def book(self, doctor=SHARMA, phone=PHONE, date=TOMORROW, time="11:00", **kw):
        from app.services import booking
        return booking.book_appointment(self.conn, self.clock, self.rules, doctor_id=doctor, patient_phone=phone,
                                        appointment_date=date, appointment_time=time, **kw)

    def cancel(self, phone=PHONE, **kw):
        from app.services import booking
        return booking.cancel_appointment(self.conn, self.clock, self.rules, patient_phone=phone, **kw)

    def slot_status(self, doctor=SHARMA, date=TOMORROW, time="11:00"):
        return self.conn.execute("SELECT status FROM appointment_slots WHERE doctor_id=? AND slot_date=? AND slot_time=?",
                                 (doctor, date, time)).fetchone()[0]
