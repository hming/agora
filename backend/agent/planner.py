from agent.base import Agent
from agora.models import MessageType
from tasks.queue import TaskQueue
from tasks.decomposer import GoalDecomposer


class PlannerAgent(Agent):
    """拥有 planning 能力的特殊 Agent，负责将 decompose 任务拆解为子任务。"""

    def __init__(self, agent_id: str, agora, llm, task_queue: TaskQueue, decomposer: GoalDecomposer):
        super().__init__(agent_id, agora, llm, capabilities=["planning"])
        self.task_queue = task_queue
        self.decomposer = decomposer

    async def run_task(self, task: dict) -> str:
        if task.get("type") == "decompose":
            return await self._run_decompose(task)
        return await super().run_task(task)

    async def _run_decompose(self, task: dict) -> str:
        task_id = task["id"]
        goal_id = task["goal_id"]
        goal = task["goal"]

        await self.publish(MessageType.TASK_CLAIMED, {
            "task_id": task_id,
            "description": task.get("description", ""),
        })

        try:
            subtasks = await self.decomposer.decompose(goal)
            await self.task_queue.push(subtasks)
            await self.task_queue.register_goal(goal_id, goal, [t["id"] for t in subtasks])

            await self.publish(MessageType.GOAL_DECOMPOSED, {
                "goal_id": goal_id,
                "goal": goal,
                "tasks": subtasks,
            })
            await self.publish(MessageType.TASK_DONE, {
                "task_id": task_id,
                "result": f"Decomposed into {len(subtasks)} subtasks",
            })
            return f"Decomposed into {len(subtasks)} subtasks"
        except Exception as e:
            await self.publish(MessageType.TASK_FAILED, {
                "task_id": task_id,
                "error": str(e),
            })
            raise
