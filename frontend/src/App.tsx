import { useState } from 'react'
import { useAgora } from './hooks/useAgora'
import GoalForm from './components/GoalForm'
import AgentPanel from './components/AgentPanel'
import ArbitrationPanel from './components/ArbitrationPanel'
import MessageLog from './components/MessageLog'

export default function App() {
  const { messages, agents, leader, proposals, stats, connected, reset } = useAgora()
  const [lastGoalId, setLastGoalId] = useState<string | null>(null)

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-slate-950">
      {/* Top bar */}
      <header className="flex items-center gap-4 px-5 py-3 border-b border-slate-800/80 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded bg-blue-600/80 flex items-center justify-center text-xs font-bold">A</div>
          <span className="font-semibold text-slate-200 tracking-tight">AGORA</span>
          <span className="text-slate-600 text-xs">去中心化多 Agent 协调</span>
        </div>

        {/* Stats */}
        <div className="ml-auto flex items-center gap-5 text-xs">
          <Stat label="Claimed" value={stats.claimed} color="text-blue-400" />
          <Stat label="Done"    value={stats.done}    color="text-green-400" />
          <Stat label="Failed"  value={stats.failed}  color="text-red-400" />
          {lastGoalId && (
            <span className="text-slate-600 font-mono">{lastGoalId}</span>
          )}
        </div>
      </header>

      {/* Main layout */}
      <div className="flex flex-1 min-h-0 gap-4 p-4">
        {/* Left sidebar */}
        <div className="w-72 flex-shrink-0 flex flex-col gap-4">
          <GoalForm onSubmitted={id => setLastGoalId(id)} />
          <AgentPanel agents={agents} leader={leader} />
          <ArbitrationPanel leader={leader} proposals={proposals} />
        </div>

        {/* Message log */}
        <MessageLog messages={messages} connected={connected} onReset={reset} />
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-slate-600">{label}</span>
      <span className={`font-mono font-medium ${color}`}>{value}</span>
    </div>
  )
}
