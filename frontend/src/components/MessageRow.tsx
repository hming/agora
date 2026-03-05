import { useState } from 'react'
import type { AgoraMessage, MessageType } from '../types'

const STYLE: Record<MessageType, { color: string; bg: string; icon: string }> = {
  GOAL_RECEIVED:    { color: 'text-purple-400',  bg: 'bg-purple-900/20',  icon: '◎' },
  GOAL_DECOMPOSED:  { color: 'text-violet-400',  bg: 'bg-violet-900/20',  icon: '⬡' },
  GOAL_COMPLETED:   { color: 'text-green-300',   bg: 'bg-green-900/30',   icon: '★' },
  TASK_CLAIMED:     { color: 'text-blue-400',    bg: 'bg-blue-900/20',    icon: '⟳' },
  TASK_DONE:        { color: 'text-green-400',   bg: 'bg-green-900/20',   icon: '✓' },
  TASK_FAILED:      { color: 'text-red-400',     bg: 'bg-red-900/20',     icon: '✗' },
  TASK_UNBLOCKED:   { color: 'text-cyan-400',    bg: 'bg-cyan-900/15',    icon: '⬆' },
  AGENT_JOINED:     { color: 'text-emerald-400', bg: 'bg-emerald-900/15', icon: '↗' },
  AGENT_LEFT:       { color: 'text-slate-500',   bg: 'bg-slate-800/30',   icon: '↙' },
  EPOCH_START:      { color: 'text-yellow-300',  bg: 'bg-yellow-900/10',  icon: '◈' },
  STATE_PUBLISH:    { color: 'text-amber-400',   bg: 'bg-amber-900/15',   icon: '~' },
  ACK:              { color: 'text-slate-600',   bg: 'bg-slate-800/20',   icon: '·' },
  LEADER_ELECTED:   { color: 'text-amber-300',   bg: 'bg-amber-900/20',   icon: '👑' },
  VOTE_REQUEST:     { color: 'text-indigo-400',  bg: 'bg-indigo-900/20',  icon: '?' },
  VOTE:             { color: 'text-indigo-300',  bg: 'bg-indigo-900/15',  icon: '✔' },
  CONSENSUS_REACHED:{ color: 'text-green-300',   bg: 'bg-green-900/25',   icon: '⚑' },
  CONSENSUS_FAILED: { color: 'text-red-300',     bg: 'bg-red-900/20',     icon: '⊘' },
  GOAL_FAILED:      { color: 'text-red-300',     bg: 'bg-red-900/25',     icon: '✗' },
}

function formatSummary(type: MessageType, p: Record<string, unknown>): string {
  const s = (v: unknown) => String(v ?? '')
  switch (type) {
    case 'GOAL_RECEIVED':     return s(p.goal)
    case 'GOAL_DECOMPOSED':   return `${(p.tasks as unknown[])?.length ?? 0} tasks`
    case 'GOAL_COMPLETED':    return `✓ ${s(p.goal)}  (${s(p.total_tasks)} tasks)`
    case 'TASK_CLAIMED':      return `[${s(p.task_id)}] ${s(p.description).slice(0, 80)}`
    case 'TASK_DONE':         return `[${s(p.task_id)}] ${s(p.result).slice(0, 100)}`
    case 'TASK_FAILED': {
      const retry = p.retry_count != null ? `  (attempt ${s(p.retry_count)})` : ''
      return `[${s(p.task_id)}] ${s(p.error)}${retry}`
    }
    case 'TASK_UNBLOCKED':    return `[${s(p.task_id)}] → ${s(p.description).slice(0, 60)}`
    case 'AGENT_JOINED':      return s(p.agent_id)
    case 'AGENT_LEFT':        return `${s(p.agent_id)}${p.reason ? ` (${s(p.reason)})` : ''}`
    case 'EPOCH_START':       return `epoch ${s(p.epoch)}  ·  ${(p.agents as string[])?.length ?? 0} agents`
    case 'STATE_PUBLISH':     return `epoch ${s(p.epoch)}  ·  peers: ${((p.peers as string[]) ?? []).map(x => x.replace('agent-','')).join(', ') || '—'}`
    case 'ACK':               return `epoch ${s(p.epoch)}  →  ${s(p.ack_target).replace('agent-','')}`
    case 'LEADER_ELECTED':    return `leader: ${s(p.leader).replace('agent-','')}  ·  epoch ${s(p.epoch)}`
    case 'VOTE_REQUEST':      return `[${s(p.proposal_id)}] ${s(p.topic)}: "${s(p.value)}"  threshold=${s(p.threshold)}`
    case 'VOTE':              return `[${s(p.proposal_id)}] ${p.approve ? '✔ approve' : '✘ reject'}`
    case 'CONSENSUS_REACHED': return `[${s(p.proposal_id)}] ✔ ${s(p.topic)}="${s(p.value)}"  (${s(p.votes_for)} for)`
    case 'CONSENSUS_FAILED':  return `[${s(p.proposal_id)}] ✘ ${s(p.topic)}`
    case 'GOAL_FAILED':       return `✗ ${s(p.goal)}  (failed on ${s(p.failed_task)})`
  }
}

interface Props { msg: AgoraMessage }

export default function MessageRow({ msg }: Props) {
  const [expanded, setExpanded] = useState(false)
  const p = msg.payload
  const style = STYLE[msg.type] ?? { color: 'text-slate-400', bg: 'bg-slate-800/30', icon: '·' }
  const ts = new Date(msg.ts * 1000).toLocaleTimeString('zh', { hour12: false })
  const agentShort = (msg.agent_id ?? '').replace('agent-', '')
  const hasDetail = msg.type === 'TASK_DONE' || msg.type === 'GOAL_DECOMPOSED'

  // EPOCH_START as divider
  if (msg.type === 'EPOCH_START') {
    return (
      <div className="msg-enter flex items-center gap-2 my-2 px-2">
        <div className="flex-1 h-px bg-yellow-900/40" />
        <span className="text-yellow-300/70 text-[10px] font-bold tracking-widest uppercase px-2">
          ◈ Epoch {p.epoch as number}
        </span>
        <div className="flex-1 h-px bg-yellow-900/40" />
      </div>
    )
  }

  // GOAL_FAILED as banner
  if (msg.type === 'GOAL_FAILED') {
    return (
      <div className="msg-enter my-3 mx-2 px-4 py-3 rounded-xl bg-red-900/30 border border-red-500/40">
        <div className="flex items-center gap-2 text-red-300 font-bold text-sm mb-1">
          <span>✗ 目标失败</span>
          <span className="text-red-500/60 text-xs font-normal">{p.goal_id as string}</span>
        </div>
        <div className="text-red-200/80 text-xs leading-relaxed">{p.goal as string}</div>
        <div className="text-red-500/60 text-[10px] mt-1">任务 {p.failed_task as string} 重试耗尽</div>
      </div>
    )
  }

  // GOAL_COMPLETED as banner
  if (msg.type === 'GOAL_COMPLETED') {
    return (
      <div className="msg-enter my-3 mx-2 px-4 py-3 rounded-xl bg-green-900/40 border border-green-500/40">
        <div className="flex items-center gap-2 text-green-300 font-bold text-sm mb-1">
          <span>★ 目标完成</span>
          <span className="text-green-500/60 text-xs font-normal">{p.goal_id as string}</span>
        </div>
        <div className="text-green-200/80 text-xs leading-relaxed">{p.goal as string}</div>
        <div className="text-green-500/60 text-[10px] mt-1">{p.total_tasks as string} 个任务全部完成</div>
      </div>
    )
  }

  return (
    <div
      className={`msg-enter px-2 py-1 rounded ${style.bg} ${hasDetail ? 'cursor-pointer' : ''}`}
      onClick={() => hasDetail && setExpanded(x => !x)}
    >
      <div className="flex items-start gap-2">
        <span className="text-slate-600 select-none w-16 flex-shrink-0 text-[11px]">{ts}</span>
        <span className={`${style.color} font-bold w-4 flex-shrink-0 text-center select-none`}>{style.icon}</span>
        <span className="text-slate-500 w-20 flex-shrink-0 truncate text-[11px]">{agentShort}</span>
        <span className={`${style.color} w-28 flex-shrink-0 text-[10px] uppercase tracking-wide`}>{msg.type}</span>
        <span className="text-slate-300 flex-1 min-w-0 break-words leading-relaxed text-[11px]">
          {formatSummary(msg.type, p)}
        </span>
        {hasDetail && (
          <span className="text-slate-600 text-[10px] flex-shrink-0">{expanded ? '▲' : '▼'}</span>
        )}
      </div>

      {expanded && msg.type === 'TASK_DONE' && (
        <div className="mt-1.5 ml-[140px] text-slate-400 text-[11px] whitespace-pre-wrap bg-slate-800/60 rounded p-2 border border-slate-700/40">
          {p.result as string}
        </div>
      )}

      {expanded && msg.type === 'GOAL_DECOMPOSED' && (
        <div className="mt-1.5 ml-[140px] space-y-1">
          {((p.tasks as Array<{ id: string; description: string; depends_on: string[] }>) ?? []).map(t => (
            <div key={t.id} className="text-[11px] text-slate-400 bg-slate-800/60 rounded px-2 py-1 border border-slate-700/40">
              <span className="text-blue-400 font-mono mr-2">{t.id}</span>
              {t.description}
              {t.depends_on.length > 0 && (
                <span className="text-slate-600 ml-2">← {t.depends_on.join(', ')}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
