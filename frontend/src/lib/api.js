const BASE = import.meta.env?.VITE_API_BASE || ''

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request(path, options) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch {
    throw new ApiError('Cannot reach the server. Check that the backend is running.', 0, 'network')
  }
  if (!res.ok) {
    let body = null
    try {
      body = await res.json()
    } catch {
      /* not json */
    }
    const e = body?.error
    throw new ApiError(e?.message || `Request failed (${res.status})`, res.status, e?.code)
  }
  return res
}

const json = async (path, options) => (await request(path, options)).json()

export const api = {
  state: () => json('/api/state'),
  stats: () => json('/api/stats'),
  doctors: () => json('/api/doctors'),
  availability: (date, params = {}) => json(`/api/availability?${new URLSearchParams({ date, ...params })}`),
  appointments: (params = {}) => json(`/api/appointments?${new URLSearchParams(params)}`),
  calls: () => json('/api/calls'),
  transcript: (id) => json(`/api/calls/${id}/transcript`),
  activity: (limit = 100) => json(`/api/activity?limit=${limit}`),
  config: () => json('/api/config/status'),
  health: () => json('/api/health'),
  offer: (sdp, type) =>
    json('/api/offer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sdp, type }) }),
  endCall: (id) => fetch(`${BASE}/api/calls/${id}/end`, { method: 'POST', keepalive: true }).catch(() => {}),
  exportUrl: (status) => `${BASE}/api/appointments/export.csv${status ? `?status=${status}` : ''}`,
  transcriptUrl: (id) => `${BASE}/api/calls/${id}/transcript.txt`,
}
