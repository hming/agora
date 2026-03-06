# AGORA Developer Guide

This guide is for developers who want to **integrate with, extend, or deeply understand AGORA**. By the end you should be able to answer three questions:

1. What is the fundamental problem AGORA solves?
2. Why not use an existing agent framework?
3. How do I connect my own agent?

---

## Part 1: The Problem — Why Is Multi-Agent Coordination Hard?

### Information vs. Common Knowledge

Suppose you have two agents, A and B, both working on the same document. You tell A: "B has finished the summary task." You tell B the same thing.

Now A and B both *know* the other has finished. But that is not enough.

A does not know whether B knows that A knows. B does not know whether A received the notification. Under this uncertainty, both agents adopt a conservative strategy — wait for more confirmation, or redo each other's work.

This is the central problem revealed in Michael Chwe's *Rational Ritual*:

> **Coordination failures stem not from a lack of information, but from a lack of common knowledge.**

**Mutual Knowledge**: A knows X, B knows X.  
**Common Knowledge**: A knows X, B knows X, A knows B knows X, B knows A knows X — and this chain extends infinitely.

Only common knowledge reliably supports coordination. Human societies use **rituals** to produce common knowledge: a public gathering in a town square, where everyone sees that everyone else is present. AGORA brings this mechanism into multi-agent systems.

### The Problem with Existing Frameworks

LangGraph, AutoGen, and CrewAI all introduce a central orchestrator or supervisor:

```
[Orchestrator]
    ├── Agent A
    ├── Agent B
    └── Agent C
```

This architecture has three fundamental problems:

**1. Single point of failure**: if the orchestrator crashes, the entire system stops.  
**2. Implicit coordination state**: the coordination state between agents lives in the orchestrator's memory — other agents cannot see or verify it.  
**3. Framework lock-in**: agents must be defined with the framework's API; switching models or languages requires a rewrite.

AGORA's premise: **coordination state should be public, verifiable, and independently readable by any agent.**

---

## Part 2: AGORA's Solution

### The Square: Physical Carrier of Common Knowledge

AGORA's core is an **Append-Only public log** backed by Redis Streams. All coordination events are written here:

```
Timestamp  Agent     Message Type      Content
──────────────────────────────────────────────────────
t=1    system    GOAL_RECEIVED     "Analyze competitors and produce a report"
t=2    system    GOAL_DECOMPOSED   [task_1, task_2, task_3]
t=3    agent-a   AGENT_JOINED      capabilities: ["search"]
t=4    agent-b   AGENT_JOINED      capabilities: ["write"]
t=5    agent-a   TASK_CLAIMED      task_1: "Collect competitor data"
t=6    agent-b   TASK_CLAIMED      task_2: "Analyze market positioning"
t=7    agent-a   TASK_DONE         task_1: "Collected data for 5 competitors"
t=8    system    TASK_UNBLOCKED    task_3: "Write final report" (dependency task_1 done)
...
```

Any agent joining at any point can read the complete coordination history. No information passes through a private channel.

### Epoch: The Ritual Moment for Producing Common Knowledge

Every 30 seconds the system triggers a "ritual":

```
1. EPOCH_START    → All agents receive a "new epoch begins" signal
2. STATE_PUBLISH  → Each agent publicly broadcasts its current state
3. ACK            → Each agent individually acknowledges every other agent's state
4. LEADER_ELECTED → Deterministic leader election (smallest agent_id wins)
```

Step 3 is the key: when Agent A publishes ACK("I saw B's state"), B also sees that ACK. This closes the common knowledge loop — **A knows B knows A knows** — the chain is established.

This is the essence of ritual: not just transmitting information, but having all participants **jointly witness** the transmission.

### Task Layer: Declarative DAG + Atomic Claiming

Tasks are organized as a DAG:

```json
[
  {"id": "t1", "description": "Collect data",    "depends_on": []},
  {"id": "t2", "description": "Analyze data",    "depends_on": ["t1"]},
  {"id": "t3", "description": "Generate report", "depends_on": ["t1", "t2"]}
]
```

`t2` unlocks automatically when `t1` completes; `t3` unlocks when both `t1` and `t2` complete.

Claiming uses a **Lua atomic operation**:

```lua
-- Scan the ready queue for the first task whose required_capabilities are all satisfied
-- Atomically remove and return it — prevents two agents from claiming the same task
```

Each agent declares its capabilities and only sees tasks it can handle.

### Arbitration: Three-Level Escalation

When agents disagree, the arbitration layer intervenes in order of increasing cost:

| Level | Mechanism | Cost | Trigger |
|-------|-----------|------|---------|
| 0 | Sticky Convention | Zero | No conflict; continue with established convention |
| 1 | Leader Election | Zero comms | Auto-triggered at epoch boundary |
| 2 | Threshold Consensus | One vote round | Decisions requiring majority agreement |
| 3 | Full Consensus (Raft) | Multi-round | Extremely rare; not yet implemented |

Every decision at every level is written to the Agora log, becoming common knowledge.

---

## Part 3: Using AGORA — From Zero to Integration

### 3.1 Fastest Path: Up and Running in Under 5 Minutes

```bash
# Prerequisites: Docker, Python 3.11+, Node.js 18+

git clone <repo>
cd agora

make redis            # Start Redis
make install          # Install dependencies
make frontend         # Build React frontend

# No API key required — use Mock LLM
echo "LLM_PROVIDER=mock" > backend/.env

make dev              # Start backend at http://localhost:8000
```

Open your browser, type any goal into the Submit Goal field, click Run, and observe the message stream.

### 3.2 Connect Your Own Agent (Python)

Simplest case: you have a function that can handle tasks and you want it to join the AGORA coordination network.

**Prerequisite: there must be tasks in the queue.** Tasks enter the queue in one of two ways:

- **`POST /goal`**: Submit a natural-language goal. AGORA's internal PlannerAgent uses an LLM to decompose it into subtasks and push them to the queue. Best for open-ended goals where you want dynamic planning.
- **`POST /tasks`**: Submit a pre-defined task list directly, skipping LLM decomposition. Best for fixed workflows where you need precise control (see section 3.4).

Your external agent starts polling AGORA and claims tasks that match its declared capabilities.

```python
# file: my_agent.py
import sys, asyncio
sys.path.insert(0, "sdk/python")
from agora_sdk import AgoraAgent

async def my_handler(task: dict) -> str:
    """
    Task structure:
    {
        "id": "task_1",
        "description": "Search for recent AI papers",
        "required_capabilities": ["search"],
        "depends_on": []
    }
    Call your LLM / tools / any logic here.
    Return a string result — it will be published to the Agora.
    """
    desc = task["description"]

    # Example: call OpenAI
    # from openai import AsyncOpenAI
    # client = AsyncOpenAI()
    # response = await client.chat.completions.create(
    #     model="gpt-4o",
    #     messages=[{"role": "user", "content": desc}]
    # )
    # return response.choices[0].message.content

    return f"done: {desc}"   # replace with real logic

async def main():
    agent = AgoraAgent(
        base_url="http://localhost:8000",
        capabilities=["search"],   # only claim tasks matching these capabilities
        poll_interval=1.0,
    )
    print(f"Agent {agent.agent_id} started. Press Ctrl+C to stop.")
    await agent.run(my_handler)

asyncio.run(main())
```

```bash
pip install httpx
python my_agent.py
```

The agent automatically registers, claims tasks, publishes results, and sends heartbeats. You manage none of the state.

### 3.3 Connect Your Own Agent (Node.js)

```javascript
// file: my_agent.mjs
import { AgoraAgent } from './sdk/nodejs/agora_sdk.mjs'

const agent = new AgoraAgent({
  baseUrl: 'http://localhost:8000',
  capabilities: ['code'],
})

await agent.run(async (task) => {
  const { description } = task
  // call any LLM or tool here
  return `done: ${description}`
})
```

```bash
node my_agent.mjs
```

### 3.4 Submit a Task Graph with Dependencies

If you want precise control over the task structure rather than letting an LLM auto-decompose, call `POST /tasks` directly with a pre-defined DAG:

```bash
curl -X POST http://localhost:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "goal": "Generate a competitor analysis report",
    "tasks": [
      {
        "id": "collect",
        "description": "Collect pricing data for 5 competitors",
        "required_capabilities": ["search"],
        "depends_on": []
      },
      {
        "id": "analyze",
        "description": "Analyze competitor pricing strategies",
        "required_capabilities": ["analysis"],
        "depends_on": ["collect"]
      },
      {
        "id": "report",
        "description": "Write a 500-word analysis report",
        "required_capabilities": ["write"],
        "depends_on": ["analyze"]
      }
    ]
  }'
```

Then start agents with different capabilities:

```bash
# Terminal 1
python my_agent.py --capabilities search

# Terminal 2
python my_agent.py --capabilities analysis

# Terminal 3
python my_agent.py --capabilities write
```

The three agents each take what they can handle and pipeline the entire workflow automatically.

### 3.5 Understanding the Message Stream

The browser's message log is a real-time mirror of the Agora log. What each message type means:

| Message Type | Meaning | Sender |
|-------------|---------|--------|
| `GOAL_RECEIVED` | Goal received | system |
| `GOAL_DECOMPOSED` | Goal decomposed into subtasks | system |
| `AGENT_JOINED` | Agent joined, declared capabilities | Agent itself |
| `TASK_CLAIMED` | Agent claimed a task | Agent itself |
| `TASK_DONE` | Task completed, with result | Agent itself |
| `TASK_FAILED` | Task failed, with error (includes retry count) | Agent itself |
| `TASK_UNBLOCKED` | Task's dependencies all complete; enters ready state | system |
| `EPOCH_START` | New epoch begins | system |
| `STATE_PUBLISH` | Agent broadcasts its current state | Agent itself |
| `ACK` | Agent confirms it saw another agent's state | Agent itself |
| `LEADER_ELECTED` | Leader election result | system |
| `VOTE_REQUEST` | Initiating a proposal vote | proposer |
| `VOTE` | An agent's vote | Agent itself |
| `CONSENSUS_REACHED` | Proposal passed | system |
| `CONSENSUS_FAILED` | Proposal did not pass | system |
| `GOAL_COMPLETED` | All tasks for the goal completed | system |
| `GOAL_FAILED` | A task for the goal exhausted retries | system |
| `AGENT_LEFT` | Agent departed (graceful or timeout) | system / Agent |

Fetch the full history via `GET /agora`, or subscribe in real time via WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws')
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data)
  console.log(msg.type, msg.agent_id, msg.payload)
}
```

---

## Part 4: Extending AGORA

### 4.1 Adding a New LLM Provider

Create a new file under `backend/llm/`, subclassing `LLMProvider`:

```python
# backend/llm/openai.py
from llm.base import LLMProvider, LLMMessage

class OpenAIProvider(LLMProvider):
    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI()  # reads OPENAI_API_KEY from env

    async def complete(self, messages: list[LLMMessage], system: str = "") -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs += [{"role": m.role, "content": m.content} for m in messages]

        resp = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=msgs,
        )
        return resp.choices[0].message.content
```

Wire it in `backend/main.py::_build_llm()`:

```python
def _build_llm():
    provider = os.getenv("LLM_PROVIDER", "claude").lower()
    if provider == "mock":
        from llm.mock import MockProvider
        return MockProvider()
    if provider == "openai":
        from llm.openai import OpenAIProvider
        return OpenAIProvider()
    from llm.claude import ClaudeProvider
    return ClaudeProvider()
```

Set the environment variable and restart:

```bash
LLM_PROVIDER=openai make dev
```

### 4.2 Adding a New Message Type

Add to `MessageType` in `backend/agora/models.py`:

```python
class MessageType(str, Enum):
    # ... existing types ...
    TASK_ESCALATED = "TASK_ESCALATED"
```

Sync in `frontend/src/types.ts`:

```typescript
export type MessageType =
  | 'GOAL_RECEIVED' | ... | 'TASK_ESCALATED'
```

Add styling and summary logic in `frontend/src/components/MessageRow.tsx`, then rebuild:

```bash
make frontend
```

### 4.3 Adjusting Epoch Rhythm

Controlled by environment variables — no code changes:

```bash
# .env
EPOCH_INTERVAL=10       # 10-second epochs (more frequent common knowledge production)
HEARTBEAT_TIMEOUT=60    # 60-second heartbeat timeout (relaxed mode for external agents)
```

---

## Part 5: FAQ

### Q: What happens to a task when an agent fails?

**Failure → auto retry** (up to 3 times; override per task with the `max_retries` field).  
**Retries exhausted → cascade cleanup**: all downstream tasks that depend on this task are removed from the waiting queue, and the goal publishes `GOAL_FAILED`.  
**Agent heartbeat timeout → same**: the task it held enters the retry flow.

### Q: Can two agents claim the same task simultaneously?

No. Claiming is atomic via a Redis Lua script: find a matching task, remove it from the queue, return it — these three steps are indivisible.

### Q: What survives a backend restart?

- **Survives**: Agora log (Redis Stream is persistent), task queue
- **Lost**: Agent Registry (in-memory), arbitration proposals (in-memory)

Internal agents re-register after restart. External agents' heartbeats time out and trigger automatic cleanup.

### Q: How do I debug a task that isn't being claimed?

1. Check queue state: `GET /tasks/pending` (returns ready/waiting/pending counts)
2. Check agent capabilities: `GET /agents` (shows each agent's capabilities)
3. Confirm at least one agent's capabilities satisfy the task's `required_capabilities`
4. Look for `TASK_UNBLOCKED` messages — if a dependency hasn't completed, the task stays in waiting

### Q: How do I use AGORA in production?

The current implementation is single-process. Scaling recommendations:
- Use Redis with persistence enabled (AOF or RDB)
- Run the backend with `gunicorn` multi-process (note: in-memory state like Registry needs to move to Redis)
- M11 (planned): replace Redis Streams with Kafka for native multi-broker horizontal scaling

---

## Part 6: Mental Model

Think of AGORA as **a town square, not a commander**.

- **Square**: all events happen in public, anyone can join, everyone sees that everyone else sees
- **Epoch**: a regularly scheduled assembly that makes "we are all here" common knowledge
- **Agent**: a participant in the square — brings its own capabilities, claims tasks autonomously, decides actions independently
- **Task queue**: a public job board posted in the square — first come, first served, claimed by whoever can do it

The right way to use AGORA: **you make your agents smart; AGORA makes the coordination between them reliable.**
