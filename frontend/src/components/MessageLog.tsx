import { useEffect, useRef, useState } from 'react'
import type { AgoraMessage, MessageType } from '../types'
import MessageRow from './MessageRow'

const FILTER_OPTIONS: { label: string; types: MessageType[] | 'all' }[] = [
  { label: 'All',   types: 'all' },
  { label: 'Tasks', types: ['TASK_CLAIMED', 'TASK_DONE', 'TASK_FAILED', 'TASK_UNBLOCKED'] },
  { label: 'Goals', types: ['GOAL_RECEIVED', 'GOAL_DECOMPOSED', 'GOAL_COMPLETED', 'GOAL_FAILED'] },
  { label: 'Epoch', types: ['EPOCH_START', 'STATE_PUBLISH', 'ACK'] },
  { label: 'Arb',   types: ['LEADER_ELECTED', 'VOTE_REQUEST', 'VOTE', 'CONSENSUS_REACHED', 'CONSENSUS_FAILED'] },
]

interface Props {
  messages: AgoraMessage[]
  connected: boolean
  onReset: () => void
}

export default function MessageLog({ messages, connected, onReset }: Props) {
  const [filter, setFilter] = useState<number>(0)
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const visible = filter === 0
    ? messages
    : messages.filter(m => (FILTER_OPTIONS[filter].types as MessageType[]).includes(m.type))

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [visible.length, autoScroll])

  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    setAutoScroll(atBottom)
  }

  return (
    <div className="flex-1 flex flex-col bg-slate-900/40 rounded-xl border border-slate-700/60 min-h-0">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-700/60 flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'}`} />
          <span className="text-xs text-slate-500">{connected ? 'live' : 'disconnected'}</span>
        </div>

        <span className="text-xs text-slate-600">{messages.length} msgs</span>

        {/* Filter tabs */}
        <div className="flex gap-1 ml-2">
          {FILTER_OPTIONS.map((opt, i) => (
            <button
              key={opt.label}
              onClick={() => setFilter(i)}
              className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                filter === i
                  ? 'bg-blue-600/70 text-white'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-slate-500 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={e => setAutoScroll(e.target.checked)}
              className="accent-blue-500"
            />
            Auto-scroll
          </label>
          <button
            onClick={onReset}
            className="text-xs text-slate-600 hover:text-red-400 transition-colors"
          >
            Reset
          </button>
        </div>
      </div>

      {/* Log */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 space-y-0.5 font-mono text-xs"
      >
        {visible.length === 0 ? (
          <p className="text-slate-700 italic text-center mt-8">No messages yet</p>
        ) : (
          visible.map(msg => <MessageRow key={msg.id || `${msg.ts}-${msg.type}`} msg={msg} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
