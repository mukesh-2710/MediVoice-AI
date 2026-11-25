# MediVoice AI: voice doctor-appointment assistant

A caller speaks to an AI receptionist in the browser. It checks a doctor's availability, books and cancels
appointments, and every action shows up live on a dashboard. Built for the *SDE Intern Round 1* assignment.

| Part | Technology |
|---|---|
| Voice pipeline | **Pipecat** (Python), SmallWebRTC audio transport |
| Speech-to-text / text-to-speech | **ElevenLabs** |
| LLM | **Google Gemini** (`gemini-3.8-flash` by default) with function calling |
| VAD | Silero (bonus) |
| Backend / API | FastAPI, SQLite, WebSocket events |
| Frontend | React + Vite, hand-written CSS (no UI kit) |

> **Which LLM?** Google Gemini. Set `GEMINI_MODEL` in `backend/.env` to change the model.

> **Honesty note.** This code was written in a sandbox with **no internet access**, so the live voice path
> (Pipecat + ElevenLabs + Gemini + WebRTC) has **not been executed**. Everything else was tested; see
> [TEST_REPORT.md](TEST_REPORT.md) for exactly what was and was not verified. Run
> [docs/LIVE_TEST_CHECKLIST.md](docs/LIVE_TEST_CHECKLIST.md) before you record your video.

## Quick start

Prerequisites: Python 3.10+ (3.11/3.12 recommended), Node 18+, a Gemini API key
([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) and an ElevenLabs API key
([elevenlabs.io](https://elevenlabs.io), the free tier includes STT and TTS credits).

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then put your two keys in .env
uvicorn app.main:app --port 8000                       # DB is created and seeded automatically

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

Open http://localhost:5173, click **Try Call**, allow the microphone, and talk.
API docs (Swagger): http://localhost:8000/docs · Health: http://localhost:8000/api/health

First run downloads the Silero VAD model through Pipecat, so allow a minute.

### Pinning
`requirements.txt` uses ranges because Pipecat evolves quickly. After your first successful install run
`pip freeze > requirements.lock` and commit it; `npm install` creates `package-lock.json`. Commit both.

## Environment variables
`backend/.env` (see `backend/.env.example`)

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `ELEVENLABS_API_KEY` | **Secrets. Backend only.** The browser never sees them. |
| `GEMINI_MODEL` | default `gemini-3.8-flash` |
| `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_MODEL` | voice and TTS model |
| `CLINIC_NAME`, `CLINIC_TIMEZONE` | clinic identity; slots are clinic-local wall time (default `Asia/Kolkata`) |
| `PHONE_REGION` | `IN` = 10-digit mobile numbers starting 6-9 |
| `BOOKING_HORIZON_DAYS`, `MIN_LEAD_MINUTES` | how far ahead callers can book; minimum notice |
| `DATABASE_PATH` | SQLite file (default `data/medivoice.db`) |
| `CORS_ORIGINS` | allowed browser origins (also checked on the WebSocket) |
| `SILENCE_PROMPT_SECS`, `SILENCE_HANGUP_SECS` | silence handling |

`frontend/.env.example` is optional: in development Vite proxies `/api` and `/ws` to the backend.

## How it works (short)
1. The browser captures the mic and opens a WebRTC connection to the backend (`POST /api/offer`).
2. Pipecat pipeline: `mic → ElevenLabs STT → transcript tap → Silero VAD/aggregator → Gemini → ElevenLabs TTS → speaker`.
3. Gemini calls tools (`check_doctor_availability`, `book_appointment`, `cancel_appointment` plus small helpers).
   Tools run on the server against SQLite.
4. Every change is committed in a database transaction, then published over WebSocket; the dashboard updates live.

Details: [ARCHITECTURE.md](ARCHITECTURE.md), [PIPELINE_EXPLANATION.md](PIPELINE_EXPLANATION.md).

### The rules the *server* enforces (not just the prompt)
* The caller is identified **only** by the phone number they say. `record_phone_number` returns a digit-by-digit
  read-back; the number becomes *verified* only if the caller's next transcribed utterance is an affirmative yes.
* `book_appointment` / `cancel_appointment` are two-phase: *propose → caller says yes → execute*. The server checks the
  caller's actual transcript for the yes; the LLM cannot self-confirm. A confirmation for one appointment cannot cancel another.
* A booking is "successful" only when a committed database row exists. DB errors return `DB_ERROR` and nothing is announced as booked.
* `call_session_id` is injected server-side, never chosen by the model.

## Example conversation
> **Agent:** Hello, you've reached Northwell Clinic. How can I help?
> **Caller:** I'd like to see a cardiologist tomorrow.
> **Agent:** Of course. May I have your phone number?
> **Caller:** nine eight seven six five four three two one zero
> **Agent:** I heard 9 8 7 6 5, 4 3 2 1 0. Is that correct? **Caller:** Yes.
> **Agent:** Dr. Anika Sharma has 9, 9:30 and 10 AM tomorrow. Dr. Rohan Mehta has 10 and 10:30. Which suits you?
> **Caller:** Dr. Sharma at ten. **Agent:** Dr. Sharma, tomorrow at 10 AM, fee 1200 rupees, number 9 8 7 6 5, 4 3 2 1 0. Shall I book it?
> **Caller:** Yes. **Agent:** Booked. Your reference is M V 4 8 2 9 1 5.

## Project layout
```
backend/app/
  main.py  config.py  database.py  seed.py
  routers/       api.py (REST) · voice.py (WebRTC offer / hang-up)
  websocket/     router.py (dashboard socket) · bus.py (event bus)
  services/      availability.py · booking.py (book/cancel, transactions) · dashboard.py
  repositories/  doctors · slots · appointments · logs (calls, transcripts, activity)
  tools/         definitions.py (LLM schemas) · handlers.py (server-side gating)
  voice/         pipeline.py · taps.py · compat.py · prompts.py · session.py
  utils/         phone.py · dates.py · confirm.py · clock.py
  schemas/ middleware/
backend/tests/   107 tests (see TEST_REPORT.md)
frontend/src/
  lib/           store · callMachine · voiceCall (WebRTC) · events (WS) · api · sounds   (all unit-tested logic)
  components/    PhoneModal · Radial (waveform) · Charts · Sidebar · ui
  pages/         Overview · VoiceAssistant · Doctors · Availability · Appointments · CallHistory · Activity · Settings
```

## Tests
```bash
cd backend && python -m pytest          # or: python -m unittest discover -s tests -t .
cd frontend && npm test                 # node's built-in test runner, no extra deps
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| "Voice is not configured" in the UI / 503 on `/api/offer` | Add both keys to `backend/.env`, restart uvicorn |
| `ImportError` from `pipecat...` at call start | Pipecat moved a module: `pip install -U "pipecat-ai[elevenlabs,google,silero,webrtc]"`, then see `backend/app/voice/compat.py` (version shims live there) |
| Mic prompt never appears | Use `http://localhost` or HTTPS; check browser site permissions |
| Connected but no audio from the agent | Click once on the page (autoplay policy), check output device, check backend logs for ElevenLabs errors |
| Call connects then ends in silence | Check Gemini quota / key; the logs show `pipeline error` lines |
| Dashboard says "Connection lost" | Backend is down or CORS_ORIGINS does not include your frontend origin |
| Corporate/VPN network blocks audio | WebRTC needs UDP; try another network or add a TURN server (`STUN` in `routers/voice.py`) |

## Known limitations
* **Identity is weak by design.** Anyone who knows a phone number can ask about its appointments. The assignment
  specifies spoken-number-only identification; a real deployment needs OTP or caller-ID verification. This does not prove ownership of the number.
* Dashboard has no login (single-clinic demo); don't expose it publicly as-is.
* Phone parsing targets Indian 10-digit mobile numbers (`PHONE_REGION`).
* Spoken-name matching is fuzzy but English-centric.
* STUN only; strict NATs may need TURN.
* Full-duplex echo: use headphones for the best demo, since laptop speakers can feed the agent's voice back into the mic.
#   M e d i V o i c e - A I  
 