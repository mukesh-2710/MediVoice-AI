import React, { useEffect, useRef } from 'react'

// Radial waveform. Outer cyan ring = agent audio (remote stream), inner blue ring = caller microphone.
// Bar lengths come from the live frequency spectrum of the real MediaStreams, not from a canned animation.
const BARS = 56

export default function Radial({ voiceRef, active }) {
  const ref = useRef(null)
  useEffect(() => {
    const canvas = ref.current
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const size = 214
    canvas.width = canvas.height = size * dpr
    const g = canvas.getContext('2d')
    g.scale(dpr, dpr)
    const smoothIn = new Array(BARS).fill(0)
    const smoothOut = new Array(BARS).fill(0)
    let raf
    const draw = () => {
      g.clearRect(0, 0, size, size)
      const v = voiceRef.current
      const inS = v && active ? v.spectrum('in', BARS) : []
      const outS = v && active ? v.spectrum('out', BARS) : []
      const c = size / 2
      g.lineCap = 'round'
      for (let i = 0; i < BARS; i++) {
        smoothIn[i] += ((inS[i] || 0) - smoothIn[i]) * 0.35
        smoothOut[i] += ((outS[i] || 0) - smoothOut[i]) * 0.35
        const a = (i / BARS) * Math.PI * 2 - Math.PI / 2
        const cos = Math.cos(a), sin = Math.sin(a)
        // agent: grows outward
        const lo = 3 + Math.pow(smoothOut[i], 0.8) * 40
        g.strokeStyle = `rgba(56,213,232,${0.35 + Math.min(smoothOut[i] * 1.4, 0.65)})`
        g.lineWidth = 2.6
        g.beginPath(); g.moveTo(c + cos * 58, c + sin * 58); g.lineTo(c + cos * (58 + lo), c + sin * (58 + lo)); g.stroke()
        // caller: grows inward from a thinner ring
        const li = 2 + Math.pow(smoothIn[i], 0.8) * 12
        g.strokeStyle = `rgba(76,141,255,${0.3 + Math.min(smoothIn[i] * 1.6, 0.7)})`
        g.lineWidth = 2
        g.beginPath(); g.moveTo(c + cos * 52, c + sin * 52); g.lineTo(c + cos * (52 - li), c + sin * (52 - li)); g.stroke()
      }
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [voiceRef, active])
  return <canvas ref={ref} aria-hidden="true" />
}
