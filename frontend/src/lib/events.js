// WebSocket client with automatic reconnect (exponential backoff), heartbeat and call re-subscription.

export class RealtimeClient {
  constructor({ url, onEvent, onStatus, onOpen }) {
    this.url = url
    this.onEvent = onEvent
    this.onStatus = onStatus
    this.onOpen = onOpen
    this.ws = null
    this.attempt = 0
    this.closed = false
    this.callId = null
    this.timer = null
    this.ping = null
    this.everOpened = false
  }

  connect() {
    this.closed = false
    this._open()
  }

  _open() {
    clearTimeout(this.timer)
    this.onStatus(this.everOpened ? 'reconnecting' : 'connecting')
    let ws
    try {
      ws = new WebSocket(this.url)
    } catch {
      return this._retry()
    }
    this.ws = ws
    ws.onopen = () => {
      this.attempt = 0
      this.everOpened = true
      this.onStatus('live')
      if (this.callId) this._send({ type: 'subscribe', call_id: this.callId })
      this.ping = setInterval(() => this._send({ type: 'ping' }), 20000)
      this.onOpen?.() // caller re-syncs from the database snapshot
    }
    ws.onmessage = (m) => {
      try {
        this.onEvent(JSON.parse(m.data))
      } catch {
        /* ignore malformed frames */
      }
    }
    ws.onclose = () => {
      clearInterval(this.ping)
      if (!this.closed) this._retry()
    }
    ws.onerror = () => ws.close()
  }

  _retry() {
    this.attempt += 1
    this.onStatus(this.attempt > 6 ? 'offline' : 'reconnecting')
    const delay = Math.min(10000, 500 * 2 ** Math.min(this.attempt, 5))
    this.timer = setTimeout(() => this._open(), delay)
  }

  _send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj))
  }

  subscribeCall(callId) {
    this.callId = callId
    if (callId) this._send({ type: 'subscribe', call_id: callId })
  }

  close() {
    this.closed = true
    clearTimeout(this.timer)
    clearInterval(this.ping)
    this.ws?.close()
  }
}

export function wsUrl() {
  const explicit = import.meta.env?.VITE_WS_URL
  if (explicit) return explicit
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/ws/events`
}
