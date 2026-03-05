import { useState } from 'react'
import type { Proposal } from '../types'

interface Props {
  leader: string | null
  proposals: Record<string, Proposal>
}

export default function ArbitrationPanel({ leader, proposals }: Props) {
  const [topic, setTopic] = useState('')
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const leaderShort = (leader ?? '').replace('agent-', '') || '—'
  const list = Object.values(proposals).slice().reverse()

  async function propose() {
    if (!topic.trim() || !value.trim()) return
    setSubmitting(true)
    try {
      await fetch('/arbitration/propose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topic.trim(), value: value.trim() }),
      })
      setTopic('')
      setValue('')
    } finally {
      setSubmitting(false)
    }
  }

  async function vote(proposalId: string, approve: boolean) {
    await fetch('/arbitration/vote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proposal_id: proposalId, approve }),
    })
  }

  return (
    <div className="bg-slate-900/60 rounded-xl border border-slate-700/60 p-4 flex flex-col gap-3">
      <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex-shrink-0">
        Arbitration
      </h2>

      {/* Leader */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-slate-600">Leader</span>
        <span className={`font-mono ${leader ? 'text-amber-300' : 'text-slate-600'}`}>
          {leader ? `👑 ${leaderShort}` : '—'}
        </span>
      </div>

      {/* Propose form */}
      <div className="space-y-1.5">
        <input
          className="w-full bg-slate-800/80 border border-slate-700/60 rounded px-2 py-1 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-indigo-500/60"
          placeholder="Topic (e.g. model)"
          value={topic}
          onChange={e => setTopic(e.target.value)}
        />
        <input
          className="w-full bg-slate-800/80 border border-slate-700/60 rounded px-2 py-1 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-indigo-500/60"
          placeholder="Value (e.g. gpt-4o)"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && propose()}
        />
        <button
          onClick={propose}
          disabled={submitting || !topic.trim() || !value.trim()}
          className="w-full py-1 rounded bg-indigo-600/70 hover:bg-indigo-600 disabled:opacity-40 text-xs text-indigo-100 transition-colors"
        >
          Propose
        </button>
      </div>

      {/* Proposals */}
      {list.length > 0 && (
        <div className="space-y-1.5 max-h-48 overflow-y-auto">
          {list.map(p => (
            <ProposalCard key={p.id} proposal={p} onVote={vote} />
          ))}
        </div>
      )}
    </div>
  )
}

function ProposalCard({ proposal: p, onVote }: { proposal: Proposal; onVote: (id: string, approve: boolean) => void }) {
  const total = p.votes_for + p.votes_against
  const pct = total > 0 ? Math.round((p.votes_for / total) * 100) : 0
  const statusColor =
    p.status === 'passed' ? 'text-green-400 border-green-700/40' :
    p.status === 'failed' ? 'text-red-400 border-red-700/40' :
    'text-indigo-300 border-indigo-700/40'

  return (
    <div className={`rounded border px-2 py-1.5 space-y-1 text-[11px] bg-slate-800/50 ${statusColor}`}>
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-slate-500 font-mono">{p.id.slice(-6)}</span>
        <span className="text-slate-400 font-semibold">{p.topic}</span>
        <span className="text-slate-300">= "{p.value}"</span>
        {p.status !== 'open' && (
          <span className={`ml-auto text-[10px] font-bold uppercase ${p.status === 'passed' ? 'text-green-400' : 'text-red-400'}`}>
            {p.status === 'passed' ? '✔ passed' : '✘ failed'}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <div className="flex-1 h-1 bg-slate-700 rounded overflow-hidden">
          <div className="h-full bg-green-500/70 rounded" style={{ width: `${pct}%` }} />
        </div>
        <span className="text-slate-500">{p.votes_for}/{p.threshold}</span>
      </div>

      {p.status === 'open' && (
        <div className="flex gap-1.5 pt-0.5">
          <button
            onClick={() => onVote(p.id, true)}
            className="flex-1 py-0.5 rounded bg-green-700/40 hover:bg-green-700/70 text-green-300 text-[10px] transition-colors"
          >
            ✔ Approve
          </button>
          <button
            onClick={() => onVote(p.id, false)}
            className="flex-1 py-0.5 rounded bg-red-700/40 hover:bg-red-700/70 text-red-300 text-[10px] transition-colors"
          >
            ✘ Reject
          </button>
        </div>
      )}
    </div>
  )
}
