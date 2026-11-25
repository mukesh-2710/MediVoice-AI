# Pipeline explanation (draft: rewrite in your own words for the form)

> The assignment asks for a short description *in your own words*. Treat this as notes and
> make sure you can explain every line before you submit.

**What I built.** A voice agent for a clinic. The browser sends microphone audio to a Python backend over WebRTC.
A Pipecat pipeline turns that audio into text with ElevenLabs STT, hands it to Gemini, and turns Gemini's answer
back into speech with ElevenLabs TTS, which streams back to the browser.

**Pipecat.** Pipecat is a framework where audio, text and events are "frames" flowing through a chain of processors:
transport in → STT → (my transcript tap) → user aggregator with Silero VAD → LLM → TTS → transport out. Because it
streams, the agent starts talking before the full answer exists, and when the caller interrupts, Pipecat cancels the speech.

**VAD.** Silero VAD decides when the caller starts and stops speaking, so I don't cut people off or react to background noise.

**Function calling.** Gemini is given three required tools: `check_doctor_availability`, `book_appointment`,
`cancel_appointment`, plus two small helpers to capture and confirm the phone number. When Gemini wants data it emits
a tool call; my handler runs it against SQLite and returns structured JSON; Gemini then speaks from that result.

**Why I don't trust the LLM.** A model can say "yes, confirmed" when the caller didn't. So the server checks the
caller's real transcript for a yes before it verifies a number or runs a booking/cancellation, and bookings are
database transactions. If the DB write fails, the agent is told it failed.

**Dashboard.** Every committed change is published over a WebSocket, and the React app also re-fetches a database
snapshot after any reconnect, so the screen always matches the database.

**What I'd improve.** Real identity verification (OTP), TURN server for strict networks, load testing, and per-clinic configuration.
