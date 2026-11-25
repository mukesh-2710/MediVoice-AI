// Ring and end-call tones synthesised with Web Audio (no audio files to ship).
let ctx = null
let ringTimer = null

function audio() {
  ctx = ctx || new (window.AudioContext || window.webkitAudioContext)()
  if (ctx.state === 'suspended') ctx.resume()
  return ctx
}

function tone(freqs, start, dur, gain = 0.06) {
  const c = audio()
  const g = c.createGain()
  g.gain.setValueAtTime(0, start)
  g.gain.linearRampToValueAtTime(gain, start + 0.02)
  g.gain.setValueAtTime(gain, start + dur - 0.04)
  g.gain.linearRampToValueAtTime(0, start + dur)
  g.connect(c.destination)
  freqs.forEach((f) => {
    const o = c.createOscillator()
    o.type = 'sine'
    o.frequency.value = f
    o.connect(g)
    o.start(start)
    o.stop(start + dur + 0.02)
  })
}

export function startRing() {
  try {
    const burst = () => tone([440, 480], audio().currentTime, 0.9)
    burst()
    ringTimer = setInterval(burst, 2200)
  } catch {
    /* audio unavailable: silent ring */
  }
}

export function stopRing() {
  clearInterval(ringTimer)
  ringTimer = null
}

export function playConnected() {
  try {
    const t = audio().currentTime
    tone([660], t, 0.12, 0.05)
    tone([880], t + 0.14, 0.16, 0.05)
  } catch {
    /* ignore */
  }
}

export function playEnd() {
  try {
    const t = audio().currentTime
    tone([480, 620], t, 0.22)
    tone([350, 440], t + 0.26, 0.3)
  } catch {
    /* ignore */
  }
}
