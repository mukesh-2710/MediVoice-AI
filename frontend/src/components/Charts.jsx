import React from 'react'
import { parseISODate } from '../lib/format.js'

export function DayBars({ data }) {
  const max = Math.max(1, ...data.map((d) => d.count))
  return (
    <div className="bars" role="img" aria-label="Confirmed appointments for the next seven days">
      {data.map((d, i) => (
        <div className="bar" key={d.date}>
          <span className="n">{d.count}</span>
          <div className={`col ${d.count ? '' : 'zero'}`} style={{ height: `${(d.count / max) * 100}%` }} />
          <span className="d">{i === 0 ? 'Today' : parseISODate(d.date).toLocaleDateString('en-IN', { weekday: 'short' })}</span>
        </div>
      ))}
    </div>
  )
}

export function StatusSplit({ by }) {
  const total = (by.BOOKED || 0) + (by.COMPLETED || 0) + (by.CANCELLED || 0)
  const seg = [
    ['Confirmed', by.BOOKED || 0, 'var(--green)'],
    ['Completed', by.COMPLETED || 0, 'var(--blue)'],
    ['Cancelled', by.CANCELLED || 0, 'var(--coral)'],
  ]
  return (
    <div>
      <div className="split" role="img" aria-label="Appointment status split">
        {total > 0 && seg.map(([l, n, c]) => <span key={l} style={{ width: `${(n / total) * 100}%`, background: c }} />)}
      </div>
      <div className="legend">
        {seg.map(([l, n, c]) => (
          <span key={l}><i style={{ background: c }} />{l} <b className="num" style={{ color: 'var(--text)' }}>{n}</b></span>
        ))}
      </div>
    </div>
  )
}

export function SpecialityBars({ rows }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <div>
      {rows.map((r) => (
        <div className="hbar" key={r.speciality}>
          <span>{r.speciality}</span>
          <div className="t"><i style={{ width: `${(r.count / max) * 100}%` }} /></div>
          <b className="num">{r.count}</b>
        </div>
      ))}
    </div>
  )
}
