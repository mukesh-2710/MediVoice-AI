# Test report

Authoring environment: Python 3.12, Node 22, headless Chromium (Playwright). **No internet access**, so no
third-party package could be installed and **no live API (Gemini / ElevenLabs) was called.**

## Summary

| Suite | Result | How it ran |
|---|---|---|
| Backend unit + integration (phone, dates, confirmation, availability, booking, cancellation, concurrency, rollback, persistence, tool gating, event bus) | **97 passed** | `python -m unittest discover -s tests -t .`, real SQLite files, real threads |
| Backend API + WebSocket tests (`tests/test_api.py`) | **10 written, SKIPPED here** (need FastAPI) | will run automatically after `pip install -r requirements.txt` |
| Frontend logic (store reducer, call state machine, formatters) | **30 passed** | `npm test` (node:test) |
| Frontend bundle | **builds** (esbuild, 0 errors/warnings) | proves syntax and imports resolve |
| Browser run (Chromium) against a stub server that serves **real data from this repo's service layer** | **14/14 checks passed** | see below |
| Mutation check | **tests fail when safety is removed** | removed the "caller said yes" gate → 3 tests failed; removed the unique-slot index → 1 test failed; restored |

Mocked vs live: the 97 backend tests exercise real business logic and a real database; they do **not** involve
STT/LLM/TTS at all. Tool calls are made directly (as Gemini would), with the caller's utterance set explicitly.
Nothing here proves that Gemini will *choose* the right tool in the right order; only the live checklist can.

## Browser checks that passed (Chromium, stub server + real booking/cancel service code)
1. Overview renders, WebSocket goes Live. 2. A booking made through `booking.book_appointment` appears in the
Appointments table with no reload. 3. New row flashes green. 4. Overview total refreshes from DB-backed stats.
5. A re-delivered event id does not duplicate the row. 6. Cancellation flips the row to *Cancelled* and flashes coral.
7. Dropping the socket shows the stale-data banner; 8. it reconnects, resyncs and the banner clears.
9. All eight pages render. 10. Try Call opens the phone in *Ringing*. 11. A server error ("keys missing") is shown in the phone with retry.
12. Mobile layout (390 px) has no horizontal overflow. Screenshots: `docs/screenshots/`.

## Edge-case coverage matrix
✅ automated test · 🔶 implemented, only verifiable live · ❌ not done

| Area | Case | Status |
|---|---|---|
| Phone | invalid / too short / too long / spoken in groups / words / double-triple / +91 / unclear / empty | ✅ |
| Phone | caller changes number → verification reset and read-back again | ✅ |
| Confirmation | caller says no (even if LLM claims yes); LLM cannot self-confirm; stale proposal needs re-confirm | ✅ |
| Confirmation | caller corrects one digit | ✅ (re-record) · 🔶 (speech) |
| Voice | VAD, interruption, silence prompt/hangup, STT/TTS/LLM failure paths, mic denied message | 🔶 (code present, never run) |
| Voice | call ends mid-tool: transaction atomic, logged, dashboard still synced | ✅ |
| Intent | multiple intents, corrections, unclear request, unrecognised doctor/speciality | ✅ tool side (suggestions returned) · 🔶 LLM behaviour |
| Dates | today/tomorrow, past, ambiguous numeric, weekday (flagged "assumed"), named month, invalid, out of range | ✅ |
| Dates | Sunday/holiday/doctor-off explanations; outside hours; lunch break; too-soon today | ✅ |
| Slots | no slots → alternatives; slot taken between proposal and confirm; doctor goes on leave after slots shown; blocked slot | ✅ |
| Slots | concurrent booking (8 threads → exactly 1) | ✅ |
| Booking | missing info, invalid doctor id (incl. SQL-injection string), duplicate/delayed repeat (idempotent), same number multiple appointments (distinct IDs), same number same time, same doctor same day | ✅ |
| Booking | DB failure/rollback at two points inside the transaction; never announced as success | ✅ |
| Booking | earliest available, no doctor specified, day without time | ✅ tool side |
| Cancellation | no match, multiple → select, cancel-all, already cancelled, completed, wrong-number id, invalid id, caller rejects, book-then-cancel, rollback, concurrent cancel (5 threads → 1) | ✅ |
| Dashboard | duplicate events, reconnect + resync, stale banner, refresh restores from DB, empty states, loading skeletons, mobile | ✅ (browser run) |
| Database | unique slot, foreign key, one live appointment per slot, persistence after reopen | ✅ |
| Security | keys never in API responses | ✅ written (`test_api.py`, skipped here) |
| Security | WebSocket origin check, call-scoped events don't leak, unknown call subscription rejected | ✅ bus scoping · written (`test_api.py`) for socket |
| Security | untrusted LLM args: unknown tool, non-dict args, wrong types | ✅ |
| Dashboard | same browser opens two calls | ✅ blocked client-side by state machine; server also supports independent sessions |
| Frontend | React component rendering tests (RTL/jsdom) | ❌ not written; covered by the manual browser run instead |
| Ops | Docker | ❌ skipped (optional) |

## NOT verified (read this)
* Pipecat imports, class names and constructor arguments (`ElevenLabsRealtimeSTTService`, `GoogleLLMService`,
  `SmallWebRTCConnection`, `LLMContextAggregatorPair`, observers). I wrote against my knowledge of the
  0.0.8x–0.0.9x API and isolated version differences in `voice/compat.py`, but **could not import the package**.
  Expect to fix a name or an argument on first run.
* ElevenLabs / Gemini authentication, model names, voice id, rate limits.
* The WebRTC handshake with `SmallWebRTCTransport`, audio quality, echo.
* `npm install`, `vite build`, and the app under Vite. (The bundle was built with esbuild; `package-lock.json` does not exist yet.)
* `tests/test_api.py` has never been executed.
* The connected-call screen was verified only by rendering the real component with a *scripted* call state (`docs/screenshots/phone-connected-scripted.png`); the waveform was driven by simulated data there, in production it reads the real streams.
