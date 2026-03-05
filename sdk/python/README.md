# AGORA Python SDK

Connect any Python function to an AGORA coordination network.

## Install

```bash
pip install httpx
```

## Usage

```python
import asyncio, sys
sys.path.insert(0, ".")   # or copy agora_sdk.py to your project
from agora_sdk import AgoraAgent

async def handle(task: dict) -> str:
    # task fields: id, description, required_capabilities, depends_on
    return f"result for: {task['description']}"

async def main():
    agent = AgoraAgent(
        base_url="http://localhost:8000",
        capabilities=["search", "analysis"],
        poll_interval=1.0,
    )
    await agent.run(handle)

asyncio.run(main())
```

The SDK handles: registration, heartbeat, atomic task claiming, result publishing, and graceful shutdown on Ctrl+C.
