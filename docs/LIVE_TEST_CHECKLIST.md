# Live-service checklist (do this before recording the video)

Automated tests use no external AI services. These steps are the **only** way to verify the real pipeline.
Tick each box; fix anything red before submitting.

## Setup
- [ ] `backend/.env` has `GEMINI_API_KEY` and `ELEVENLABS_API_KEY`
- [ ] `pip install -r requirements.txt` finished without errors; `python -c "import pipecat; print(pipecat.__version__)"` works
- [ ] `uvicorn app.main:app --port 8000` starts; backend log shows `voice_ready=True`
- [ ] http://localhost:8000/docs loads; `/api/health` → `{"status":"ok"}`
- [ ] `npm install && npm run dev`; dashboard shows data and the **Live** pill is green
- [ ] Settings page shows Gemini and ElevenLabs as *Configured*

## Voice (use headphones)
- [ ] **Try Call** → ringing → connecting → connected; timer runs; browser mic indicator is on
- [ ] Agent greets you out loud; greeting appears in the transcript
- [ ] Waveform moves with *your* voice (inner ring) and the *agent's* voice (outer ring)
- [ ] Interrupt the agent mid-sentence: it stops and listens
- [ ] Stay silent ~12 s: it asks "Are you still there?"; stay silent more: it hangs up
- [ ] Mute button silences your mic (indicator changes); end-call closes the phone and mic

## Booking
- [ ] "Book a cardiologist tomorrow" → it asks for your number
- [ ] Say a 10-digit number → it reads it back digit by digit
- [ ] Answer "no, it's …" with a corrected number → it reads the new number back
- [ ] Say "yes" → availability offered matches **Availability** page for that date
- [ ] Pick a slot → it summarises doctor/day/time/fee/number and asks to confirm
- [ ] Say "yes" → it speaks a reference like MV-123456; **Appointments** page shows the row (green flash); confirmation card appears in the phone
- [ ] Overview counters changed; slot is struck-through on **Availability**

## Cancellation
- [ ] "Cancel my appointment" → (number already confirmed) it reads the appointment back
- [ ] Say "no" → appointment stays Confirmed
- [ ] Repeat, say "yes" → status becomes Cancelled (coral flash), slot is free again, cancellation card shown
- [ ] With two appointments on one number it asks which one

## Edge probes
- [ ] Number with 9 digits → rejected, asks again
- [ ] "Book for yesterday" → asks for a future date
- [ ] Ask for the day seeded as a clinic holiday (see **Availability**: "Clinic maintenance day") → explains it is closed
- [ ] "Dr. Nobody" → suggests real doctors
- [ ] Try to book an already-booked slot from a 2nd browser tab → refused, alternatives offered
- [ ] Stop the backend mid-call → UI shows error/retry; restart → data persists after refresh

## Record the video (≤ 3 min)
1. Dashboard (10 s) → 2. Try Call, say number, confirm (30 s) → 3. Ask cardiologist availability (30 s) →
4. Book; show the row appear on Appointments (40 s) → 5. Cancel (30 s) → 6. Show tests passing / architecture (20 s).
