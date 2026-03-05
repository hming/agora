"""Mock LLM provider for local testing without an API key."""
import asyncio
import json
from .base import LLMProvider, LLMMessage


class MockProvider(LLMProvider):
    async def complete(self, messages: list[LLMMessage], system: str = "") -> str:
        await asyncio.sleep(0.3)  # simulate latency
        last = messages[-1].content if messages else ""

        # Decompose mode: return plausible task list
        if "Decompose" in last or "decompose" in last:
            goal = last.split("\n\n")[-1].strip()
            return json.dumps([
                {"id": "task_1", "description": f"[Mock] Research and analyze: {goal}", "depends_on": []},
                {"id": "task_2", "description": f"[Mock] Draft solution for: {goal}", "depends_on": ["task_1"]},
                {"id": "task_3", "description": f"[Mock] Review and finalize: {goal}", "depends_on": ["task_2"]},
            ], ensure_ascii=False)

        # Task execution mode
        return f"[Mock result] Task completed.\nInput summary: {last[:120]}..."
