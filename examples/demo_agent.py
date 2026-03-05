"""
demo_agent.py — AGORA external agent demo

Shows how to connect to AGORA using agora_sdk and handle tasks with your own logic.
Replace `my_handler` with any real LLM call (OpenAI, local Llama, etc.).

Usage (ensure the AGORA backend is running first):
    pip install httpx
    python examples/demo_agent.py           # single agent
    python examples/demo_agent.py --multi   # three agents with different capabilities

Open http://localhost:8000 in a browser to watch the live coordination log.
"""

import asyncio
import logging
import sys
import os

# Import the SDK from sdk/python
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sdk", "python"))
from agora_sdk import AgoraAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)

AGORA_URL = os.getenv("AGORA_URL", "http://localhost:8000")


async def my_handler(task: dict) -> str:
    """
    Your task handling logic goes here.
    This mock simulates processing time — replace it with a real LLM call.
    """
    desc = task.get("description", "")

    # Simulate processing time
    await asyncio.sleep(0.5)

    return (
        f"[demo_agent.py] Completed: {desc[:100]}\n"
        f"(Replace this with a real LLM call)"
    )


async def run_single_agent():
    """Run a single external agent."""
    agent = AgoraAgent(
        base_url=AGORA_URL,
        capabilities=["general"],
        poll_interval=0.8,
    )

    print(f"\nAGORA external agent started")
    print(f"  server:       {AGORA_URL}")
    print(f"  capabilities: {agent.capabilities}")
    print("  Press Ctrl+C to stop\n")

    try:
        await agent.run(my_handler)
    except KeyboardInterrupt:
        agent.stop()


async def run_multi_agent():
    """Run multiple agents in parallel, each with different capabilities."""
    agents_config = [
        {"capabilities": ["code"], "agent_id": "ext-coder"},
        {"capabilities": ["search"], "agent_id": "ext-searcher"},
        {"capabilities": ["code", "search"], "agent_id": "ext-fullstack"},
    ]

    agents = [
        AgoraAgent(base_url=AGORA_URL, poll_interval=0.5, **cfg)
        for cfg in agents_config
    ]

    print(f"\nStarting {len(agents)} external agents...")
    tasks = [asyncio.create_task(agent.run(my_handler)) for agent in agents]

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        for agent in agents:
            agent.stop()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AGORA external agent demo")
    parser.add_argument("--multi", action="store_true", help="Start multiple agents")
    args = parser.parse_args()

    if args.multi:
        asyncio.run(run_multi_agent())
    else:
        asyncio.run(run_single_agent())
