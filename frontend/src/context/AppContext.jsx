import React, { createContext, useCallback, useContext, useEffect, useReducer, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { RealtimeClient, wsUrl } from '../lib/events.js'
import { initialState, reducer } from '../lib/store.js'
import { actionFromEvent, callReducer, initialCall, isCallActive } from '../lib/callMachine.js'
import { VoiceCall } from '../lib/voiceCall.js'
import { playConnected, playEnd, startRing, stopRing } from '../lib/sounds.js'

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const MIN_RING_MS = 1700
const CONNECT_TIMEOUT_MS = 20000

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [call, callDispatch] = useReducer(callReducer, initialCall)
  const [loadError, setLoadError] = useState(null)
  const [playbackBlocked, setPlaybackBlocked] = useState(false)
  const audioRef = useRef(null)
  const voice = useRef(null)
  const rt = useRef(null)
  const callIdRef = useRef(null)
  const phaseRef = useRef('idle')
  phaseRef.current = call.phase

  // ---- database-backed (re)sync
  const resync = useCallback(async () => {
    try {
      const snap = await api.state()
      dispatch({ type: 'snapshot', payload: snap })
      setLoadError(null)
    } catch (e) {
      setLoadError(e.message)
    }
  }, [])

  // ---- realtime socket
  useEffect(() => {
    const client = new RealtimeClient({
      url: wsUrl(),
      onStatus: (status) => dispatch({ type: 'connection', status }),
      onOpen: resync,
      onEvent: (ev) => {
        if (ev.type === 'hello' || ev.type === 'pong' || ev.type === 'subscribed' || ev.type === 'subscribe.rejected') return
        dispatch({ type: 'event', event: ev })
        if (ev.call_id && ev.call_id === callIdRef.current) {
          const a = actionFromEvent(ev)
          if (a) callDispatch(a)
          if (ev.type === 'call.ended' && isCallActive(phaseRef.current)) finishLocal()
        }
      },
    })
    rt.current = client
    client.connect()
    return () => client.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- refresh derived data after events (debounced)
  useEffect(() => {
    if (!state.refreshTick) return
    const t = setTimeout(async () => {
      try {
        const [stats, activity, calls] = await Promise.all([api.stats(), api.activity(60), api.calls()])
        dispatch({ type: 'snapshot', payload: { stats, activity, calls } })
      } catch {
        /* the socket status banner already tells the user */
      }
    }, 300)
    return () => clearTimeout(t)
  }, [state.refreshTick])

  // ---- clear row highlights
  useEffect(() => {
    const ids = Object.keys(state.flash)
    if (!ids.length) return
    const timers = ids.map((id) => setTimeout(() => dispatch({ type: 'flash-clear', id }), 2800))
    return () => timers.forEach(clearTimeout)
  }, [state.flash])

  // ---- call control
  const cleanup = useCallback(async () => {
    stopRing()
    setPlaybackBlocked(false)
    const v = voice.current
    voice.current = null
    if (v) await v.end()
    rt.current?.subscribeCall(null)
  }, [])

  const finishLocal = useCallback(async () => {
    await cleanup()
    playEnd()
    callDispatch({ type: 'ended' })
    callIdRef.current = null
    resync()
  }, [cleanup, resync])

  const fail = useCallback(async (message) => {
    await cleanup()
    callIdRef.current = null
    callDispatch({ type: 'error', message })
  }, [cleanup])

  const startCall = useCallback(async () => {
    if (isCallActive(phaseRef.current)) return
    callDispatch({ type: 'start' })
    setPlaybackBlocked(false)
    startRing()
    let resolveConnected
    const connected = new Promise((r) => (resolveConnected = r))
    const vc = new VoiceCall({
      audioEl: audioRef.current,
      onConnected: () => resolveConnected(true),
      onFailed: (m) => (phaseRef.current === 'connected' || phaseRef.current === 'connecting') && fail(m),
      onPlaybackBlocked: setPlaybackBlocked,
    })
    voice.current = vc
    try {
      const [callId] = await Promise.all([vc.start(), sleep(MIN_RING_MS)])
      callIdRef.current = callId
      callDispatch({ type: 'call-id', callId })
      rt.current?.subscribeCall(callId)
      stopRing()
      callDispatch({ type: 'connecting' })
      await Promise.race([connected, sleep(CONNECT_TIMEOUT_MS).then(() => Promise.reject(new Error('The call took too long to connect.')))])
      if (voice.current !== vc) return // hung up meanwhile
      playConnected()
      callDispatch({ type: 'connected' })
    } catch (e) {
      if (voice.current === vc || voice.current === null) await fail(e.message || 'Could not start the call.')
    }
  }, [fail])

  const endCall = useCallback(async () => {
    if (!isCallActive(phaseRef.current)) return
    callDispatch({ type: 'ending' })
    await finishLocal()
  }, [finishLocal])

  const toggleMute = useCallback(() => {
    callDispatch({ type: 'mute' })
  }, [])
  useEffect(() => {
    voice.current?.setMuted(call.muted)
  }, [call.muted])

  const dismissCall = useCallback(() => callDispatch({ type: 'reset' }), [])

  // hang up if the tab closes mid-call
  useEffect(() => {
    const h = () => callIdRef.current && api.endCall(callIdRef.current)
    window.addEventListener('pagehide', h)
    return () => window.removeEventListener('pagehide', h)
  }, [])

  const value = {
    state, dispatch, call, loadError, resync, startCall, endCall, toggleMute, dismissCall,
    playbackBlocked, enableAudio: () => voice.current?.playAudio(), voice, audioRef,
  }
  return (
    <Ctx.Provider value={value}>
      {children}
      <audio ref={audioRef} autoPlay playsInline />
    </Ctx.Provider>
  )
}
