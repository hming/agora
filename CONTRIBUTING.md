# Contributing to AGORA

## Getting started

```bash
git clone https://github.com/your-org/agora.git
cd agora

make redis
make install       # cd backend && pip install -e ".[test]"
make frontend
cp backend/.env.example backend/.env   # set LLM_PROVIDER=mock for local dev
make dev
```

## Running tests

```bash
cd backend && pytest
```

Tests use `fakeredis` — no real Redis needed.

## Project structure

```
backend/
  agora/          # Core: stream, models (MessageType enum)
  agent/          # Agent runtime, registry, planner
  tasks/          # Task queue (Lua atomic claim), DAG decomposer
  epoch/          # Epoch ritual manager
  arbitration/    # Leader election + threshold consensus
  llm/            # Pluggable LLM providers
  main.py         # FastAPI entry point

frontend/src/
  components/     # React UI components
  hooks/          # useAgora WebSocket hook
  types.ts        # Shared TypeScript types

sdk/
  python/         # Python external agent SDK
  nodejs/         # Node.js external agent SDK

scripts/
  demo.py         # Demo script
```

## Making changes

- **New LLM provider**: subclass `LLMProvider` in `llm/base.py`, wire it in `main.py::_build_llm()`
- **New message type**: add to `MessageType` in `agora/models.py`, sync `frontend/src/types.ts`
- **New agent capability**: implement `run_task()` in a subclass of `AgentBase`

## Pull requests

- Keep PRs focused — one concern per PR
- Add or update tests when changing task queue or agent logic
- Frontend changes: run `make frontend` before committing to verify the build passes

## Issues

Bug reports and feature requests are welcome. Please include:
- What you expected vs. what happened
- Minimal reproduction steps
- AGORA version / Python version / OS
