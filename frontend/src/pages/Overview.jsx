import React from 'react'
import { useApp } from '../context/AppContext.jsx'
import { DayBars, SpecialityBars, StatusSplit } from '../components/Charts.jsx'
import { Empty, Skeleton, StatusBadge } from '../components/ui.jsx'
import { formatDay, groupPhone, maskPhone, timeAgo, to12h } from '../lib/format.js'

function Stat({ v, l, lead, live }) {
  return (
    <div className={`stat ${lead ? 'lead' : ''}`}>
      <div className={`v ${live ? 'live' : ''}`}>{v ?? '–'}</div>
      <div className="l">{l}</div>
    </div>
  )
}

export default function Overview() {
  const { state } = useApp()
  const s = state.stats
  const todayIso = s?.per_day?.[0]?.date
  const today = state.appointments.filter((a) => a.appointment_date === todayIso && a.status !== 'CANCELLED')
    .sort((a, b) => a.appointment_time.localeCompare(b.appointment_time))

  if (!state.loaded) return <><Skeleton h={190} style={{ marginBottom: 18 }} /><Skeleton h={260} /></>

  return (
    <>
      <section className="stats" aria-label="Key figures">
        <Stat lead v={s?.total_appointments} l="Total appointments" />
        <Stat v={s?.today_appointments} l="Today" />
        <Stat v={s?.confirmed_appointments} l="Confirmed" />
        <Stat v={s?.cancelled_appointments} l="Cancelled" />
        <Stat v={s?.available_slots?.toLocaleString('en-IN')} l="Free slots ahead" />
        <Stat v={s?.active_calls} l="Active calls" live={s?.active_calls > 0} />
        <Stat v={s?.total_doctors} l="Doctors" />
        <Stat v={s?.completed_appointments} l="Completed" />
      </section>

      <div className="grid-main">
        <div className="stack">
          <section className="panel">
            <header><h2>Confirmed visits, next 7 days</h2><span className="muted">from the database</span></header>
            <DayBars data={s?.per_day || []} />
          </section>
          <section className="panel">
            <header><h2>Today’s schedule</h2><span className="muted">{today.length} visit{today.length === 1 ? '' : 's'}</span></header>
            {today.length === 0 ? (
              <Empty title="Nothing scheduled today">Bookings made by phone appear here the moment they’re confirmed.</Empty>
            ) : (
              <div className="list">
                {today.map((a) => (
                  <div className="row appt" key={a.id}>
                    <span className="time">{to12h(a.appointment_time)}</span>
                    <div className="who"><b>{a.doctor_name}</b><span>{maskPhone(a.patient_phone)} · {a.speciality}</span></div>
                    <StatusBadge status={a.status} />
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <div className="stack">
          <section className="panel">
            <header><h2>Live activity</h2></header>
            {state.activity.length === 0 ? (
              <Empty title="No activity yet">Start a call to see bookings and cancellations stream in.</Empty>
            ) : (
              <div className="list">
                {state.activity.slice(0, 7).map((e) => (
                  <div className="row" style={{ gridTemplateColumns: '1fr' }} key={e.id}>
                    <span>{e.message}</span>
                    <span className="faint" style={{ fontSize: 12.5 }}>{timeAgo(e.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
          <section className="panel">
            <header><h2>Status</h2></header>
            <StatusSplit by={s?.by_status || {}} />
          </section>
          <section className="panel">
            <header><h2>By speciality</h2></header>
            {s?.by_speciality?.length ? <SpecialityBars rows={s.by_speciality} /> : <Empty title="No visits yet" />}
          </section>
        </div>
      </div>
    </>
  )
}
