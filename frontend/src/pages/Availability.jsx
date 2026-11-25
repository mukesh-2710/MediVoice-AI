import React, { useState } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { api } from '../lib/api.js'
import { useFetch } from '../lib/useFetch.js'
import { addDays, formatDay, parseISODate } from '../lib/format.js'
import { Empty, ErrorBanner, Initials, Skeleton } from '../components/ui.jsx'

export default function Availability() {
  const { state } = useApp()
  const today = state.stats?.per_day?.[0]?.date || new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)
  const [spec, setSpec] = useState('All')
  const specs = ['All', ...new Set(state.doctors.map((d) => d.speciality))]
  const { data, error, loading, reload } = useFetch(
    () => api.availability(date, spec === 'All' ? {} : { speciality: spec }), [date, spec, state.availabilityTick])
  const rows = (data?.doctors || []).filter((r) => r.available.length || r.booked.length)
  return (
    <>
      <div className="datestrip" role="group" aria-label="Choose a date">
        {Array.from({ length: 14 }, (_, i) => addDays(today, i)).map((iso) => {
          const d = parseISODate(iso)
          return (
            <button key={iso} aria-pressed={date === iso} onClick={() => setDate(iso)}>
              {d.toLocaleDateString('en-IN', { weekday: 'short' })}<b>{d.getDate()}</b>{d.toLocaleDateString('en-IN', { month: 'short' })}
            </button>
          )
        })}
      </div>
      <div className="toolbar"><div className="chips">{specs.map((s) => <button key={s} className="chip" aria-pressed={spec === s} onClick={() => setSpec(s)}>{s}</button>)}</div></div>
      {error && <ErrorBanner onRetry={reload}>{error}</ErrorBanner>}
      <section className="panel">
        <header><h2>{formatDay(date)}</h2><span className="muted">{date}{data?.holiday ? ` · closed: ${data.holiday}` : ''}</span></header>
        {loading && !data ? <Skeleton h={120} /> : data?.holiday ? <Empty title="Clinic closed">{data.holiday}. No appointments can be booked on this day.</Empty>
          : rows.length === 0 ? <Empty title="No sessions">No doctors are scheduled on this day for this filter.</Empty>
          : rows.map((r) => (
            <div className="avail-row" key={r.doctor_id}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}><Initials name={r.name} /><div><b style={{ fontWeight: 600 }}>{r.name}</b><div className="muted" style={{ fontSize: 13 }}>{r.speciality}</div></div></div>
              <div className="slots">
                {r.available.length === 0 && <span className="muted">Fully booked</span>}
                {r.available.map((s) => <span className="slot" key={s.time}>{s.label}</span>)}
                {r.booked.map((s) => <span className="slot booked" key={s.time} title="Booked">{s.label}</span>)}
              </div>
            </div>
          ))}
      </section>
    </>
  )
}
