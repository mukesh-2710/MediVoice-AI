// Pure state container for dashboard data. No React imports so it can be unit-tested with node:test.
// Real-time events are de-duplicated by event id, and every reconnect is followed by a full
// database-backed snapshot, so a missed or repeated event can never leave the screen wrong.

export const initialState = {
  loaded: false,
  connection: 'connecting', // connecting | live | reconnecting | offline
  stale: false,
  doctors: [],
  appointments: [],
  stats: null,
  calls: [],
  activity: [],
  activeCallIds: [],
  flash: {}, // appointment id -> 'created' | 'cancelled'
  seen: [], // recent event ids (bounded)
  availabilityTick: 0,
  refreshTick: 0,
  lastError: null,
}

const SEEN_LIMIT = 500

export function reducer(state, action) {
  switch (action.type) {
    case 'snapshot': {
      const s = action.payload
      return {
        ...state,
        loaded: true,
        stale: false,
        doctors: s.doctors ?? state.doctors,
        appointments: s.appointments ?? state.appointments,
        stats: s.stats ?? state.stats,
        calls: s.calls ?? state.calls,
        activity: s.activity ?? state.activity,
        activeCallIds: s.active_call_ids ?? state.activeCallIds,
        availabilityTick: state.availabilityTick + 1,
      }
    }
    case 'connection': {
      const connection = action.status
      return { ...state, connection, stale: connection === 'live' ? state.stale : state.loaded }
    }
    case 'flash-clear': {
      const flash = { ...state.flash }
      delete flash[action.id]
      return { ...state, flash }
    }
    case 'dismiss-error':
      return { ...state, lastError: null }
    case 'event':
      return applyEvent(state, action.event)
    default:
      return state
  }
}

export function applyEvent(state, ev) {
  if (!ev || !ev.type) return state
  if (ev.id) {
    if (state.seen.includes(ev.id)) return state // duplicate delivery
    state = { ...state, seen: [...state.seen, ev.id].slice(-SEEN_LIMIT) }
  }
  const d = ev.data || {}
  switch (ev.type) {
    case 'appointment.created': {
      const a = d.appointment
      if (!a) return state
      const exists = state.appointments.some((x) => x.id === a.id)
      const appointments = exists
        ? state.appointments.map((x) => (x.id === a.id ? { ...x, ...a } : x))
        : [a, ...state.appointments]
      return { ...state, appointments, flash: { ...state.flash, [a.id]: 'created' }, refreshTick: state.refreshTick + 1 }
    }
    case 'appointment.cancelled': {
      const a = d.appointment
      if (!a) return state
      const appointments = state.appointments.some((x) => x.id === a.id)
        ? state.appointments.map((x) => (x.id === a.id ? { ...x, ...a } : x))
        : [a, ...state.appointments]
      return { ...state, appointments, flash: { ...state.flash, [a.id]: 'cancelled' }, refreshTick: state.refreshTick + 1 }
    }
    case 'availability.updated':
      return { ...state, availabilityTick: state.availabilityTick + 1 }
    case 'call.started': {
      const id = d.call_id
      return id && !state.activeCallIds.includes(id)
        ? { ...state, activeCallIds: [...state.activeCallIds, id], refreshTick: state.refreshTick + 1 }
        : state
    }
    case 'call.ended':
      return { ...state, activeCallIds: state.activeCallIds.filter((c) => c !== d.call_id), refreshTick: state.refreshTick + 1 }
    case 'system.error':
      return { ...state, lastError: { message: d.message, note: d.note, at: ev.ts } }
    case 'resync.required':
      return { ...state, stale: true, refreshTick: state.refreshTick + 1 }
    default:
      return state
  }
}
