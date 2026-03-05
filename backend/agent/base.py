import time
from agora.stream import AgoraStream
from agora.models import AgoraMessage, MessageType
from llm.base import LLMProvider, LLMMessage

AGENT_SYSTEM = """You are an autonomous AI agent in a decentralized multi-agent system called AGORA.
Your role is to complete assigned tasks thoroughly and independently.
Report results clearly and concisely. Do not ask clarifying questions — make reasonable assumptions."""


class Agent:
    def __init__(self, agent_id: str, agora: AgoraStream, llm: LLMProvider,
                 capabilities: list[str] | None = None):
        self.agent_id = agent_id
        self.agora = agora
        self.llm = llm
        self.running = False
        self.epoch = 0
        self.capabilities: list[str] = capabilities or []

    async def publish(self, type: MessageType, payload: dict) -> str:
        msg = AgoraMessage(
            epoch=self.epoch,
            agent_id=self.agent_id,
            type=type,
            payload=payload,
            ts=time.time(),
        )
        return await self.agora.publish(msg)

    async def run_task(self, task: dict) -> str:
        task_id = task.get("id", "?")
        await self.publish(MessageType.TASK_CLAIMED, {"task_id": task_id, "description": task.get("description", "")})

        try:
            messages = [LLMMessage(role="user", content=f"Complete this task:\n\n{task.get('description', task)}")]
            result = await self.llm.complete(messages, system=AGENT_SYSTEM)
            await self.publish(MessageType.TASK_DONE, {"task_id": task_id, "result": result})
            return result
        except Exception as e:
            payload: dict = {"task_id": task_id, "error": str(e)}
            if task.get("retry_count"):
                payload["retry_count"] = task["retry_count"]
            await self.publish(MessageType.TASK_FAILED, payload)
            raise
