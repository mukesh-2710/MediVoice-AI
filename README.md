# MediVoice AI

MediVoice AI is a browser-based voice receptionist and clinic dashboard. Callers can ask about doctor availability, confirm a phone number, and book or cancel appointments by speaking. The dashboard reads from the same SQLite database and updates as call events arrive.

> **Demo data:** The included doctors, schedules, fees, holidays, and appointments are seeded sample clinic data. They are not connected to a real clinic scheduling system.

## Features

### Voice receptionist

- Browser microphone and speaker audio over WebRTC, using Pipecat's SmallWebRTC transport.
- ElevenLabs speech-to-text and text-to-speech, Google Gemini tool calling, and Silero voice activity detection.
- Live caller/agent transcript, caller and agent speaking indicators, mute and hang-up controls, and an audio activity waveform.
- Browser playback-block detection with an **Enable audio** retry prompt.
- Natural-language date, doctor, speciality, and time requests, including requests for the earliest available appointment.
- Server-side availability lookup. The assistant is instructed to use the live schedule data rather than invent or recall slots.
- Caller phone-number read-back and explicit spoken confirmation before the number is treated as verified.
- Two-step appointment booking and cancellation: the server proposes the action, checks the caller's spoken confirmation, then executes it.
- Silence prompt and hang-up handling, call lifecycle tracking, and call-scoped live transcript and speaking events.

### Clinic dashboard

The app shell provides eight pages:

| Page | Features |
|---|---|
| **Overview** | Appointment and call totals, free slots, next-seven-day visit chart, today's schedule, activity feed, status split, and speciality chart. |
| **Voice Assistant** | Start a call, check voice setup status, view the live transcript, and see suggested phrases. |
| **Doctors** | Search and filter doctors by name or speciality; inspect experience, fees, working days, hours, and upcoming booked/free slots. |
| **Availability** | Browse a 14-day date strip, filter by speciality, and compare available and booked slots; clinic holidays and empty schedules are shown. |
| **Appointments** | Search by phone, doctor, speciality, or reference; filter by status and date range; export matching statuses to CSV. |
| **Call History** | Review call status, duration, end reason, and transcript; download a transcript. |
| **Activity** | Browse recent booking, cancellation, and call events. |
| **Settings** | Check backend, database, WebSocket, Gemini, ElevenLabs, VAD, transport, clinic, and booking-horizon status without exposing API keys. |

### Data and reliability

- SQLite-backed doctors, schedules, appointments, call sessions, transcripts, and activity.
- Booking and cancellation run through server-side service logic and database transactions. A unique slot constraint protects against concurrent double-booking.
- Appointment and availability changes are published over WebSocket so connected dashboards update without a page refresh.
- Reconnect and resync support, duplicate-event protection, stale-data indication, loading states, and empty states.
- API errors use structured responses; health and configuration-status endpoints support troubleshooting.

## Technology

| Area | Technology |
|---|---|
| Frontend | React 18, Vite, hand-written CSS |
| Backend | Python, FastAPI, SQLite |
| Voice orchestration and transport | Pipecat, SmallWebRTC |
| Speech recognition and speech generation | ElevenLabs |
| Language model and function calling | Google Gemini (`gemini-3.8-flash` by default) |
| Voice activity detection | Silero |
| Realtime dashboard updates | WebSocket |

## Quick start

### Requirements

- Python 3.10 or later (Python 3.11 or 3.12 recommended)
- Node.js 18 or later and npm
- A Google Gemini API key and an ElevenLabs API key for live voice calls

Keep both API keys in `backend/.env` only. Never put them in frontend environment variables or commit them.

### Windows PowerShell

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
```

Edit `backend\.env` and set `GEMINI_API_KEY` and `ELEVENLABS_API_KEY`. Then start the backend:

```powershell
Set-Location backend
..\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

If the virtual environment is already activated from the project root, you can omit the activation command after changing into `backend`.

In a second terminal, from the project root:

```powershell
npm install --prefix frontend
npm run dev --prefix frontend -- --host 127.0.0.1
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173), allow microphone access, and select **Try Call**. The first voice run may download local VAD model files.

### macOS / Linux

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
```

Add the API keys to `backend/.env`, then run the backend from `backend/`:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal, from the project root:

```bash
npm install --prefix frontend
npm run dev --prefix frontend
```

Open [http://localhost:5173](http://localhost:5173). The backend creates and seeds its SQLite database on startup.

### Useful local URLs

- Dashboard: [http://localhost:5173](http://localhost:5173)
- API health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- API configuration status: [http://127.0.0.1:8000/api/config/status](http://127.0.0.1:8000/api/config/status)
- Interactive API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Configuration

Configure the backend in `backend/.env`; see [`backend/.env.example`](backend/.env.example) for the full list and defaults.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY`, `ELEVENLABS_API_KEY` | Server-only credentials required for voice calls. |
| `GEMINI_MODEL` | Gemini model name; defaults to `gemini-3.8-flash`. |
| `ELEVENLABS_VOICE_ID`, `ELEVENLABS_TTS_MODEL` | Voice and text-to-speech model selection. |
| `CLINIC_NAME`, `CLINIC_TIMEZONE` | Clinic label and timezone used to interpret schedule dates and times. |
| `PHONE_REGION` | Phone validation region; `IN` expects Indian 10-digit mobile numbers. |
| `BOOKING_HORIZON_DAYS`, `MIN_LEAD_MINUTES` | Maximum booking horizon and minimum advance notice. |
| `DATABASE_PATH` | SQLite database path; defaults to `data/medivoice.db` relative to the backend working directory. |
| `CORS_ORIGINS` | Allowed frontend origins; also checked for WebSocket connections. |
| `SILENCE_PROMPT_SECS`, `SILENCE_HANGUP_SECS` | Call silence prompt and timeout behaviour. |
| `LOG_LEVEL` | Backend log verbosity. |

In development, Vite proxies `/api` and `/ws` to `http://localhost:8000`. Set `VITE_BACKEND_URL` in the frontend environment if the backend is hosted elsewhere.

## How a voice call works

1. The browser requests microphone access, creates a WebRTC offer, and sends it to `POST /api/offer`.
2. The backend creates a per-call session and starts the Pipecat pipeline:
   `browser microphone → WebRTC input → ElevenLabs STT → transcript tap → Silero VAD/context → Gemini → ElevenLabs TTS → WebRTC output → browser speakers`.
3. Gemini may call server-registered tools for availability, phone-number read-back/confirmation, appointment lookup, booking, and cancellation. The backend—not the model—executes those tools against SQLite.
4. The backend publishes call-scoped transcript/speaking events and dashboard-wide appointment, availability, and call events over WebSocket.
5. If the browser blocks audio autoplay, the call UI offers an **Enable audio** action. If voice services fail, inspect the backend terminal for the provider error.

Additional design detail is in [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`PIPELINE_EXPLANATION.md`](PIPELINE_EXPLANATION.md).

## Confirmation and security boundaries

- A caller's spoken phone number is read back digit by digit. It is marked verified only after the next caller utterance clearly confirms it.
- Booking and cancellation require a proposal followed by a clear caller confirmation. The server checks the caller's transcript before executing the action.
- The server injects the call-session ID; it is not supplied by the LLM.
- A booking is reported successful only after the database transaction commits.
- API responses expose whether credentials are configured, never their values. WebSocket connections validate browser origins and keep transcripts/speaking events scoped to the live call.
- **Spoken-number verification is not identity authentication.** Anyone who knows a number may be able to access its appointment details. A production deployment needs OTP or another ownership check.

## API overview

The dashboard and voice client use these principal endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Backend, database, voice-readiness, and active-call status. |
| `GET /api/config/status` | Non-secret service configuration status. |
| `GET /api/state` | Initial dashboard snapshot and reconnect resync. |
| `GET /api/doctors`, `GET /api/doctors/{doctor_id}` | Doctor directory and details. |
| `GET /api/availability?date=YYYY-MM-DD` | Schedule and free/booked slots; optionally filter by doctor or speciality. |
| `GET /api/appointments` | Appointment search and filters. |
| `GET /api/appointments/export.csv` | CSV export. |
| `GET /api/stats`, `GET /api/activity` | Dashboard metrics and activity feed. |
| `GET /api/calls`, `GET /api/calls/{call_id}/transcript` | Call history and transcript. |
| `POST /api/offer` | WebRTC signalling and voice-session startup. |
| `POST /api/calls/{call_id}/end` | End a live call. |
| `WS /ws/events` | Realtime dashboard and call events. |

## Tests and verification

Run the backend tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

Run frontend tests and the production build:

```powershell
npm test --prefix frontend
npm run build --prefix frontend
```

The automated suites cover backend API, services, tool confirmation, date/phone parsing, booking concurrency and rollback, and frontend state/format/call logic. Browser playback, provider credentials and quota, network/WebRTC quality, and a complete live Gemini/ElevenLabs conversation still require a real manual call. See [`TEST_REPORT.md`](TEST_REPORT.md) for the latest recorded test results and limitations, and [`docs/LIVE_TEST_CHECKLIST.md`](docs/LIVE_TEST_CHECKLIST.md) for a manual test sequence.

## Troubleshooting

| Symptom | Check |
|---|---|
| Voice setup reports missing keys / `/api/offer` returns 503 | Set both backend keys in `backend/.env`, then restart Uvicorn. |
| Port 8000 is occupied or health checks time out | Stop the existing backend process from its terminal with Ctrl+C, then restart Uvicorn from `backend/`. |
| Microphone permission is unavailable | Use `localhost` or HTTPS and allow microphone access in browser site settings. |
| Transcript appears but there is no agent audio | Check the tab/output device and backend ElevenLabs logs. If the UI shows **Enable audio**, click it to retry browser playback. |
| Agent repeats itself or does not provide appointment slots | Check backend logs for Gemini errors and `tool=check_doctor_availability`; confirm the requested speciality/date exists in the sample clinic schedule. |
| Call connects but the agent is silent | Check the Uvicorn terminal for Gemini, ElevenLabs, Pipecat, or `pipeline error` messages; verify model availability, credentials, and provider account limits. |
| Dashboard says the connection is lost | Confirm Uvicorn is running and `CORS_ORIGINS` includes the dashboard origin. |
| Call cannot connect on a restrictive network | WebRTC currently uses STUN; some networks require TURN. |

## Known limitations

- The included clinic schedule and patient records are demonstration data, not a production clinic integration.
- The dashboard has no login or role-based access control; do not expose it publicly as-is.
- Caller identity is based on spoken phone number only and is not secure proof of ownership.
- Phone validation is region-specific, and fuzzy doctor-name matching is English-centric.
- WebRTC uses STUN only; restrictive NAT/firewall environments may require TURN.
- Headphones are recommended to reduce the microphone picking up the agent's speaker audio.
- The live voice experience depends on third-party API access, available models, credentials, quota, and network quality.

## Project layout

```text
backend/
  app/
    routers/       REST API and WebRTC call routes
    websocket/     event bus and dashboard socket
    services/      availability, booking, cancellation, dashboard metrics
    repositories/  SQLite queries for doctors, slots, appointments, calls, and logs
    tools/         Gemini tool schemas and server-side handlers
    voice/         Pipecat pipeline, prompts, compatibility helpers, transcript taps
    utils/         phone, date, confirmation, and clock helpers
  tests/           backend tests
frontend/
  src/
    pages/         the eight dashboard pages
    components/    app shell, charts, phone modal, waveform, and shared UI
    context/       application and call state
    lib/           API, WebSocket, WebRTC, reducers, formatters, and tests
docs/
  LIVE_TEST_CHECKLIST.md
  screenshots/
```
