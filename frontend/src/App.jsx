import React, { useEffect, useState } from 'react'
import { useApp } from './context/AppContext.jsx'
import Sidebar, { ConnectionPill, PAGES } from './components/Sidebar.jsx'
import PhoneModal from './components/PhoneModal.jsx'
import Icon from './components/Icon.jsx'
import { ErrorBanner } from './components/ui.jsx'
import Overview from './pages/Overview.jsx'
import VoiceAssistant from './pages/VoiceAssistant.jsx'
import Doctors from './pages/Doctors.jsx'
import Availability from './pages/Availability.jsx'
import Appointments from './pages/Appointments.jsx'
import CallHistory from './pages/CallHistory.jsx'
import Activity from './pages/Activity.jsx'
import Settings from './pages/Settings.jsx'
import { isCallActive } from './lib/callMachine.js'

const VIEWS = { overview: Overview, voice: VoiceAssistant, doctors: Doctors, availability: Availability, appointments: Appointments, calls: CallHistory, activity: Activity, settings: Settings }
const fromHash = () => { const h = location.hash.replace('#', ''); return VIEWS[h] ? h : 'overview' }

export default function App() {
  const { state, dispatch, call, startCall, loadError, resync } = useApp()
  const [page, setPageState] = useState(fromHash)
  const setPage = (p) => { location.hash = p; setPageState(p) }
  useEffect(() => { const h = () => setPageState(fromHash()); window.addEventListener('hashchange', h); return () => window.removeEventListener('hashchange', h) }, [])

  const View = VIEWS[page]
  const title = PAGES.find((p) => p[0] === page)[1]
  const today = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })
  const active = isCallActive(call.phase)

  return (
    <div className="app">
      <Sidebar page={page} setPage={setPage} />
      <main className="main">
        <header className="topbar">
          <div>
            <h1>{page === 'overview' ? today : title}</h1>
            <p className="sub">{page === 'overview' ? 'Clinic overview' : today}</p>
          </div>
          <div className="actions">
            <span className="show-mobile"><ConnectionPill /></span>
            <button className="btn primary" onClick={startCall} disabled={active}><Icon name="phone" /> Try Call</button>
          </div>
        </header>

        {loadError && <ErrorBanner onRetry={resync}>{loadError}</ErrorBanner>}
        {state.stale && !loadError && (
          <div className="banner warn" role="status"><span className="grow">Connection lost. Showing the last known data, which may be out of date. Reconnecting…</span></div>
        )}

        <View />
      </main>

      <PhoneModal />
      {state.lastError && (
        <div className="toast" role="alert">
          <b>{state.lastError.message}</b>
          {state.lastError.note && <div className="muted" style={{ marginTop: 4 }}>{state.lastError.note}</div>}
          <div style={{ marginTop: 8 }}><button className="btn small" onClick={() => dispatch({ type: 'dismiss-error' })}>Dismiss</button></div>
        </div>
      )}
    </div>
  )
}
