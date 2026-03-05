# AGORA

**Decentralized multi-agent coordination infrastructure based on common knowledge theory.**

Most multi-agent systems fail not because agents lack information, but because they lack *common knowledge* — the certainty that everyone knows that everyone knows. AGORA solves this by replacing a central orchestrator with a public broadcast log: a digital town square where all coordination happens in the open.

> Inspired by Michael Chwe's *Rational Ritual: Culture, Coordination, and Common Knowledge*.

---

## Why AGORA?

| | LangGraph / CrewAI / AutoGen | AGORA |
|---|---|---|
| Coordination model | Central orchestrator / supervisor | Decentralized append-only log |
| Knowledge sharing | Point-to-point (mutual knowledge) | Public broadcast + ACK (common knowledge) |
| Agent coupling | Defined inside the framework | External clients, any language or model |
| Single point of failure | Yes — orchestrator down = system down | No — log is the authority |
| Auditability | Implicit, inside orchestrator state | Every decision is a public, immutable record |

AGORA is to multi-agent coordination what a database is to state management: you don't want to re-invent it yourself, and you don't want it baked into your application framework.

---

## Quick Start (5 minutes, no API key required)

**Prerequisites:** Docker, Python ≥ 3.11, Node.js ≥ 18

```bash
git clone https://github.com/your-org/agora.git
cd agora

make redis         # Start Redis in Docker
make install       # Install Python dependencies

# No API key needed — use the mock LLM
echo "LLM_PROVIDER=mock" > backend/.env

make frontend      # Build the React UI
make dev           # Start backend at http://localhost:8000
```

Open `http://localhost:8000`, type any goal into the Submit box, and watch the coordination unfold in real time.

---

## Connect Your Own Agent

### Python

```python
# pip install httpx
import asyncio, sys
sys.path.insert(0, "sdk/python")
from agora_sdk import AgoraAgent

async def handle(task: dict) -> str:
    # task = {"id": "...", "description": "...", "required_capabilities": [...]}
    # call any LLM or tool here
    return f"done: {task['description']}"

async def main():
    agent = AgoraAgent(
        base_url="http://localhost:8000",
        capabilities=["search"],   # only claim tasks you can handle
    )
    await agent.run(handle)

asyncio.run(main())
```

### Node.js

```js
import { AgoraAgent } from './sdk/nodejs/agora_sdk.mjs'

const agent = new AgoraAgent({
  baseUrl: 'http://localhost:8000',
  capabilities: ['code'],
})

await agent.run(async (task) => {
  // call any LLM or tool here
  return `done: ${task.description}`
})
```

The SDK handles registration, heartbeat, atomic task claiming, and result publishing. You only write the task logic.

---

## Submit a Task Graph

Skip the LLM decomposition step and submit a pre-defined DAG directly:

```bash
curl -X POST http://localhost:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "tasks": [
      {"id": "t1", "description": "Collect competitor data",  "required_capabilities": ["search"],   "depends_on": []},
      {"id": "t2", "description": "Analyze pricing strategy", "required_capabilities": ["analysis"], "depends_on": ["t1"]},
      {"id": "t3", "description": "Write summary report",     "required_capabilities": ["write"],    "depends_on": ["t2"]}
    ]
  }'
```

Agents with matching capabilities claim tasks automatically. Downstream tasks unlock as dependencies complete.

---

## Architecture

```
User (browser) ──POST /goal──▶ GoalDecomposer (LLM) ──▶ TaskQueue (Redis List)
                                                                  │
                                                         AgentRuntime spawns agents
                                                                  │
                                               Each Agent polls queue, claims tasks,
                                               calls LLM, publishes results to Agora
                                                                  │
                                           AgoraStream (Redis Stream "agora:log")
                                                                  │
                                          _broadcast_loop ──▶ WebSocket ──▶ browser
```

### Core layers

| Layer | Files | Role |
|-------|-------|------|
| **Agora (the square)** | `agora/stream.py`, `agora/models.py` | Append-only public log — the source of common knowledge |
| **Epoch ritual** | `epoch/manager.py` | Periodic STATE_PUBLISH + ACK cycle that closes the common knowledge loop |
| **Task system** | `tasks/queue.py`, `tasks/decomposer.py` | Redis List queue; Lua atomic claim; DAG dependency scheduling; retry + cascade failure |
| **Agent runtime** | `agent/base.py`, `agent/runtime.py`, `agent/registry.py` | asyncio tasks; poll, execute, publish; heartbeat tracking |
| **Arbitration** | `arbitration/manager.py` | Leader election (min agent_id) + threshold consensus; all results written to Agora |
| **LLM abstraction** | `llm/base.py`, `llm/claude.py`, `llm/mock.py` | Pluggable LLM; set `LLM_PROVIDER=claude\|mock` in `.env` |
| **API** | `main.py` | FastAPI REST + WebSocket; `/x/` external agent interface |
| **SDK** | `sdk/python/`, `sdk/nodejs/` | External agent libraries |
| **Frontend** | `frontend/src/` | React + Vite + Tailwind; real-time message stream + arbitration UI |

### Message types

All coordination is expressed as typed messages on the Agora stream:

```
GOAL_RECEIVED → GOAL_DECOMPOSED → AGENT_JOINED → TASK_CLAIMED → TASK_DONE / TASK_FAILED
                                                                        │ (retries exhausted)
                                                               GOAL_COMPLETED / GOAL_FAILED

Arbitration: LEADER_ELECTED · VOTE_REQUEST → VOTE → CONSENSUS_REACHED / CONSENSUS_FAILED
```

---

## Configuration

Copy `backend/.env.example` to `backend/.env`:

```bash
ANTHROPIC_API_KEY=your-key-here
REDIS_URL=redis://localhost:6379
LLM_PROVIDER=claude          # or: mock (no API key needed)
# EPOCH_INTERVAL=30          # seconds between Epoch rituals
# HEARTBEAT_TIMEOUT=30       # seconds before an external agent is considered dead
```

---

## Development

```bash
make redis         # Start Redis
make install       # Install Python deps (cd backend && pip install -e .)
make dev           # Run backend with hot reload (http://localhost:8000)
make reset         # Clear all agents and logs at runtime
make ui            # Frontend dev server with hot reload (proxies to backend)
make frontend      # Production build to frontend/dist/
```

Run tests:

```bash
cd backend && pytest
```

---

## Documentation

| Document | English | 中文 |
|----------|---------|------|
| Developer Guide — integration, architecture, extension | [developer-guide.md](doc/developer-guide.md) | [开发者指南.md](doc/开发者指南.md) |
| System Design — layers, protocol, design principles | [design.md](doc/design.md) | [AGORA-设计.md](doc/AGORA-设计.md) |
| Why AGORA — problem framing, when to use | [why-agora.md](doc/why-agora.md) | [AGORA-存在必要性.md](doc/AGORA-存在必要性.md) |

> All documentation is available in both English and Chinese (中英双语).

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
