export type MessageType =
  | 'GOAL_RECEIVED' | 'GOAL_DECOMPOSED' | 'GOAL_COMPLETED' | 'GOAL_FAILED'
  | 'TASK_CLAIMED'  | 'TASK_DONE'       | 'TASK_FAILED' | 'TASK_UNBLOCKED'
  | 'AGENT_JOINED'  | 'AGENT_LEFT'
  | 'EPOCH_START'   | 'STATE_PUBLISH'   | 'ACK'
  | 'LEADER_ELECTED'
  | 'VOTE_REQUEST'  | 'VOTE'            | 'CONSENSUS_REACHED' | 'CONSENSUS_FAILED'

export interface AgoraMessage {
  id: string
  epoch: number
  agent_id: string
  type: MessageType
  payload: Record<string, unknown>
  ts: number
}

export interface AgentRecord {
  agent_id: string
  status: 'running' | 'stopped'
  capabilities: string[]
  current_task: string | null
  epoch: number
}

export interface Stats {
  claimed: number
  done: number
  failed: number
}

export interface Proposal {
  id: string
  topic: string
  value: string
  proposer: string
  votes_for: number
  votes_against: number
  threshold: number
  status: 'open' | 'passed' | 'failed'
}
