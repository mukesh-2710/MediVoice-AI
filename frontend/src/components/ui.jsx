import React from 'react'
import { STATUS_LABEL } from '../lib/format.js'

export const StatusBadge = ({ status }) => <span className={`badge ${status}`}>{STATUS_LABEL[status] || status}</span>

export const Empty = ({ title, children, action }) => (
  <div className="empty">
    <b>{title}</b>
    {children && <span>{children}</span>}
    {action}
  </div>
)

export const Skeleton = ({ h = 16, w = '100%', style }) => <div className="skeleton" style={{ height: h, width: w, ...style }} />

export const Initials = ({ name }) => {
  const t = name.replace(/^Dr\.?\s*/i, '').split(' ').map((p) => p[0]).slice(0, 2).join('')
  return <div className="avatar">{t}</div>
}

export function ErrorBanner({ children, onRetry }) {
  return (
    <div className="banner err" role="alert">
      <span className="grow">{children}</span>
      {onRetry && <button className="btn small" onClick={onRetry}>Retry</button>}
    </div>
  )
}
