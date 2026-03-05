"""
AGORA SDK — 外部 Agent 接入库

用法示例：
    import asyncio
    from agora_sdk import AgoraAgent

    async def my_handler(task: dict) -> str:
        # 用任意 LLM / 工具处理任务
        return f"Completed: {task['description']}"

    async def main():
        agent = AgoraAgent(
            base_url="http://localhost:8000",
            capabilities=["code", "search"],
        )
        await agent.run(my_handler)

    asyncio.run(main())

依赖：pip install httpx
"""

import asyncio
import logging
import uuid
from typing import Callable, Awaitable, List, Optional

import httpx

log = logging.getLogger("agora_sdk")


class AgoraAgent:
    """
    AGORA 外部 Agent 客户端。

    它通过 HTTP REST 接口接入 AGORA 基础设施，
    无需在 AGORA 进程内部运行，可使用任意 LLM。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        capabilities: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
        poll_interval: float = 1.0,
        heartbeat_interval: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.capabilities = capabilities or []
        self.agent_id = agent_id or f"ext-{uuid.uuid4().hex[:6]}"
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=30)
        self._running = False

    # ------------------------------------------------------------------ #
    # Low-level API calls                                                  #
    # ------------------------------------------------------------------ #

    async def register(self) -> None:
        r = await self._http.post("/x/agents/register", json={
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
        })
        r.raise_for_status()
        data = r.json()
        self.agent_id = data["agent_id"]
        log.info("[%s] Registered | capabilities=%s", self.agent_id, self.capabilities)

    async def claim(self) -> Optional[dict]:
        r = await self._http.post(f"/x/agents/{self.agent_id}/claim")
        r.raise_for_status()
        return r.json().get("task")

    async def done(self, task_id: str, result: str) -> int:
        """返回因此解锁的任务数量。"""
        r = await self._http.post(
            f"/x/agents/{self.agent_id}/tasks/{task_id}/done",
            json={"result": result},
        )
        r.raise_for_status()
        return r.json().get("unblocked", 0)

    async def failed(self, task_id: str, error: str) -> None:
        r = await self._http.post(
            f"/x/agents/{self.agent_id}/tasks/{task_id}/failed",
            json={"error": error},
        )
        r.raise_for_status()

    async def heartbeat(self) -> int:
        """发送心跳，返回当前 epoch。"""
        r = await self._http.post(f"/x/agents/{self.agent_id}/heartbeat")
        r.raise_for_status()
        return r.json().get("epoch", 0)

    async def vote(self, proposal_id: str, approve: bool) -> dict:
        """对提案投票。"""
        r = await self._http.post(
            f"/x/agents/{self.agent_id}/vote",
            json={"proposal_id": proposal_id, "approve": approve},
        )
        r.raise_for_status()
        return r.json()

    async def leave(self) -> None:
        try:
            r = await self._http.delete(f"/x/agents/{self.agent_id}")
            r.raise_for_status()
        except Exception:
            pass
        finally:
            await self._http.aclose()

    # ------------------------------------------------------------------ #
    # High-level run loop                                                  #
    # ------------------------------------------------------------------ #

    async def run(
        self,
        handler: Callable[[dict], Awaitable[str]],
    ) -> None:
        """
        主循环：注册 → 认领任务 → 执行 → 发布结果 → 循环。

        handler 是用户提供的异步函数：
            async def handler(task: dict) -> str
        task 字段：id, description, required_capabilities, depends_on
        """
        await self.register()
        self._running = True

        hb_task = asyncio.create_task(self._heartbeat_loop())
        try:
            while self._running:
                task = await self.claim()
                if task:
                    task_id = task["id"]
                    desc = task.get("description", "")[:80]
                    log.info("[%s] Claimed %s | %s", self.agent_id, task_id, desc)
                    try:
                        result = await handler(task)
                        unblocked = await self.done(task_id, result)
                        log.info("[%s] Done %s | unblocked=%d", self.agent_id, task_id, unblocked)
                    except Exception as e:
                        log.error("[%s] Failed %s | %s", self.agent_id, task_id, e)
                        await self.failed(task_id, str(e))
                else:
                    await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            hb_task.cancel()
            await self.leave()
            log.info("[%s] Left AGORA", self.agent_id)

    def stop(self) -> None:
        """从外部停止运行循环。"""
        self._running = False

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                epoch = await self.heartbeat()
                log.debug("[%s] Heartbeat | epoch=%d", self.agent_id, epoch)
            except Exception as e:
                log.warning("[%s] Heartbeat failed: %s", self.agent_id, e)
