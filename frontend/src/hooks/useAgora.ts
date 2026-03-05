import { useEffect, useRef, useState, useCallback } from 'react'
import type { AgoraMessage, AgentRecord, Stats, Proposal } from '../types'

const WS_URL = `ws://${window.location.host}/ws`

export function useAgora() {
  const [messages, setMessages] = useState<AgoraMessage[]>([])
  const [agents, setAgents] = useState<Record<string, AgentRecord>>({})
  const [leader, setLeader] = useState<string | null>(null)
  const [proposals, setProposals] = useState<Record<string, Proposal>>({})
  const [stats, setStats] = useState<Stats>({ claimed: 0, done: 0, failed: 0 })
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  const handleMessage = useCallback((msg: AgoraMessage) => {
    setMessages(prev => [...prev, msg])

    const p = msg.payload

    switch (msg.type) {
      case 'AGENT_JOINED':
        setAgents(prev => ({
          ...prev,
          [msg.agent_id]: {
            agent_id: msg.agent_id,
            status: 'running',
            capabilities: (p.capabilities as string[]) ?? [],
            current_task: null,
            epoch: msg.epoch,
          },
        }))
        break

      case 'AGENT_LEFT':
        setAgents(prev => ({
          ...prev,
          [msg.agent_id]: { ...prev[msg.agent_id], status: 'stopped', current_task: null },
        }))
        break

      case 'TASK_CLAIMED':
        setStats(s => ({ ...s, claimed: s.claimed + 1 }))
        setAgents(prev => ({
          ...prev,
          [msg.agent_id]: { ...prev[msg.agent_id], current_task: p.task_id as string },
        }))
        break

      case 'TASK_DONE':
        setStats(s => ({ ...s, done: s.done + 1 }))
        setAgents(prev => ({
          ...prev,
          [msg.agent_id]: { ...prev[msg.agent_id], current_task: null },
        }))
        break

      case 'TASK_FAILED':
        setStats(s => ({ ...s, failed: s.failed + 1 }))
        setAgents(prev => ({
          ...prev,
          [msg.agent_id]: { ...prev[msg.agent_id], current_task: null },
        }))
        break

      case 'EPOCH_START':
        setAgents(prev => {
          const next = { ...prev }
          const active = (p.agents as string[]) ?? []
          active.forEach(id => {
            if (next[id]) next[id] = { ...next[id], epoch: p.epoch as number }
          })
          return next
        })
        break

      case 'LEADER_ELECTED':
        setLeader(p.leader as string ?? null)
        break

      case 'VOTE_REQUEST':
        setProposals(prev => ({
          ...prev,
          [p.proposal_id as string]: {
            id: p.proposal_id as string,
            topic: p.topic as string,
            value: p.value as string,
            proposer: p.proposer as string,
            votes_for: 0,
            votes_against: 0,
            threshold: p.threshold as number,
            status: 'open',
          },
        }))
        break

      case 'VOTE':
        setProposals(prev => {
          const prop = prev[p.proposal_id as string]
          if (!prop) return prev
          return {
            ...prev,
            [p.proposal_id as string]: {
              ...prop,
              votes_for: prop.votes_for + (p.approve ? 1 : 0),
              votes_against: prop.votes_against + (p.approve ? 0 : 1),
            },
          }
        })
        break

      case 'CONSENSUS_REACHED':
        setProposals(prev => {
          const prop = prev[p.proposal_id as string]
          if (!prop) return prev
          return { ...prev, [p.proposal_id as string]: { ...prop, status: 'passed' } }
        })
        break

      case 'CONSENSUS_FAILED':
        setProposals(prev => {
          const prop = prev[p.proposal_id as string]
          if (!prop) return prev
          return { ...prev, [p.proposal_id as string]: { ...prop, status: 'failed' } }
        })
        break
    }
  }, [])

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        reconnectTimer = setTimeout(connect, 2000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = e => {
        try { handleMessage(JSON.parse(e.data) as AgoraMessage) }
        catch { /* ignore malformed */ }
      }
    }

    connect()
    return () => {
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [handleMessage])

  const reset = useCallback(async () => {
    await fetch('/reset', { method: 'DELETE' })
    setMessages([])
    setAgents({})
    setLeader(null)
    setProposals({})
    setStats({ claimed: 0, done: 0, failed: 0 })
  }, [])

  return { messages, agents, leader, proposals, stats, connected, reset }
}
