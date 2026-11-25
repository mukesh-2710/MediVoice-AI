import test from 'node:test'
import assert from 'node:assert/strict'
import { actionFromEvent, callReducer, initialCall, isCallActive } from './callMachine.js'

const run = (actions, s = initialCall) => actions.reduce(callReducer, s)

test('happy path: ringing -> connecting -> connected -> ending -> ended', () => {
  let s = run([{ type: 'start' }])
  assert.equal(s.phase, 'ringing')
  s = run([{ type: 'connecting' }], s)
  assert.equal(s.phase, 'connecting')
  s = run([{ type: 'connected', at: 1000 }], s)
  assert.equal(s.phase, 'connected')
  s = run([{ type: 'ending' }], s)
  assert.equal(s.phase, 'ending')
  s = run([{ type: 'ended', at: 66000 }], s)
  assert.equal(s.phase, 'ended')
  assert.equal(s.endedAfter, 65)
})

test('start is ignored while a call is active (no double sessions from one tab)', () => {
  const s = run([{ type: 'start' }, { type: 'connecting' }, { type: 'start' }])
  assert.equal(s.phase, 'connecting')
})

test('errors move to error and allow retry via start', () => {
  let s = run([{ type: 'start' }, { type: 'error', message: 'Microphone access is blocked.' }])
  assert.equal(s.phase, 'error')
  assert.equal(s.error, 'Microphone access is blocked.')
  s = run([{ type: 'start' }], s)
  assert.equal(s.phase, 'ringing')
  assert.equal(s.error, null)
})

test('connected before connecting is allowed only from ringing/connecting', () => {
  assert.equal(run([{ type: 'connected' }]).phase, 'idle')
  assert.equal(run([{ type: 'start' }, { type: 'connected' }]).phase, 'connected')
})

test('error after the call has ended does not clobber the ended screen', () => {
  const s = run([{ type: 'start' }, { type: 'connecting' }, { type: 'connected' }, { type: 'ended' }, { type: 'error', message: 'late' }])
  assert.equal(s.phase, 'ended')
})

test('partial transcripts replace each other, a final closes the line', () => {
  let s = run([{ type: 'start' }])
  s = run([
    { type: 'transcript', role: 'user', text: 'I want', final: false },
    { type: 'transcript', role: 'user', text: 'I want a heart doctor', final: false },
  ], s)
  assert.equal(s.transcript.length, 1)
  s = run([{ type: 'transcript', id: 'e1', role: 'user', text: 'I want a heart doctor.', final: true }], s)
  assert.equal(s.transcript.length, 1)
  assert.equal(s.transcript[0].final, true)
  s = run([{ type: 'transcript', id: 'e2', role: 'agent', text: 'Sure.', final: true }], s)
  assert.deepEqual(s.transcript.map((t) => t.role), ['user', 'agent'])
})

test('duplicate final transcript events are not shown twice', () => {
  const a = { type: 'transcript', id: 'e1', role: 'agent', text: 'Hello', final: true }
  const s = run([{ type: 'start' }, a, a])
  assert.equal(s.transcript.length, 1)
})

test('speaking indicators are cleared when the call ends', () => {
  let s = run([{ type: 'start' }, { type: 'connecting' }, { type: 'connected' }, { type: 'speaking', who: 'agent', value: true }])
  assert.equal(s.agentSpeaking, true)
  s = run([{ type: 'ended' }], s)
  assert.equal(s.agentSpeaking, false)
})

test('mute toggles', () => {
  let s = run([{ type: 'mute' }])
  assert.equal(s.muted, true)
  s = run([{ type: 'mute' }], s)
  assert.equal(s.muted, false)
})

test('confirmation cards are de-duplicated per appointment and kind', () => {
  const booked = { type: 'card', card: { kind: 'booked', id: 5, appointment: {} } }
  const cancelled = { type: 'card', card: { kind: 'cancelled', id: 5, appointment: {} } }
  const s = run([booked, booked, cancelled])
  assert.equal(s.cards.length, 2)
})

test('server events map to actions', () => {
  assert.equal(actionFromEvent({ type: 'agent.speaking', data: { speaking: true } }).value, true)
  assert.equal(actionFromEvent({ type: 'transcript.final', id: 'x', data: { role: 'user', text: 'hi' } }).final, true)
  assert.equal(actionFromEvent({ type: 'appointment.created', data: { appointment: { id: 1 } } }).card.kind, 'booked')
  assert.equal(actionFromEvent({ type: 'appointment.cancelled', data: {} }), null)
  assert.equal(actionFromEvent({ type: 'unknown' }), null)
})

test('isCallActive', () => {
  assert.equal(isCallActive('connected'), true)
  assert.equal(isCallActive('ended'), false)
})
