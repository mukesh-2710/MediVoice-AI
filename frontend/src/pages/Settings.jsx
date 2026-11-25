import React from 'react'
import { useApp } from '../context/AppContext.jsx'
import { api } from '../lib/api.js'
import { useFetch } from '../lib/useFetch.js'
import { ErrorBanner, Skeleton } from '../components/ui.jsx'

const Yes = ({ ok, yes = 'Configured', no = 'Missing' }) => <span className={`badge ${ok ? 'BOOKED' : 'CANCELLED'}`}>{ok ? yes : no}</span>

export default function Settings() {
  const { state } = useApp()
  const cfg = useFetch(() => api.config(), [])
  const health = useFetch(() => api.health(), [state.connection])
  const c = cfg.data
  return (
    <div className="stack">
      {(cfg.error || health.error) && <ErrorBanner onRetry={() => { cfg.reload(); health.reload() }}>{cfg.error || health.error}</ErrorBanner>}
      <section className="panel">
        <header><h2>Connections</h2><span className="muted">API keys stay on the server; only status is shown here</span></header>
        {!c ? <Skeleton h={160} /> : (
          <dl className="kv">
            <dt>Backend API</dt><dd><Yes ok={health.data?.status === 'ok'} yes="Healthy" no="Unreachable" /></dd>
            <dt>Database</dt><dd><Yes ok={health.data?.database === 'ok'} yes="SQLite OK" no="Error" /></dd>
            <dt>Real-time socket</dt><dd><Yes ok={state.connection === 'live'} yes="Connected" no={state.connection} /></dd>
            <dt>Gemini</dt><dd><Yes ok={c.gemini_configured} /> <span className="muted">&nbsp;{c.llm_model}</span></dd>
            <dt>ElevenLabs (STT + TTS)</dt><dd><Yes ok={c.elevenlabs_configured} /> <span className="muted">&nbsp;{c.tts_model}</span></dd>
            <dt>Voice activity detection</dt><dd>{c.vad}</dd>
            <dt>Audio transport</dt><dd>{c.transport}</dd>
            <dt>Clinic</dt><dd>{c.clinic_name} · {c.clinic_timezone} · bookings open {c.booking_horizon_days} days ahead</dd>
          </dl>
        )}
      </section>
      <section className="panel">
        <header><h2>About caller identification</h2></header>
        <p className="note">Callers are identified only by the phone number they say aloud, and the agent reads it back for confirmation. This is not strong authentication: anyone who knows a number can ask about its appointments. A production system would add an OTP or caller-ID check.</p>
      </section>
    </div>
  )
}
