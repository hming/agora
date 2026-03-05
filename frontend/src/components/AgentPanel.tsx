import type { AgentRecord } from '../types'

interface Props {
  agents: Record<string, AgentRecord>
  leader: string | null
}

export default function AgentPanel({ agents, leader }: Props) {
  const list = Object.values(agents)

  return (
    <div className="bg-slate-900/60 rounded-xl border border-slate-700/60 p-4 flex flex-col gap-2 flex-1 min-h-0">
      <div className="flex items-center justify-between flex-shrink-0">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Agents</h2>
        <div className="flex items-center gap-2">
          {leader && (
            <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 px-1.5 py-0.5 rounded">
              👑 {leader.replace('agent-', '')}
            </span>
          )}
          <span className="text-xs text-slate-600">{list.length}</span>
        </div>
      </div>

      <div className="overflow-y-auto flex-1 space-y-1.5 text-xs">
        {list.length === 0 ? (
          <p className="text-slate-600 italic">No agents running</p>
        ) : (
          list.map(agent => <AgentCard key={agent.agent_id} agent={agent} isLeader={agent.agent_id === leader} />)
        )}
      </div>
    </div>
  )
}

function AgentCard({ agent, isLeader }: { agent: AgentRecord; isLeader: boolean }) {
  const running = agent.status === 'running'
  const short = (agent.agent_id ?? '').replace('agent-', '').replace('ext-', 'ext/')
  const caps = (agent.capabilities ?? []).join(', ')

  return (
    <div className={`px-2 py-1.5 rounded space-y-0.5 ${isLeader ? 'bg-amber-900/20 border border-amber-700/30' : 'bg-slate-800/50'}`}>
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${running ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
        <span className="text-slate-300 font-medium truncate flex-1">{short}</span>
        {agent.current_task && (
          <span className="text-blue-400/70 text-[10px] truncate max-w-[72px]">
            {agent.current_task.replace('task_', 't')}
          </span>
        )}
        <span className="text-slate-600 text-[10px]">e{agent.epoch}</span>
      </div>
      {caps && <div className="pl-3.5 text-slate-500 text-[10px] truncate">{caps}</div>}
    </div>
  )
}
