import asyncio
import uuid
from agent.base import Agent
from agent.registry import AgentRegistry
from agora.stream import AgoraStream
from agora.models import MessageType
from tasks.queue import TaskQueue
from llm.base import LLMProvider

POLL_INTERVAL = 0.5  # seconds between task queue polls when idle


class AgentRuntime:
    def __init__(self, agora: AgoraStream, task_queue: TaskQueue, llm: LLMProvider):
        self.agora = agora
        self.task_queue = task_queue
        self.llm = llm
        self.agents: dict[str, Agent] = {}
        self._asyncio_tasks: dict[str, asyncio.Task] = {}
        self.registry = AgentRegistry()

    def spawn_planner(self) -> "Agent":
        from agent.planner import PlannerAgent
        from tasks.decomposer import GoalDecomposer
        agent_id = f"planner-{uuid.uuid4().hex[:6]}"
        agent = PlannerAgent(agent_id, self.agora, self.llm, self.task_queue, GoalDecomposer(self.llm))
        self.agents[agent_id] = agent
        self.registry.register(agent_id, agent.capabilities)
        self._asyncio_tasks[agent_id] = asyncio.create_task(
            self._run(agent), name=agent_id
        )
        return agent

    def spawn(self, capabilities: list[str] | None = None) -> Agent:
        agent_id = f"agent-{uuid.uuid4().hex[:6]}"
        agent = Agent(agent_id, self.agora, self.llm, capabilities=capabilities or [])
        self.agents[agent_id] = agent
        self.registry.register(agent_id, agent.capabilities)
        self._asyncio_tasks[agent_id] = asyncio.create_task(
            self._run(agent), name=agent_id
        )
        return agent

    def stop(self, agent_id: str) -> None:
        if agent_id in self.agents:
            self.agents[agent_id].running = False

    def stop_all(self) -> None:
        for agent in self.agents.values():
            agent.running = False

    def status(self) -> list[dict]:
        return [
            {
                "agent_id": rec.agent_id,
                "status": rec.status,
                "capabilities": rec.capabilities,
                "current_task": rec.current_task,
                "epoch": rec.epoch,
            }
            for rec in self.registry.all()
        ]

    async def _publish_goal_failed(self, goal_id: str, failed_task_id: str) -> None:
        import time as _time
        from agora.models import AgoraMessage
        meta = await self.task_queue.get_goal_meta(goal_id)
        await self.agora.publish(AgoraMessage(
            agent_id="system",
            type=MessageType.GOAL_FAILED,
            payload={"goal_id": goal_id, "goal": meta.get("goal", ""), "failed_task": failed_task_id},
            ts=_time.time(),
        ))

    async def _publish_goal_completed(self, goal_id: str) -> None:
        import time as _time
        from agora.models import AgoraMessage
        meta = await self.task_queue.get_goal_meta(goal_id)
        await self.agora.publish(AgoraMessage(
            agent_id="system",
            type=MessageType.GOAL_COMPLETED,
            payload={"goal_id": goal_id, "goal": meta.get("goal", ""), "total_tasks": meta.get("total", 0)},
            ts=_time.time(),
        ))

    async def _run(self, agent: Agent) -> None:
        import logging
        import time as _time
        from agora.models import AgoraMessage

        log = logging.getLogger(agent.agent_id)

        try:
            agent.running = True
            await agent.publish(MessageType.AGENT_JOINED, {
                "agent_id": agent.agent_id,
                "capabilities": agent.capabilities,
            })

            while agent.running:
                task = await self.task_queue.claim(agent.capabilities)
                if task:
                    self.registry.touch(agent.agent_id, current_task=task["id"],
                                        current_task_data=task)
                    try:
                        await agent.run_task(task)
                        self.registry.clear_task(agent.agent_id)
                        unblocked, completed_goals = await self.task_queue.mark_done(task["id"])
                        await asyncio.sleep(0)  # 让出 event loop，给其他 agent 机会 claim 解锁的任务
                        for t in unblocked:
                            await self.agora.publish(AgoraMessage(
                                agent_id="system",
                                type=MessageType.TASK_UNBLOCKED,
                                payload={"task_id": t["id"], "description": t.get("description", "")},
                                ts=_time.time(),
                            ))
                        for goal_id in completed_goals:
                            await self._publish_goal_completed(goal_id)
                    except Exception:
                        self.registry.clear_task(agent.agent_id)
                        # TASK_FAILED already published inside run_task
                        # Try to requeue for retry; if max retries exceeded, mark goal failed
                        requeued = await self.task_queue.try_requeue(task)
                        if requeued:
                            log.warning("Task %s requeued for retry (attempt %d)",
                                        task["id"], task.get("retry_count", 0) + 1)
                        else:
                            failed_goals, cascaded = await self.task_queue.mark_failed(task["id"])
                            # 发布级联失败的下游任务
                            for ct in cascaded:
                                await self.agora.publish(AgoraMessage(
                                    agent_id="system",
                                    type=MessageType.TASK_FAILED,
                                    payload={"task_id": ct["id"], "error": f"dependency failed: {task['id']}"},
                                    ts=_time.time(),
                                ))
                            for goal_id in failed_goals:
                                await self._publish_goal_failed(goal_id, task["id"])
                else:
                    await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("Agent %s crashed: %s", agent.agent_id, repr(e), exc_info=True)
        finally:
            agent.running = False
            self.registry.mark_stopped(agent.agent_id)
            await agent.publish(MessageType.AGENT_LEFT, {"agent_id": agent.agent_id})
