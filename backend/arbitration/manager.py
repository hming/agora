"""
仲裁层 (Arbitration Layer)

实现设计文档 Layer 3 的两个机制：

Level 1 — Leader Election
  在每个 Epoch 边界由 EpochManager 触发，确定性规则：
  active agent 中 agent_id 字典序最小者为 Leader。
  零通信成本，结果立即成为公共知识（发布到 Agora）。

Level 2 — Threshold Consensus
  对需要多方认可的决策发起提案（Proposal）。
  当 ≥ ⌈n/2⌉+1 个 active agent 投 approve 时，共识达成。
  当反对票使通过不再可能时，共识失败。
  所有投票行为和结果均发布到 Agora，产生公共知识。
"""

import math
import time
import uuid
from dataclasses import dataclass, field

from agora.models import AgoraMessage, MessageType
from agora.stream import AgoraStream


@dataclass
class Proposal:
    id: str
    topic: str
    value: str
    proposer: str
    created_at: float
    votes_for: set[str] = field(default_factory=set)
    votes_against: set[str] = field(default_factory=set)
    status: str = "pending"   # pending | reached | failed

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "value": self.value,
            "proposer": self.proposer,
            "status": self.status,
            "votes_for": len(self.votes_for),
            "votes_against": len(self.votes_against),
        }


class ArbitrationManager:
    def __init__(self, agora: AgoraStream, runtime):
        self.agora = agora
        self.runtime = runtime
        self._proposals: dict[str, Proposal] = {}

    # ------------------------------------------------------------------ #
    # Level 1: Leader Election                                             #
    # ------------------------------------------------------------------ #

    def current_leader(self) -> str | None:
        """确定性规则：active agent 中 agent_id 字典序最小者。"""
        active = self.runtime.registry.get_active()
        if not active:
            return None
        return min(active, key=lambda r: r.agent_id).agent_id

    async def elect_leader(self, epoch: int) -> str | None:
        """选出 Leader 并发布到 Agora，结果立即成为公共知识。"""
        leader = self.current_leader()
        if leader is None:
            return None

        active = self.runtime.registry.get_active()
        await self.agora.publish(AgoraMessage(
            agent_id="system",
            type=MessageType.LEADER_ELECTED,
            epoch=epoch,
            payload={
                "leader": leader,
                "epoch": epoch,
                "candidates": [r.agent_id for r in active],
            },
            ts=time.time(),
        ))
        return leader

    # ------------------------------------------------------------------ #
    # Level 2: Threshold Consensus                                         #
    # ------------------------------------------------------------------ #

    async def propose(self, topic: str, value: str,
                      proposer: str = "system") -> Proposal:
        """创建提案并广播 VOTE_REQUEST 给所有 active agent。"""
        p = Proposal(
            id=f"prop-{uuid.uuid4().hex[:6]}",
            topic=topic,
            value=value,
            proposer=proposer,
            created_at=time.time(),
        )
        self._proposals[p.id] = p

        active = self.runtime.registry.get_active()
        threshold = math.ceil(len(active) / 2) + 1 if active else 1

        await self.agora.publish(AgoraMessage(
            agent_id="system",
            type=MessageType.VOTE_REQUEST,
            payload={
                "proposal_id": p.id,
                "topic": p.topic,
                "value": p.value,
                "threshold": threshold,
                "active_agents": [r.agent_id for r in active],
            },
            ts=time.time(),
        ))
        return p

    async def vote(self, agent_id: str, proposal_id: str,
                   approve: bool) -> dict:
        """Agent 对提案投票，返回当前投票状态。"""
        p = self._proposals.get(proposal_id)
        if not p:
            raise ValueError(f"Unknown proposal: {proposal_id}")
        if p.status != "pending":
            return {"status": p.status, "already_decided": True}

        if approve:
            p.votes_for.add(agent_id)
            p.votes_against.discard(agent_id)
        else:
            p.votes_against.add(agent_id)
            p.votes_for.discard(agent_id)

        # Publish vote to Agora (all agents can see every vote)
        await self.agora.publish(AgoraMessage(
            agent_id=agent_id,
            type=MessageType.VOTE,
            payload={
                "proposal_id": proposal_id,
                "approve": approve,
                "topic": p.topic,
            },
            ts=time.time(),
        ))

        active = self.runtime.registry.get_active()
        n = max(len(active), 1)
        threshold = math.ceil(n / 2) + 1

        if len(p.votes_for) >= threshold:
            p.status = "reached"
            await self.agora.publish(AgoraMessage(
                agent_id="system",
                type=MessageType.CONSENSUS_REACHED,
                payload={
                    "proposal_id": proposal_id,
                    "topic": p.topic,
                    "value": p.value,
                    "votes_for": len(p.votes_for),
                    "votes_against": len(p.votes_against),
                    "threshold": threshold,
                },
                ts=time.time(),
            ))
        elif len(p.votes_against) > n - threshold:
            p.status = "failed"
            await self.agora.publish(AgoraMessage(
                agent_id="system",
                type=MessageType.CONSENSUS_FAILED,
                payload={
                    "proposal_id": proposal_id,
                    "topic": p.topic,
                    "votes_for": len(p.votes_for),
                    "votes_against": len(p.votes_against),
                    "threshold": threshold,
                },
                ts=time.time(),
            ))

        return {
            "proposal_id": proposal_id,
            "status": p.status,
            "votes_for": len(p.votes_for),
            "votes_against": len(p.votes_against),
            "threshold": threshold,
        }

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        return self._proposals.get(proposal_id)

    def all_proposals(self) -> list[dict]:
        return [p.to_dict() for p in self._proposals.values()]

    def clear(self) -> None:
        self._proposals.clear()
