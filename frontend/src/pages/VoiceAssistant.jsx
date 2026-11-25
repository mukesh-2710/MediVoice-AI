import React from 'react'
import { useApp } from '../context/AppContext.jsx'
import { useFetch } from '../lib/useFetch.js'
import { api } from '../lib/api.js'
import { isCallActive } from '../lib/callMachine.js'
import Icon from '../components/Icon.jsx'
import { Empty } from '../components/ui.jsx'

export default function VoiceAssistant() {
  const { call, startCall, state } = useApp()
  const cfg = useFetch(() => api.config(), [])
  const active = isCallActive(call.phase)
  const notReady = cfg.data && !cfg.data.voice_ready

  return (
    <div className="grid-main">
      <section className="panel">
        <header><h2>Place a call</h2><span className="muted">{state.activeCallIds.length} active</span></header>
        {notReady && (
          <div className="banner warn" role="alert">
            <span className="grow">Voice is not configured. Add {!cfg.data.gemini_configured && 'GEMINI_API_KEY'}{!cfg.data.gemini_configured && !cfg.data.elevenlabs_configured && ' and '}{!cfg.data.elevenlabs_configured && 'ELEVENLABS_API_KEY'} to backend/.env and restart.</span>
          </div>
        )}
        <div className="callpad">
          <p className="muted">You’ll speak to the clinic’s AI receptionist through your browser microphone. It can check availability, book and cancel.</p>
          <button className="btn primary" onClick={startCall} disabled={active}>
            <Icon name="phone" /> {active ? 'Call in progress' : 'Try Call'}
          </button>
          <div className="hint">
            <span>“Book a cardiologist tomorrow”</span>
            <span>“Earliest dermatologist”</span>
            <span>“Cancel my appointment”</span>
          </div>
        </div>
      </section>
      <section className="panel">
        <header><h2>Live transcript</h2><span className="muted">{call.transcript.length ? `${call.transcript.length} lines` : ''}</span></header>
        <div className="live-transcript">
          {call.transcript.length === 0 ? (
            <Empty title="No conversation yet">Words appear here as they’re spoken, for both sides.</Empty>
          ) : call.transcript.map((m) => (
            <div className="tline" key={m.key} style={m.final ? undefined : { opacity: 0.6 }}>
              <span className={`r ${m.role === 'user' ? 'you' : 'agent'}`}>{m.role === 'user' ? 'Caller' : 'Agent'}</span>
              <span>{m.text}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
