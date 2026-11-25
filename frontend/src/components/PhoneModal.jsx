import React, { useEffect, useRef, useState } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { formatDay, formatDuration, to12h } from '../lib/format.js'
import { isCallActive } from '../lib/callMachine.js'
import Icon, { Logo } from './Icon.jsx'
import Radial from './Radial.jsx'

const TOOL_TEXT = {
  check_doctor_availability: 'Checking availability…',
  record_phone_number: 'Noting your number…',
  confirm_phone_number: 'Verifying number…',
  find_my_appointments: 'Looking up appointments…',
  book_appointment: 'Booking…',
  cancel_appointment: 'Cancelling…',
}

function useElapsed(since, running) {
  const [s, setS] = useState(0)
  useEffect(() => {
    if (!running || !since) return
    const tick = () => setS((Date.now() - since) / 1000)
    tick()
    const t = setInterval(tick, 500)
    return () => clearInterval(t)
  }, [since, running])
  return s
}

function Confirmation({ card }) {
  const a = card.appointment
  const cancelled = card.kind === 'cancelled'
  return (
    <div className={`confirm ${cancelled ? 'cancelled' : ''}`} role="status">
      <div className="ico"><Icon name={cancelled ? 'x' : 'check'} size={18} stroke={2.6} /></div>
      <b>{cancelled ? 'Appointment cancelled' : 'Appointment confirmed'}</b>
      <span>{a.doctor_name} · {a.speciality}</span>
      <span>{formatDay(a.appointment_date)}, {to12h(a.appointment_time)} · <span className="ref">{a.appointment_ref}</span></span>
    </div>
  )
}

export default function PhoneModal() {
  const { call, voice, endCall, startCall, toggleMute, dismissCall, playbackBlocked, enableAudio } = useApp()
  const txRef = useRef(null)
  const active = isCallActive(call.phase)
  const elapsed = useElapsed(call.connectedAt, call.phase === 'connected')

  useEffect(() => {
    txRef.current?.scrollTo({ top: txRef.current.scrollHeight, behavior: 'smooth' })
  }, [call.transcript, call.cards.length])

  // Escape closes a finished call screen; during a call it must be explicit (end-call button)
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && !active && dismissCall()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [active, dismissCall])

  if (call.phase === 'idle') return null

  const { phase } = call
  let status = ''
  let cls = ''
  if (phase === 'ringing') status = 'Ringing…'
  else if (phase === 'connecting') status = 'Connecting…'
  else if (phase === 'connected') { status = call.tool ? TOOL_TEXT[call.tool] || 'Working…' : formatDuration(elapsed); cls = call.tool ? '' : 'ok' }
  else if (phase === 'ending') status = 'Ending…'
  else if (phase === 'ended') status = 'Call ended'
  else if (phase === 'error') { status = 'Call failed'; cls = 'bad' }

  const cue = phase !== 'connected' ? '' : call.agentSpeaking ? 'Agent speaking' : call.callerSpeaking ? 'You’re speaking' : call.muted ? 'Microphone muted' : 'Listening'
  const cueCls = call.agentSpeaking ? 'agent' : call.callerSpeaking ? 'you' : ''

  return (
    <div className="phone-layer" role="dialog" aria-modal="true" aria-label="Voice call with the clinic assistant">
      <div className="phone">
        <div className="who">
          <h2>Northwell Reception</h2>
          <div className={`status ${cls}`} aria-live="polite">{status}</div>
        </div>

        <div className="stage">
          {(phase === 'ringing' || phase === 'connecting') && (<><i className="ripple" /><i className="ripple" /><i className="ripple" /></>)}
          {phase === 'connected' && <Radial voiceRef={voice} active />}
          <div className={`face ${call.agentSpeaking ? 'talk' : ''}`}><Logo size={44} /></div>
        </div>
        <div className={`cue ${cueCls}`} aria-live="polite">{cue}</div>

        {phase === 'error' && (
          <div className="errbox" role="alert">
            <b>{call.error}</b>
          </div>
        )}
        {phase === 'ended' && (
          <div className="summary"><span className="num">{formatDuration(call.endedAfter)}</span>Call length</div>
        )}

        <div className="tx" ref={txRef}>
          {call.transcript.length === 0 && phase !== 'error' && (
            <div className="tx-empty">{phase === 'connected' ? 'Say hello. Your conversation appears here.' : phase === 'ended' ? 'No conversation was captured.' : ''}</div>
          )}
          {call.transcript.map((m) => (
            <div key={m.key} className={`msg ${m.role} ${m.final ? '' : 'partial'}`}>{m.text}</div>
          ))}
        </div>

        {call.cards.slice(-1).map((c) => <Confirmation key={`${c.kind}-${c.id}`} card={c} />)}

        {playbackBlocked && phase !== 'idle' && (
          <div className="audio-warning" role="status">
            <span>Speaker playback was blocked by the browser.</span>
            <button type="button" onClick={enableAudio}>Enable audio</button>
          </div>
        )}

        <div className="controls">
          {active ? (
            <>
              <button className="rbtn" aria-pressed={call.muted} onClick={toggleMute} aria-label={call.muted ? 'Unmute microphone' : 'Mute microphone'} disabled={phase !== 'connected'}>
                <Icon name={call.muted ? 'micoff' : 'mic'} size={24} />
              </button>
              <button className="rbtn end" onClick={endCall} aria-label="End call"><Icon name="hangup" size={28} /></button>
            </>
          ) : (
            <>
              <button className="rbtn" onClick={dismissCall} aria-label="Close"><Icon name="x" size={22} /></button>
              <button className="rbtn go" onClick={startCall} aria-label={phase === 'error' ? 'Retry call' : 'Call again'}><Icon name="phone" size={24} /></button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
