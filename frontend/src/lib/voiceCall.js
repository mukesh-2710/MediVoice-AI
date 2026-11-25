// Browser side of the call: microphone -> WebRTC -> Pipecat (SmallWebRTC transport) and back.
// Audio levels for the waveform are read from the REAL local and remote streams via Web Audio analysers.
import { api } from './api.js'

const ICE = [{ urls: 'stun:stun.l.google.com:19302' }]

export class VoiceCall {
  constructor({ audioEl, onConnected, onFailed, onPlaybackBlocked }) {
    this.audioEl = audioEl
    this.onConnected = onConnected
    this.onFailed = onFailed
    this.onPlaybackBlocked = onPlaybackBlocked
    this.pc = null
    this.stream = null
    this.callId = null
    this.ctx = null
    this.inAnalyser = null
    this.outAnalyser = null
    this.buf = null
    this.ended = false
  }

  async start() {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('This browser cannot access the microphone.')
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
    } catch (e) {
      if (e?.name === 'NotAllowedError' || e?.name === 'SecurityError')
        throw new Error('Microphone access is blocked. Allow it in the address bar, then try again.')
      if (e?.name === 'NotFoundError') throw new Error('No microphone was found.')
      throw new Error('Could not start the microphone.')
    }
    this._setupLevels(this.stream, 'in')

    const pc = new RTCPeerConnection({ iceServers: ICE })
    this.pc = pc
    this.stream.getAudioTracks().forEach((t) => pc.addTrack(t, this.stream))
    pc.createDataChannel('chat') // keeps the SmallWebRTC session happy; no app data is sent over it
    pc.ontrack = (e) => {
      const remote = e.streams[0] || new MediaStream([e.track])
      this.audioEl.srcObject = remote
      this.playAudio()
      this._setupLevels(remote, 'out')
    }
    pc.onconnectionstatechange = () => {
      if (this.ended) return
      if (pc.connectionState === 'connected') this.onConnected?.()
      if (pc.connectionState === 'failed') this.onFailed?.('The audio connection was lost.')
      if (pc.connectionState === 'disconnected') {
        // brief network blips recover on their own; give it a few seconds before giving up
        setTimeout(() => {
          if (!this.ended && pc.connectionState !== 'connected') this.onFailed?.('The audio connection was lost.')
        }, 4000)
      }
    }

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    await this._iceComplete(pc)
    const answer = await api.offer(pc.localDescription.sdp, pc.localDescription.type)
    this.callId = answer.call_id
    await pc.setRemoteDescription({ sdp: answer.sdp, type: answer.type })
    return answer.call_id
  }

  _iceComplete(pc, timeout = 2500) {
    if (pc.iceGatheringState === 'complete') return Promise.resolve()
    return new Promise((resolve) => {
      const done = () => {
        pc.removeEventListener('icegatheringstatechange', check)
        clearTimeout(t)
        resolve()
      }
      const check = () => pc.iceGatheringState === 'complete' && done()
      const t = setTimeout(done, timeout)
      pc.addEventListener('icegatheringstatechange', check)
    })
  }

  _setupLevels(stream, which) {
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)()
      const an = this.ctx.createAnalyser()
      an.fftSize = 256
      an.smoothingTimeConstant = 0.75
      this.ctx.createMediaStreamSource(stream).connect(an) // analyser only: not connected to speakers
      if (which === 'in') this.inAnalyser = an
      else this.outAnalyser = an
      this.buf = new Uint8Array(an.frequencyBinCount)
    } catch {
      /* waveform falls back to flat; call still works */
    }
  }

  // Frequency spectrum (0..1) for `bars` bars from the real audio stream.
  spectrum(which, bars) {
    const an = which === 'in' ? this.inAnalyser : this.outAnalyser
    const out = new Array(bars).fill(0)
    if (!an) return out
    const data = new Uint8Array(an.frequencyBinCount)
    an.getByteFrequencyData(data)
    const usable = Math.floor(data.length * 0.7) // voice lives in the lower part of the spectrum
    for (let i = 0; i < bars; i++) {
      const a = Math.floor((i / bars) * usable)
      const b = Math.max(a + 1, Math.floor(((i + 1) / bars) * usable))
      let sum = 0
      for (let j = a; j < b; j++) sum += data[j]
      out[i] = sum / (b - a) / 255
    }
    return out
  }

  level(which) {
    const s = this.spectrum(which, 12)
    return s.reduce((x, y) => x + y, 0) / s.length
  }

  setMuted(muted) {
    this.stream?.getAudioTracks().forEach((t) => (t.enabled = !muted))
  }

  async playAudio() {
    try {
      await this.audioEl?.play()
      this.onPlaybackBlocked?.(false)
      return true
    } catch {
      this.onPlaybackBlocked?.(true)
      return false
    }
  }

  async end() {
    if (this.ended) return
    this.ended = true
    if (this.callId) api.endCall(this.callId)
    this.stream?.getTracks().forEach((t) => t.stop())
    try {
      this.pc?.close()
    } catch {
      /* already closed */
    }
    if (this.audioEl) this.audioEl.srcObject = null
    try {
      await this.ctx?.close()
    } catch {
      /* ignore */
    }
  }
}
