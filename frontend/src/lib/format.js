export function to12h(hhmm) {
  if (!hhmm || !/^\d{1,2}:\d{2}$/.test(hhmm)) return hhmm || ''
  const [h, m] = hhmm.split(':').map(Number)
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}

export function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds || 0))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

// 'YYYY-MM-DD' -> local Date without timezone shifting
export function parseISODate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function formatDay(iso, today = new Date()) {
  const d = parseISODate(iso)
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const diff = Math.round((d - t) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Tomorrow'
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
}

export function toISODate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function addDays(iso, n) {
  const d = parseISODate(iso)
  d.setDate(d.getDate() + n)
  return toISODate(d)
}

export function maskPhone(p) {
  if (!p || p.length < 7) return p || ''
  return p.slice(0, 2) + '•'.repeat(p.length - 5) + p.slice(-3)
}

export function groupPhone(p) {
  return p && p.length === 10 ? `${p.slice(0, 5)} ${p.slice(5)}` : p || ''
}

export function timeAgo(isoUtc, now = Date.now()) {
  const s = Math.round((now - new Date(isoUtc).getTime()) / 1000)
  if (s < 10) return 'just now'
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return new Date(isoUtc).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

export const STATUS_LABEL = { BOOKED: 'Confirmed', CANCELLED: 'Cancelled', COMPLETED: 'Completed' }
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
