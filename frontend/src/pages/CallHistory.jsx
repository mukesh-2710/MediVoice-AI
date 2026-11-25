import React, { useState } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { api } from '../lib/api.js'
import { useFetch } from '../lib/useFetch.js'
import { formatDuration, timeAgo } from '../lib/format.js'
import Icon from '../components/Icon.jsx'
import { Empty, Skeleton } from '../components/ui.jsx'

const REASON = { caller_hangup: 'Caller hung up', silence_timeout: 'Ended after silence', pipeline_error: 'Technical error', server_restart: 'Server restarted', completed: 'Completed' }
const dur = (c) => (c.connected_at && c.ended_at ? formatDuration((new Date(c.ended_at) - new Date(c.connected_at)) / 1000) : '–')

export default function CallHistory() {
  const { state } = useApp()
  const [sel, setSel] = useState(null)
  const calls = state.calls
  const id = sel || calls[0]?.id
  const tx = useFetch(() => (id ? api.transcript(id) : Promise.resolve([])), [id, state.refreshTick])
  if (!state.loaded) return <Skeleton h={300} />
  if (!calls.length) return <section className="panel"><Empty title="No calls yet">Completed calls and their transcripts are kept here.</Empty></section>
  return (
    <div className="split-view">
      <section className="panel" style={{ padding: 8 }}>
        {calls.map((c) => (
          <button key={c.id} className="call-item" aria-current={c.id === id} onClick={() => setSel(c.id)}>
            <b style={{ fontWeight: 500 }}>{timeAgo(c.started_at)}</b>
            <div className="muted" style={{ fontSize: 13 }}>{c.state === 'ended' ? `${dur(c)} · ${REASON[c.end_reason] || c.end_reason || 'Ended'}` : 'In progress'} · {c.message_count} lines</div>
            {c.verified_phone && <div className="faint mono" style={{ fontSize: 12.5 }}>verified {c.verified_phone.slice(0, 2)}•••••{c.verified_phone.slice(-3)}</div>}
          </button>
        ))}
      </section>
      <section className="panel">
        <header><h2>Transcript</h2>{id && tx.data?.length > 0 && <a className="btn small" href={api.transcriptUrl(id)} download><Icon name="download" size={15} /> Download</a>}</header>
        {tx.loading && !tx.data ? <Skeleton h={120} /> : !tx.data?.length ? <Empty title="No transcript">Nothing was said on this call.</Empty>
          : tx.data.map((m) => (<div className="tline" key={m.id}><span className={`r ${m.role === 'user' ? 'you' : 'agent'}`}>{m.role === 'user' ? 'Caller' : 'Agent'}</span><span>{m.text}</span></div>))}
      </section>
    </div>
  )
}
