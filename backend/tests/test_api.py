"""HTTP + WebSocket tests. Need `pip install -r requirements.txt`; skipped automatically otherwise.
(Written without the ability to execute them in the authoring sandbox - see TEST_REPORT.md.)"""
import os
import tempfile
import unittest
from dataclasses import replace

try:
    from fastapi.testclient import TestClient
    HAVE = True
except Exception:       # pragma: no cover
    HAVE = False


@unittest.skipUnless(HAVE, "fastapi not installed")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ["DATABASE_PATH"] = os.path.join(cls.tmp, "api.db")
        os.environ["GEMINI_API_KEY"] = "test-secret-gemini"
        os.environ["ELEVENLABS_API_KEY"] = "test-secret-eleven"
        from app.main import create_app
        cls.ctx = TestClient(create_app())
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["database"], "ok")

    def test_secrets_never_exposed(self):
        body = self.client.get("/api/config/status").text + self.client.get("/api/state").text
        self.assertNotIn("test-secret-gemini", body)
        self.assertNotIn("test-secret-eleven", body)

    def test_doctors_and_state(self):
        docs = self.client.get("/api/doctors").json()
        self.assertGreaterEqual(len(docs), 12)
        st = self.client.get("/api/state").json()
        self.assertIn("appointments", st)
        self.assertIn("stats", st)

    def test_unknown_doctor_404_and_validation(self):
        self.assertEqual(self.client.get("/api/doctors/9999").status_code, 404)
        self.assertEqual(self.client.get("/api/appointments?status=NOPE").status_code, 422)
        self.assertEqual(self.client.get("/api/availability?date=bad").status_code, 422)

    def test_sql_injection_in_filters_is_inert(self):
        r = self.client.get("/api/appointments", params={"q": "'; DROP TABLE appointments; --", "phone": "' OR 1=1 --"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/appointments").status_code, 200)

    def test_csv_export(self):
        r = self.client.get("/api/appointments/export.csv")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.text.startswith("reference,doctor"))

    def test_offer_without_keys_configured_is_clear(self):
        settings = self.client.app.state.settings
        self.client.app.state.settings = replace(settings, gemini_api_key="", elevenlabs_api_key="")
        r = self.client.post("/api/offer", json={"sdp": "x" * 20, "type": "offer"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("error", r.json())
        self.assertEqual(r.json()["error"]["code"], "voice_not_configured")

    def test_websocket_hello_and_event_delivery(self):
        with self.client.websocket_connect("/ws/events", headers={"origin": "http://localhost:5173"}) as ws:
            self.assertEqual(ws.receive_json()["type"], "hello")
            self.client.portal.call(self.client.app.state.bus.publish, "appointment.created", {"appointment": {"id": 1}})
            ev = ws.receive_json()
            self.assertEqual(ev["type"], "appointment.created")
            self.assertIn("id", ev)

    def test_websocket_rejects_foreign_origin(self):
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/events", headers={"origin": "http://evil.example"}) as ws:
                ws.receive_json()

    def test_websocket_refuses_unknown_call_subscription(self):
        with self.client.websocket_connect("/ws/events", headers={"origin": "http://localhost:5173"}) as ws:
            ws.receive_json()
            ws.send_json({"type": "subscribe", "call_id": "not-a-real-call"})
            self.assertEqual(ws.receive_json()["type"], "subscribe.rejected")


if __name__ == "__main__":
    unittest.main()
