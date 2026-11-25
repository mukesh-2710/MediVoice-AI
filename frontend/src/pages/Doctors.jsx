import React, { useMemo, useState } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { api } from '../lib/api.js'
import { useFetch } from '../lib/useFetch.js'
import { WEEKDAYS, addDays, formatDay, to12h } from '../lib/format.js'
import { Empty, Initials } from '../components/ui.jsx'

function DoctorCard({ d, today }) {
  const [open, setOpen] = useState(false)
  const [date, setDate] = useState(today)
  const { state } = useApp()
  const slots = useFetch(() => (open ? api.availability(date, { doctor_id: d.id }) : Promise.resolve(null)), [open, date, d.id, state.availabilityTick])
  const days = new Set(d.schedule.map((s) => s.weekday))
  const hours = d.schedule[0] ? `${to12h(d.schedule[0].start_time)} – ${to12h(d.schedule[0].end_time)}` : ''
  const row = slots.data?.doctors?.[0]
  return (
    <article className="doc">
      <div className="head"><Initials name={d.name} /><div><h3 style={{ fontWeight: 600 }}>{d.name}</h3><span className="muted">{d.speciality}</span></div></div>
      <div className="meta"><span>{d.experience_years} yrs</span><span>₹{d.consultation_fee}</span><span>{d.slot_minutes} min visits</span></div>
      <div className="days" aria-label="Working days">{WEEKDAYS.map((w, i) => <span key={w} className={days.has(i) ? 'on' : ''}>{w}</span>)}</div>
      <span className="faint" style={{ fontSize: 13 }}>{hours}{d.schedule.some((s) => s.break_start) ? ` · break ${to12h(d.schedule[0].break_start)}` : ''}</span>
      <button className="btn small ghost" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? 'Hide slots' : 'View slots'}</button>
      {open && (
        <div>
          <div className="chips" style={{ marginBottom: 10 }}>
            {[0, 1, 2, 3].map((n) => { const iso = addDays(today, n); return <button key={iso} className="chip" aria-pressed={date === iso} onClick={() => setDate(iso)}>{formatDay(iso)}</button> })}
          </div>
          {slots.loading && !row ? <span className="muted">Loading…</span> : slots.data?.holiday ? <span className="muted">Closed: {slots.data.holiday}</span>
            : row && (row.available.length || row.booked.length) ? (
              <div className="slots">
                {row.available.map((s) => <span className="slot" key={s.time}>{s.label}</span>)}
                {row.booked.map((s) => <span className="slot booked" key={s.time}>{s.label}</span>)}
              </div>
            ) : <span className="muted">No sessions that day.</span>}
        </div>
      )}
    </article>
  )
}

export default function Doctors() {
  const { state } = useApp()
  const [q, setQ] = useState('')
  const [spec, setSpec] = useState('All')
  const specs = useMemo(() => ['All', ...new Set(state.doctors.map((d) => d.speciality))], [state.doctors])
  const today = state.stats?.per_day?.[0]?.date || new Date().toISOString().slice(0, 10)
  const list = state.doctors.filter((d) => (spec === 'All' || d.speciality === spec) && (d.name + d.speciality).toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <div className="toolbar">
        <input className="input grow" placeholder="Search by name or speciality" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search doctors" />
        <div className="chips">{specs.map((s) => <button key={s} className="chip" aria-pressed={spec === s} onClick={() => setSpec(s)}>{s}</button>)}</div>
      </div>
      {list.length === 0 ? <Empty title="No doctors match">Try a different name or speciality.</Empty>
        : <div className="cards">{list.map((d) => <DoctorCard key={d.id} d={d} today={today} />)}</div>}
    </>
  )
}
