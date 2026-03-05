import time
from dataclasses import dataclass, field


@dataclass
class AgentRecord:
    agent_id: str
    capabilities: list[str]
    status: str = "running"        # running | stopped
    current_task: str | None = None
    current_task_data: dict | None = None  # full task JSON for requeue on death
    epoch: int = 0
    last_active: float = field(default_factory=time.time)


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, AgentRecord] = {}

    def register(self, agent_id: str, capabilities: list[str]) -> AgentRecord:
        record = AgentRecord(agent_id=agent_id, capabilities=list(capabilities))
        self._agents[agent_id] = record
        return record

    def touch(self, agent_id: str, current_task: str | None = None,
              current_task_data: dict | None = None) -> None:
        rec = self._agents.get(agent_id)
        if rec:
            rec.last_active = time.time()
            if current_task is not None:
                rec.current_task = current_task
            if current_task_data is not None:
                rec.current_task_data = current_task_data

    def clear_task(self, agent_id: str) -> None:
        rec = self._agents.get(agent_id)
        if rec:
            rec.current_task = None
            rec.current_task_data = None
            rec.last_active = time.time()

    def stale_agents(self, timeout: float) -> list["AgentRecord"]:
        """返回超过 timeout 秒未活跃的 running agent。"""
        now = time.time()
        return [
            r for r in self._agents.values()
            if r.status == "running" and (now - r.last_active) > timeout
        ]

    def mark_stopped(self, agent_id: str) -> None:
        rec = self._agents.get(agent_id)
        if rec:
            rec.status = "stopped"
            rec.current_task = None

    def update_epoch(self, agent_id: str, epoch: int) -> None:
        rec = self._agents.get(agent_id)
        if rec:
            rec.epoch = epoch

    def get_active(self) -> list[AgentRecord]:
        return [r for r in self._agents.values() if r.status == "running"]

    def all(self) -> list[AgentRecord]:
        return list(self._agents.values())

    def clear(self) -> None:
        self._agents.clear()
