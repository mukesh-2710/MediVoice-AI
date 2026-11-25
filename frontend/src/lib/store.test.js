import test from 'node:test'
import assert from 'node:assert/strict'
import { initialState, reducer } from './store.js'

const ev = (id, type, data) => ({ id, type, data, ts: '2026-11-24T10:00:00Z' })
const appt = (id, status = 'BOOKED') => ({ id, appointment_ref: `MV-${id}`, status, doctor_name: 'Dr. X' })
const apply = (s, e) => reducer(s, { type: 'event', event: e })

test('appointment.created adds a row, flags it and asks for a stats refresh', () => {
  const s = apply(initialState, ev('a-1', 'appointment.created', { appointment: appt(7) }))
  assert.equal(s.appointments.length, 1)
  assert.equal(s.flash[7], 'created')
  assert.equal(s.refreshTick, 1)
})

test('duplicate event ids are ignored (no duplicate rows, no double refresh)', () => {
  let s = apply(initialState, ev('a-1', 'appointment.created', { appointment: appt(7) }))
  s = apply(s, ev('a-1', 'appointment.created', { appointment: appt(7) }))
  assert.equal(s.appointments.length, 1)
  assert.equal(s.refreshTick, 1)
})

test('same appointment arriving under a new event id is merged, not duplicated', () => {
  let s = apply(initialState, ev('a-1', 'appointment.created', { appointment: appt(7) }))
  s = apply(s, ev('a-2', 'appointment.created', { appointment: appt(7) }))
  assert.equal(s.appointments.length, 1)
})

test('appointment.cancelled updates status in place and highlights', () => {
  let s = apply(initialState, ev('a-1', 'appointment.created', { appointment: appt(7) }))
  s = apply(s, ev('a-2', 'appointment.cancelled', { appointment: appt(7, 'CANCELLED') }))
  assert.equal(s.appointments[0].status, 'CANCELLED')
  assert.equal(s.flash[7], 'cancelled')
})

test('cancelled event for an unseen appointment still shows it', () => {
  const s = apply(initialState, ev('a-9', 'appointment.cancelled', { appointment: appt(3, 'CANCELLED') }))
  assert.equal(s.appointments[0].id, 3)
})

test('call lifecycle tracks active calls', () => {
  let s = apply(initialState, ev('c-1', 'call.started', { call_id: 'abc' }))
  assert.deepEqual(s.activeCallIds, ['abc'])
  s = apply(s, ev('c-2', 'call.started', { call_id: 'abc' }))
  assert.deepEqual(s.activeCallIds, ['abc'])
  s = apply(s, ev('c-3', 'call.ended', { call_id: 'abc' }))
  assert.deepEqual(s.activeCallIds, [])
})

test('snapshot replaces data and clears stale flag', () => {
  let s = { ...initialState, loaded: true, stale: true }
  s = reducer(s, { type: 'snapshot', payload: { doctors: [{ id: 1 }], appointments: [appt(1)], stats: { total_appointments: 1 }, active_call_ids: ['x'] } })
  assert.equal(s.stale, false)
  assert.equal(s.appointments.length, 1)
  assert.deepEqual(s.activeCallIds, ['x'])
})

test('losing the connection after load marks data stale; reconnect keeps it until resync', () => {
  let s = reducer(initialState, { type: 'snapshot', payload: {} })
  s = reducer(s, { type: 'connection', status: 'reconnecting' })
  assert.equal(s.stale, true)
  s = reducer(s, { type: 'connection', status: 'live' })
  assert.equal(s.stale, true) // only a fresh snapshot clears it
  s = reducer(s, { type: 'snapshot', payload: {} })
  assert.equal(s.stale, false)
})

test('before first load a failed connection is not reported as stale data', () => {
  const s = reducer(initialState, { type: 'connection', status: 'offline' })
  assert.equal(s.stale, false)
})

test('system.error is surfaced; resync.required marks stale', () => {
  let s = apply(initialState, ev('e-1', 'system.error', { message: 'TTS failed', note: 'Booking MV-1 was saved' }))
  assert.equal(s.lastError.message, 'TTS failed')
  s = apply(s, { type: 'resync.required' })
  assert.equal(s.stale, true)
})

test('events without data or unknown types are harmless', () => {
  assert.equal(apply(initialState, null), initialState)
  const s = apply(initialState, ev('z-1', 'something.else', {}))
  assert.equal(s.appointments.length, 0)
})

test('seen list stays bounded', () => {
  let s = initialState
  for (let i = 0; i < 700; i++) s = apply(s, ev(`i-${i}`, 'availability.updated', {}))
  assert.ok(s.seen.length <= 500)
})
