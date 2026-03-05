import { useState } from 'react'

interface Props {
  onSubmitted: (goalId: string) => void
}

export default function GoalForm({ onSubmitted }: Props) {
  const [goal, setGoal] = useState('')
  const [agentCount, setAgentCount] = useState(2)
  const [caps, setCaps] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit() {
    if (!goal.trim() || loading) return
    setLoading(true)
    try {
      const capabilities = caps.trim()
        ? caps.split(',').map(s => s.trim()).filter(Boolean)
        : []
      const res = await fetch('/goal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal.trim(), agent_count: agentCount, capabilities }),
      })
      const data = await res.json()
      onSubmitted(data.goal_id ?? '')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-slate-900/60 rounded-xl border border-slate-700/60 p-4 space-y-3">
      <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Submit Goal</h2>

      <textarea
        rows={4}
        value={goal}
        onChange={e => setGoal(e.target.value)}
        placeholder="Describe what you want the agents to accomplish..."
        className="w-full bg-slate-800/80 border border-slate-600/50 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:border-blue-500/70"
        onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) submit() }}
      />

      <div className="flex items-center gap-2">
        <label className="text-xs text-slate-500 whitespace-nowrap">Agents:</label>
        <input
          type="number" min={1} max={8} value={agentCount}
          onChange={e => setAgentCount(Number(e.target.value))}
          className="w-16 bg-slate-800/80 border border-slate-600/50 rounded px-2 py-1 text-sm text-center text-slate-200 focus:outline-none focus:border-blue-500/70"
        />
        <button
          onClick={submit}
          disabled={loading || !goal.trim()}
          className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium py-1.5 rounded-lg transition-colors"
        >
          {loading ? 'Decomposing…' : 'Run'}
        </button>
      </div>

      <div>
        <label className="text-xs text-slate-500">Capabilities (comma-separated, optional):</label>
        <input
          type="text" value={caps}
          onChange={e => setCaps(e.target.value)}
          placeholder="e.g. code, search, write"
          className="w-full mt-1 bg-slate-800/80 border border-slate-600/50 rounded px-2 py-1 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-blue-500/70"
        />
      </div>
    </div>
  )
}
