# AGORA: Decentralized Multi-Agent Coordination System Design

## Positioning: Coordination Infrastructure, Not an Agent Framework

**AGORA is not an agent framework — it is coordination infrastructure for agents.**

| Dimension | Agent Frameworks (LangGraph / AutoGen / CrewAI) | AGORA Infrastructure |
|-----------|--------------------------------------------------|----------------------|
| Core concern | How to build agents | How agents coordinate correctly |
| Agent coupling | Agents defined inside the framework | Agents are external clients, bring their own LLM |
| Central node | Yes (Orchestrator / Supervisor) | None (the square is a log, not a dispatcher) |
| Interoperability | Closed within the framework | Any language, any model |
| Where intelligence lives | Framework layer + agent layer | Pure agent layer — infrastructure contains no LLM |
| Analogy | Rails / Django | Kafka / PostgreSQL |

**Kafka analogy**: Kafka does not care who the producer or consumer is, or what the business meaning of a message is. AGORA does not care what model an agent uses, how it is implemented, or what it is trying to accomplish — it only guarantees coordination correctness.

---

## Core Insight: Coordination Is a Common Knowledge Problem

The central thesis of *Rational Ritual* (Michael Chwe):

> **Coordination failures stem not from a lack of information, but from a lack of common knowledge.**

The difference between **mutual knowledge** and **common knowledge**:

| Level | Meaning |
|-------|---------|
| Mutual knowledge | A knows X, B knows X |
| Common knowledge | A knows X, B knows X, A knows B knows X, B knows A knows X, A knows B knows A knows X… (infinite recursion) |

Gossip protocols produce only mutual knowledge — they cannot produce common knowledge. This is the fundamental reason pure gossip systems fail under coordination pressure.

Chwe's conclusion: **Ritual is the low-cost technology human societies use to produce common knowledge.** Public gathering, observable participation, visible confirmation by all — that is the structure of a ritual.

---

## System Name

**AGORA** (Adaptive Group Orchestration via Ritual Anchors)

Named after the ancient Greek *agora* (αγορά) — the town square where citizens gathered publicly and witnessed events together. Common knowledge is produced in the square, not in private channels.

---

## Architecture Overview

```
  External Agent Processes (user-supplied, any language / model)
┌──────────────────────────────────────────────────────────────┐
│  [Agent A: GPT-4]  [Agent B: Claude]  [Agent C: Llama]  ...  │
│       │  Python SDK        │  Node SDK       │  REST API      │
└───────┼────────────────────┼─────────────────┼───────────────┘
        │   WebSocket / HTTP │                 │
════════╪════════════════════╪═════════════════╪══════════════
        │        AGORA Infrastructure (system boundary)        │
        ▼                    ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    AGORA Protocol Gateway                    │
│         JOIN · CLAIM_TASK · PUBLISH_RESULT · ACK            │
├─────────────────────────────────────────────────────────────┤
│  Agent Registry  │  Task Graph Engine  │  Epoch Scheduler   │
│  (caps + hbeat)  │  (DAG scheduling)   │  (ritual trigger)  │
├─────────────────────────────────────────────────────────────┤
│              Layer 3: Arbitration (rare path)               │
│         Leader Election → Threshold → Consensus             │
├─────────────────────────────────────────────────────────────┤
│              Layer 2: Task Layer                            │
│          Lock/Lease → Capability Routing → Market/Auction   │
├─────────────────────────────────────────────────────────────┤
│              Layer 1: Epoch Rhythm Layer                    │
│        Work Phase (autonomous) → Ritual Phase (sync)        │
├─────────────────────────────────────────────────────────────┤
│       Layer 0: The Square (Common Knowledge Layer)          │
│         Append-Only public log, visible to all agents       │
└─────────────────────────────────────────────────────────────┘
        │  Redis Streams (current implementation)
        │  Kafka / NATS (production scaling options)
```

**System boundary**:
- Inside AGORA: coordination mechanism, log, task scheduling, Epoch, arbitration
- Outside AGORA: agent's LLM choice, agent implementation language, business meaning of goals, task decomposition logic

---

## AGORA Protocol

Agents connect to the square through a standardized protocol that is language- and model-agnostic.

### Connection handshake

```
Client → Server:  JOIN { agent_id, capabilities: ["code", "search", "write"], version: "1.0" }
Server → Client:  WELCOME { epoch: 5, peers: ["agent-abc", "agent-def"] }
```

### Core message types (Agent → Square)

| Message | When | Required fields |
|---------|------|-----------------|
| `JOIN` | Agent startup | `agent_id`, `capabilities` |
| `CLAIM_TASK` | After claiming a task | `task_id` |
| `PUBLISH_RESULT` | Task completed | `task_id`, `result` |
| `REPORT_FAILURE` | Task failed | `task_id`, `error` |
| `STATE_PUBLISH` | Epoch ritual phase | `epoch`, `peers` |
| `ACK` | Acknowledging a peer's state | `epoch`, `ack_target` |
| `LEAVE` | Agent exits | `agent_id` |

### Core message types (Square → Agent)

| Message | When |
|---------|------|
| `TASK_AVAILABLE` | New claimable task, filtered by `capabilities` |
| `TASK_UNBLOCKED` | A dependency completed; task enters ready state |
| `EPOCH_START` | New epoch begins; triggers ritual phase |
| `PEER_UPDATE` | Another agent joined or left |

### Transport layer

- **Current implementation**: WebSocket long connection (JSON)
- **Production options**: NATS JetStream, gRPC bidirectional streaming
- **Task submission**: HTTP REST (`POST /tasks`) accepts Task Graph JSON

---

## Agent Registry

The Agent Registry tracks metadata for all connected agents and supports capability-based task routing.

### Agent record

```json
{
  "agent_id": "agent-abc123",
  "capabilities": ["code_generation", "web_search", "data_analysis"],
  "status": "running",
  "current_task": "task-42",
  "epoch": 7,
  "last_heartbeat": 1709500000
}
```

### Capability routing

Tasks declare required capabilities at definition time:

```json
{
  "id": "task-42",
  "description": "Search and summarize recent papers",
  "required_capabilities": ["web_search"],
  "depends_on": []
}
```

The square only notifies agents that declared matching capabilities in `TASK_AVAILABLE` broadcasts. Tasks with no capability requirement are visible to all agents (backward compatible).

### Heartbeat and failure detection

Agents send a heartbeat every 10 seconds (or via implicit WebSocket keepalive). An agent with no response for 3 heartbeat cycles (30 seconds) is marked `inactive`; its held task leases are released and `AGENT_LEFT` is broadcast to the square.

---

## Application Layer vs. Infrastructure Layer

**The following are application-layer concerns, not part of AGORA core infrastructure:**

| Feature | Application-layer implementation | Notes |
|---------|----------------------------------|-------|
| Goal decomposition | PlannerAgent or user-side agent | Infrastructure accepts a pre-decomposed Task Graph |
| LLM calls | Each agent manages its own | Infrastructure contains no LLM |
| Task result aggregation | Aggregator agent subscribes to Agora log | Infrastructure stores raw results only |
| Business logic | Entirely on the agent side | Infrastructure only cares about coordination correctness |

**Three task submission paths:**

| Path | Method | Use case |
|------|--------|----------|
| Path A | `POST /goal` → internal PlannerAgent auto-decomposes | Quick start, demos |
| Path B | `POST /goal {spawn_planner:false}` → external agent claims decompose task → `POST /tasks` | External LLM does planning |
| Path C | `POST /tasks` directly with a Task Graph | Manual decomposition, programmatic submission |

`GoalDecomposer` is now an internal tool for PlannerAgent; `POST /tasks` is the standard external interface.

---

## Layer 0: The Square (Common Knowledge Layer)

**This is the foundation of the entire system and the most critical design decision.**

The square is a **public, append-only shared log**:
- Any agent's writes are visible to all agents
- The list of readers is itself public (who is listening is known to everyone)
- Agents must publicly ACK messages they receive

Implementation substrate can be: Kafka topic, Redis Streams, shared database event log.

**Why does this produce common knowledge?**

```
Agent A publishes state S to the square
→ Agent B receives S, publicly ACKs on the square
→ Agent C receives S, publicly ACKs on the square
→ Agent A sees all ACKs
→ Agent B sees A's and C's ACKs
→ Infinite recursive closure: common knowledge achieved
```

This is precisely the ritual structure Chwe describes: **public venue + observable participation + confirmation visible to all**.

---

## Layer 1: Epoch Rhythm Layer

Time is divided into fixed-length **Epochs**. Each epoch has two phases:

### Work Phase

- Agents execute tasks autonomously
- Use locally cached state from the previous epoch as a baseline (Sticky Convention, mechanism #6)
- No real-time coordination needed — cost approaches zero

### Ritual Phase (Epoch boundary)

This is the ritual moment for producing common knowledge:

```
1. All agents publish their state summary for this epoch to the square
2. All agents publicly ACK each other's states
3. Deterministic rules resolve any conflicts (see below)
4. New epoch state becomes common knowledge
5. Next work phase begins
```

**Deterministic conflict resolution (no voting required):**
- Higher version number wins
- Same version: agent with smallest ID hash wins
- Guarantees all agents independently reach the same conclusion running the same rules

**Rhythm design principle (Chwe):** Rituals must have a predictable cadence. Agents knowing *when* a ritual will occur reduces uncertainty and defensive behavior.

---

## Layer 2: Task Layer (Environment-Mediated)

Task assignment during the work phase is entirely environment-mediated — **no direct agent-to-agent coordination needed**.

### Normal path: Lock/Lease (mechanism #11)

```
Task published to the square
→ Agent atomically requests a Lease (TTL = work phase length)
→ Agent that wins the Lease executes the task
→ Result published to the square
→ Agents that lost continue polling for the next task
```

The lock is an implementation of "environment as arbitrator": no agent needs to convince another — the environment decides directly.

### Fallback path: Market/Auction (mechanism #12)

When a task times out with no takers (all agents busy):
- Task broadcasts a bid request to the square
- Agents report their current load (capacity bids)
- Agent with the lowest bid wins the task

Market price becomes the coordination signal — no central scheduler needed.

---

## Layer 3: Arbitration Layer (Rare Path Only)

**90% of scenarios are handled by Layer 1 + Layer 2. Arbitration is a rare path.**

### Escalation order

```
Level 0: Focal Point
  └─ Is there an "obviously correct" answer? (mechanism #7)
  └─ Cost: zero

Level 1: Temporary Leader Election (mechanism #2)
  └─ Elect a short-term authority for this decision
  └─ Deterministic election (no voting rounds): smallest agent ID among active agents
  └─ Cost: O(n) one broadcast round

Level 2: Threshold Consensus (mechanism #4)
  └─ Requires ≥ ⌈n/2⌉+1 agent signatures
  └─ Used when the leader is unreachable
  └─ Cost: O(n) messages

Level 3: Majority Consensus (mechanism #3)
  └─ Full Raft/Paxos
  └─ Only for system-level state changes (agent join/leave)
  └─ Cost: O(n log n)
```

**Key design principle**: Every arbitration decision must be published to the square to produce common knowledge. Otherwise an "arbitration result" is only mutual knowledge and cannot truly end a dispute.

---

## Failure Handling

| Failure | Response |
|---------|----------|
| Agent crash | Sticky Convention continues; next epoch ritual detects missing ACK; triggers Level 1 leader election |
| Network partition | Each partition continues autonomously; on reconnection, epoch boundary ritual + threshold consensus merges state |
| State fork | Epoch boundary deterministic rules converge; escalate to arbitration if unresolved |
| Byzantine agent | Square log is public — abnormal behavior is independently verifiable by all agents; threshold mechanism naturally excludes minority bad actors |
| Square (Layer 0) failure | Only single point of risk; degrade to temporary Leader mode using the leader's log as a substitute square |

---

## Cost-vs-Frequency Trade-offs

```
Frequency
  High │  Sticky Convention ─────── Work phase default (near-zero cost)
       │  Lock/Lease ───────────── Task assignment (O(1) atomic op)
       │  Epoch Ritual ─────────── Ritual phase sync (O(n) broadcast)
       │  Deterministic Rule ────── Auto conflict resolution (zero comms)
       │
       │  Leader Election ────────── Rare conflict (O(n) one round)
       │  Threshold ─────────────── Rarer (O(n) multi-round)
  Low  │  Full Consensus ──────────  Extremely rare system change (O(n²))
       └─────────────────────────────────────────────────────────────→ Cost
```

---

## Design Summary: Three Core Principles

### Principle 1: Common Knowledge First
Every significant state transition must go through the square (public broadcast + public acknowledgment), not just point-to-point notification. This is Chwe's central lesson.

### Principle 2: Ritual as Infrastructure
The ritual phase at each epoch boundary is not overhead — it is the system's necessary mechanism for producing common knowledge. Fixed cadence reduces uncertainty; public participation builds a shared baseline.

### Principle 3: Default Autonomy + Rare Coordination
Most of the time, agents operate independently on locally cached common knowledge (Sticky Convention). Coordination mechanisms trigger only when necessary, always starting from the lowest-cost level.

---

## Milestone History

| Milestone | Content | Status |
|-----------|---------|--------|
| M1: Core pipeline | Agora square + agent task loop + WebSocket broadcast | ✅ Done |
| M2: Epoch layer | Ritual phase (STATE_PUBLISH + ACK + common knowledge) | ✅ Done |
| M3: DAG scheduling | `depends_on` dependency graph + `TASK_UNBLOCKED` | ✅ Done |
| M4: Agent Registry | Capability declaration + routing + heartbeat detection | ✅ Done |
| M5: Protocol SDK | Python SDK + `/x/` REST API | ✅ Done |
| M6: Arbitration | Leader election + threshold consensus | ✅ Done |
| M7a: Goal completion | `GOAL_COMPLETED` + result aggregation + frontend banner | ✅ Done |
| M7b: Node.js SDK | `sdk/nodejs/agora_sdk.mjs` | ✅ Done |
| M8: React frontend | Vite + React + Tailwind; message stream + arbitration UI | ✅ Done |
| M9: Retry + GOAL_FAILED | Retry exhausted → cascade cleanup → GOAL_FAILED banner | ✅ Done |
| M10: Claude Code integration | PlannerAgent + POST /tasks + cc_worker.py | ✅ Done |
| M11: Production | Kafka replaces Redis Streams | 🔲 Planned |
