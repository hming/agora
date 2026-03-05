import asyncio
import os
import time

from agora.models import AgoraMessage, MessageType
from agora.stream import AgoraStream

EPOCH_INTERVAL = int(os.getenv("EPOCH_INTERVAL", "30"))


class EpochManager:
    """
    Drives the ritual cycle that produces common knowledge among agents.

    每隔 EPOCH_INTERVAL 秒触发一次仪式期：
      1. 系统广播 EPOCH_START（所有 Agent 可见，确立新纪元）
      2. 所有活跃 Agent 发布 STATE_PUBLISH（公开各自状态）
      3. 所有活跃 Agent 互相 ACK（"我知道你知道了"——产生公共知识）
    """

    def __init__(self, agora: AgoraStream, runtime, arbitration=None):
        self.agora = agora
        self.runtime = runtime
        self.arbitration = arbitration   # ArbitrationManager (optional)
        self.current_epoch = 0

    async def run(self) -> None:
        while True:
            await asyncio.sleep(EPOCH_INTERVAL)
            await self._ritual()

    async def _ritual(self) -> None:
        self.current_epoch += 1
        epoch = self.current_epoch

        active = [a for a in self.runtime.agents.values() if a.running]
        if not active:
            return

        # Update epoch counter on all agents (both object and registry)
        for agent in active:
            agent.epoch = epoch
            self.runtime.registry.update_epoch(agent.agent_id, epoch)

        # ── Phase 0: Announce epoch start (system-level common knowledge) ──
        await self.agora.publish(AgoraMessage(
            agent_id="system",
            type=MessageType.EPOCH_START,
            epoch=epoch,
            payload={"epoch": epoch, "agents": [a.agent_id for a in active]},
            ts=time.time(),
        ))

        # ── Phase 1: Each agent publishes its local state ──
        for agent in active:
            await agent.publish(MessageType.STATE_PUBLISH, {
                "epoch": epoch,
                "peers": [a.agent_id for a in active if a.agent_id != agent.agent_id],
            })

        # ── Phase 2: Each agent publicly ACKs every peer's state ──
        # This closes the common-knowledge loop:
        # "A knows B's state, and B knows A knows B's state"
        for agent in active:
            for peer in active:
                if peer.agent_id != agent.agent_id:
                    await agent.publish(MessageType.ACK, {
                        "epoch": epoch,
                        "ack_target": peer.agent_id,
                    })

        # ── Phase 3: Leader Election (Level 1 Arbitration) ──
        # Deterministic, zero communication cost: min agent_id wins.
        if self.arbitration:
            await self.arbitration.elect_leader(epoch)
