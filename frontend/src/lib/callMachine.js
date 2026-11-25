// Pure state machine for the phone UI. Phases:
// idle -> ringing -> connecting -> connected -> ending -> ended      (and error from anywhere)

export const initialCall = {
  phase: 'idle',
  callId: null,
  error: null,
  muted: false,
  agentSpeaking: false,
  callerSpeaking: false,
  tool: null, // name of the tool currently running, e.g. 'check_doctor_availability'
  transcript: [], // { key, role, text, final }
  cards: [], // booking / cancellation confirmation cards
  seen: [],
  connectedAt: null,
  endedAfter: 0, // seconds, for the summary
}

const ACTIVE = new Set(['ringing', 'connecting', 'connected', 'ending'])
export const isCallActive = (phase) => ACTIVE.has(phase)

export function callReducer(state, a) {
  switch (a.type) {
    case 'start':
      return state.phase === 'idle' || state.phase === 'ended' || state.phase === 'error'
        ? { ...initialCall, phase: 'ringing' }
        : state // a second click while a call is live does nothing
    case 'connecting':
      return state.phase === 'ringing' ? { ...state, phase: 'connecting' } : state
    case 'call-id':
      return { ...state, callId: a.callId }
    case 'connected':
      return state.phase === 'connecting' || state.phase === 'ringing'
        ? { ...state, phase: 'connected', connectedAt: a.at ?? Date.now() }
        : state
    case 'error':
      return isCallActive(state.phase) || state.phase === 'idle'
        ? { ...state, phase: 'error', error: a.message, agentSpeaking: false, callerSpeaking: false, tool: null }
        : state
    case 'ending':
      return isCallActive(state.phase) ? { ...state, phase: 'ending' } : state
    case 'ended': {
      if (state.phase === 'idle' || state.phase === 'ended') return state
      const secs = state.connectedAt ? Math.round(((a.at ?? Date.now()) - state.connectedAt) / 1000) : 0
      return { ...state, phase: state.phase === 'error' ? 'error' : 'ended', agentSpeaking: false, callerSpeaking: false, tool: null, endedAfter: secs }
    }
    case 'reset':
      return initialCall
    case 'mute':
      return { ...state, muted: a.value ?? !state.muted }
    case 'speaking': {
      if (!isCallActive(state.phase)) return state
      return a.who === 'agent' ? { ...state, agentSpeaking: a.value } : { ...state, callerSpeaking: a.value }
    }
    case 'tool':
      return { ...state, tool: a.name }
    case 'transcript': {
      if (a.id && state.seen.includes(a.id)) return state // duplicate event
      const seen = a.id ? [...state.seen, a.id].slice(-200) : state.seen
      const t = [...state.transcript]
      const last = t[t.length - 1]
      if (!a.final) {
        // a partial replaces the previous partial of the same speaker
        if (last && !last.final && last.role === a.role) t[t.length - 1] = { ...last, text: a.text }
        else t.push({ key: `p${t.length}`, role: a.role, text: a.text, final: false })
      } else if (last && !last.final && last.role === a.role) {
        t[t.length - 1] = { ...last, text: a.text, final: true }
      } else {
        t.push({ key: `f${t.length}`, role: a.role, text: a.text, final: true })
      }
      return { ...state, transcript: t, seen }
    }
    case 'card': {
      if (state.cards.some((c) => c.id === a.card.id && c.kind === a.card.kind)) return state
      return { ...state, cards: [...state.cards, a.card] }
    }
    default:
      return state
  }
}

// Map a server event (call-scoped) onto a reducer action; returns null if irrelevant.
export function actionFromEvent(ev) {
  const d = ev.data || {}
  switch (ev.type) {
    case 'transcript.partial':
      return { type: 'transcript', id: null, role: d.role, text: d.text, final: false }
    case 'transcript.final':
      return { type: 'transcript', id: ev.id, role: d.role, text: d.text, final: true }
    case 'agent.speaking':
      return { type: 'speaking', who: 'agent', value: !!d.speaking }
    case 'caller.speaking':
      return { type: 'speaking', who: 'caller', value: !!d.speaking }
    case 'tool.started':
      return { type: 'tool', name: d.name }
    case 'tool.finished':
      return { type: 'tool', name: null }
    case 'appointment.created':
      return d.appointment ? { type: 'card', card: { kind: 'booked', id: d.appointment.id, appointment: d.appointment } } : null
    case 'appointment.cancelled':
      return d.appointment ? { type: 'card', card: { kind: 'cancelled', id: d.appointment.id, appointment: d.appointment } } : null
    default:
      return null
  }
}
