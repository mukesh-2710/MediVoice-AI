import React from 'react'

const P = {
  overview: 'M4 5h7v7H4zM13 5h7v4h-7zM13 11h7v8h-7zM4 14h7v5H4z',
  voice: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4',
  doctors: 'M9 3v5a3 3 0 0 0 6 0V3M12 11v3a4 4 0 0 0 8 0v-1M20 13a1.5 1.5 0 1 0 0 .01',
  calendar: 'M5 6h14v14H5zM5 10h14M9 3v4M15 3v4',
  list: 'M8 7h12M8 12h12M8 17h12M4 7h.01M4 12h.01M4 17h.01',
  history: 'M4 12a8 8 0 1 0 3-6.2M4 4v4h4M12 8v4l3 2',
  pulse: 'M3 12h4l2.5-6 4 12 2.5-6H21',
  gear: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19 12l2-1-1-3-2.2.4a7 7 0 0 0-1.6-1L15.5 5h-3l-.7 2.4a7 7 0 0 0-1.6 1L8 8l-1 3 2 1a7 7 0 0 0 0 2l-2 1 1 3 2.2-.4a7 7 0 0 0 1.6 1l.7 2.4h3l.7-2.4a7 7 0 0 0 1.6-1L19 19l1-3-2-1a7 7 0 0 0 .1-1.5z',
  phone: 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A15 15 0 0 1 3 6a2 2 0 0 1 2-2z',
  hangup: 'M3 14c5-4 13-4 18 0l-1.5 3-4-1.5v-2.5a10 10 0 0 0-7 0V15.5L4.5 17z',
  mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4',
  micoff: 'M4 4l16 16M9 6a3 3 0 0 1 6 0v5M15 14a3 3 0 0 1-5.5 1.6M6 11a6 6 0 0 0 9 5.2M12 17v4',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6L6 18',
  download: 'M12 4v11M7.5 11L12 15.5 16.5 11M5 20h14',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
  alert: 'M12 4l9 16H3zM12 10v4M12 17h.01',
}

export default function Icon({ name, size = 18, stroke = 1.8 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={P[name]} />
    </svg>
  )
}

export function Logo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#14233f" stroke="rgba(148,172,214,.3)" />
      <path d="M6 17h4l3-7 4 13 3-9 2 3h4" fill="none" stroke="#38D5E8" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
