import test from 'node:test'
import assert from 'node:assert/strict'
import { addDays, formatDay, formatDuration, groupPhone, maskPhone, timeAgo, to12h } from './format.js'

test('to12h', () => {
  assert.equal(to12h('09:00'), '9:00 AM')
  assert.equal(to12h('12:30'), '12:30 PM')
  assert.equal(to12h('00:05'), '12:05 AM')
  assert.equal(to12h('15:45'), '3:45 PM')
})
test('formatDuration', () => {
  assert.equal(formatDuration(0), '00:00')
  assert.equal(formatDuration(75), '01:15')
  assert.equal(formatDuration(-3), '00:00')
})
test('formatDay relative labels', () => {
  const today = new Date(2026, 10, 24)
  assert.equal(formatDay('2026-11-24', today), 'Today')
  assert.equal(formatDay('2026-11-25', today), 'Tomorrow')
})
test('addDays crosses month boundary', () => assert.equal(addDays('2026-11-30', 2), '2026-12-02'))
test('phone helpers', () => {
  assert.equal(groupPhone('9876543210'), '98765 43210')
  assert.equal(maskPhone('9876543210'), '98•••••210')
})
test('timeAgo', () => {
  const now = Date.parse('2026-11-24T10:00:00Z')
  assert.equal(timeAgo('2026-11-24T09:59:58Z', now), 'just now')
  assert.equal(timeAgo('2026-11-24T09:30:00Z', now), '30 min ago')
})
