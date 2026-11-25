import React, { useMemo, useState } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { api } from '../lib/api.js'
import { formatDay, groupPhone, to12h } from '../lib/format.js'
import Icon from '../components/Icon.jsx'
import { Empty, StatusBadge } from '../components/ui.jsx'

export default function Appointments() {
  const { state } = useApp()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const rows = useMemo(() => {
    const ql = q.trim().toLowerCase()
    return state.appointments.filter((a) =>
      (!status || a.status === status) && (!from || a.appointment_date >= from) && (!to || a.appointment_date <= to) &&
      (!ql || a.patient_phone.includes(ql.replace(/\D/g, '') || '§') || a.doctor_name.toLowerCase().includes(ql) ||
        a.appointment_ref.toLowerCase().includes(ql) || a.speciality.toLowerCase().includes(ql)))
  }, [state.appointments, q, status, from, to])

  return (
    <>
      <div className="toolbar">
        <input className="input grow" placeholder="Search phone, doctor or reference" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search appointments" />
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All statuses</option><option value="BOOKED">Confirmed</option><option value="CANCELLED">Cancelled</option><option value="COMPLETED">Completed</option>
        </select>
        <input className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From date" />
        <input className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To date" />
        <a className="btn" href={api.exportUrl(status)} download><Icon name="download" size={16} /> CSV</a>
      </div>
      {rows.length === 0 ? (
        <section className="panel"><Empty title={state.appointments.length ? 'No matches' : 'No appointments yet'}>{state.appointments.length ? 'Adjust the filters above.' : 'Book one by phone and it will appear here instantly.'}</Empty></section>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Reference</th><th>Patient phone</th><th>Doctor</th><th>When</th><th>Fee</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id} className={state.flash[a.id] ? `flash-${state.flash[a.id]}` : ''}>
                  <td className="mono">{a.appointment_ref}</td>
                  <td className="mono">{groupPhone(a.patient_phone)}</td>
                  <td>{a.doctor_name}<div className="muted" style={{ fontSize: 12.5 }}>{a.speciality}</div></td>
                  <td>{formatDay(a.appointment_date)}<div className="muted" style={{ fontSize: 12.5 }}>{to12h(a.appointment_time)}</div></td>
                  <td className="mono">₹{a.consultation_fee}</td>
                  <td><StatusBadge status={a.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
