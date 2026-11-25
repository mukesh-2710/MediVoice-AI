import React from 'react'
import { useApp } from '../context/AppContext.jsx'
import { timeAgo } from '../lib/format.js'
import { Empty, Skeleton } from '../components/ui.jsx'

export default function Activity() {
  const { state } = useApp()
  if (!state.loaded) return <Skeleton h={260} />
  return (
    <section className="panel">
      <header><h2>Bookings, cancellations and calls</h2><span className="muted">newest first</span></header>
      {state.activity.length === 0 ? <Empty title="Nothing logged yet" /> : (
        <div className="timeline">
          {state.activity.map((e) => (
            <div className={`tl ${e.event_type.replace('.', '-')}`} key={e.id}>
              {e.message}
              <small>{e.event_type} · {timeAgo(e.created_at)}{e.call_id ? ` · call ${e.call_id.slice(0, 6)}` : ''}</small>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
