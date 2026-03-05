import json
from llm.base import LLMProvider, LLMMessage

SYSTEM = """You are a task decomposer. Break a high-level goal into concrete, independent subtasks.

Return ONLY a JSON array. Each element must have:
- "id": unique string like "task_1", "task_2", ...
- "description": one clear sentence describing exactly what to do
- "depends_on": list of task ids this task needs first (empty list if none)

Keep tasks focused and parallelizable where possible. No markdown, no explanation."""


class GoalDecomposer:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def decompose(self, goal: str) -> list[dict]:
        messages = [LLMMessage(role="user", content=f"Decompose this goal into subtasks:\n\n{goal}")]
        raw = await self.llm.complete(messages, system=SYSTEM)

        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass

        # Fallback: treat the whole goal as a single task
        return [{"id": "task_1", "description": goal, "depends_on": []}]
