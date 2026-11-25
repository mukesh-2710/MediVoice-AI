# Architecture

```
 Browser (React)                              FastAPI process
┌──────────────────────┐   POST /api/offer   ┌────────────────────────────────────────────┐
│ Dashboard + Phone UI │ ──────────────────► │ routers/voice.py → SmallWebRTCConnection   │
│  mic ─WebRTC audio──►│ ◄─────────────────► │   voice/pipeline.py  (one task per call)   │
│  ◄─agent audio───────│                     │   mic → STT → tap → VAD → LLM → TTS → out  │
│                      │   WS /ws/events     │              │ function calls              │
│  store.js (reducer)  │ ◄────────────────── │   tools/handlers.py  (validation + gates)  │
│  callMachine.js      │   REST /api/*       │   services/ (availability, booking)        │
│                      │ ◄─────────────────► │   repositories/ → SQLite (WAL)             │
└──────────────────────┘                     └────────────────────────────────────────────┘
```

## Request/response paths
* **Audio** travels only over WebRTC (Opus). Plain JSON WebSockets are *not* used for audio.
* **Signalling**: the browser waits for ICE gathering, POSTs its SDP offer, receives an SDP answer plus a secret `call_id`.
* **Events** (`/ws/events`): `call.started/connected/ended`, `transcript.partial/final`, `agent.speaking`, `caller.speaking`,
  `tool.started/finished`, `appointment.created/cancelled`, `availability.updated`, `system.error`, `resync.required`.
* **State**: REST (`/api/state`) returns the full database-backed snapshot. The browser fetches it on first load and
  after every reconnect; events only *accelerate* updates, so a missed or duplicated event can never leave the UI wrong.

## Layers
| Layer | Responsibility | Notes |
|---|---|---|
| `routers/` | HTTP/WebSocket I/O, validation (Pydantic) | no business logic |
| `tools/` | The LLM-facing surface; treats all arguments as untrusted | confirmation gates, per-call session |
| `services/` | Business rules: availability, booking, cancellation | pure functions over a connection; fully unit-tested |
| `repositories/` | SQL | parameterised queries only |
| `voice/` | Pipecat wiring, taps, silence watchdog | pipecat imported lazily, so the API and tests run without it |
| `websocket/bus.py` | In-process pub/sub | unique event ids, call-scoped delivery, overflow → resync |

## Data model (SQLite)
`doctors` · `doctor_schedules` (weekday, hours, break) · `holidays` · `doctor_leave` · `appointment_slots`
(`UNIQUE(doctor_id, date, time)`, status AVAILABLE/BOOKED/BLOCKED) · `appointments` (BOOKED/CANCELLED/COMPLETED,
partial unique index: **one live appointment per slot**, many CANCELLED rows kept as history) · `call_sessions` ·
`call_transcripts` · `activity_logs`. Foreign keys on, indexes on the lookup paths. Timestamps are UTC; slot
date/time are clinic-local wall time (`CLINIC_TIMEZONE`).

## Booking transaction
`BEGIN IMMEDIATE` → re-read slot → reject if blocked/booked (idempotent if the same caller already holds it) →
reject same-number clash / same doctor-same-day duplicate → `UPDATE slot ... WHERE status='AVAILABLE'` (rowcount must be 1) →
insert appointment → write activity log → `COMMIT`. Any exception → `ROLLBACK`; nothing is announced. The partial unique index is a
second line of defence if application logic is ever bypassed. Cancellation is the mirror image and
frees the slot (or blocks it if the doctor is on leave).

## Safety design for a voice agent
1. Phone number: read back digit by digit → caller's *transcribed* yes (server-side regex) → `verified_phone`.
2. Sensitive actions: propose → caller's *transcribed* yes → execute. Changing details between steps forces a new proposal.
3. The model never supplies `call_session_id`, and one call can never read another call's state.
4. Tool results are the only source of slots, prices and IDs; the prompt forbids inventing them and the tools return structured statuses for every failure.
5. Spoken instructions are untrusted: no tool lets the model skip validation.

## Concurrency & failures
* Each DB operation uses its own connection (WAL, busy timeout). Writers queue on `BEGIN IMMEDIATE`; the concurrency tests fire 8 simultaneous bookings at one slot and exactly one wins.
* Per-call `asyncio.Lock` serialises tool calls, so a duplicated/delayed command is idempotent.
* Hang-up during a tool: the transaction is atomic; the result is logged as `tool.completed_after_hangup` and still published to the dashboard.
* TTS/LLM failure after a booking: the booking is already committed and shown on the dashboard; a `system.error` toast explains it.
* Silence: prompt after `SILENCE_PROMPT_SECS`, hang up shortly after.
