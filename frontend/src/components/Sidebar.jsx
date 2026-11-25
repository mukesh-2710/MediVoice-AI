import React from 'react'
import { useApp } from '../context/AppContext.jsx'
import Icon, { Logo } from './Icon.jsx'

export const PAGES = [
  ['overview', 'Overview', 'overview'],
  ['voice', 'AI Voice Assistant', 'voice'],
  ['doctors', 'Doctors', 'doctors'],
  ['availability', 'Availability', 'calendar'],
  ['appointments', 'Appointments', 'list'],
  ['calls', 'Call History', 'history'],
  ['activity', 'Activity Logs', 'pulse'],
  ['settings', 'Settings', 'gear'],
]

export function ConnectionPill() {
  const { state } = useApp()
  const label = { live: 'Live', connecting: 'Connecting', reconnecting: 'Reconnecting', offline: 'Offline' }[state.connection]
  return <span className={`pill ${state.connection}`} role="status"><i />{label}</span>
}

export default function Sidebar({ page, setPage }) {
  const { state } = useApp()
  const live = state.activeCallIds.length > 0
  return (
    <aside className="rail">
      <div className="brand"><Logo /> MediVoice</div>
      <nav className="nav" aria-label="Main">
        {PAGES.map(([id, label, icon]) => (
          <button key={id} aria-current={page === id ? 'page' : undefined} onClick={() => setPage(id)}>
            <Icon name={icon} />
            <span>{label}</span>
            {id === 'voice' && live && <i className="dot" title="Call in progress" />}
          </button>
        ))}
      </nav>
      <div className="rail-foot"><ConnectionPill /></div>
    </aside>
  )
}
