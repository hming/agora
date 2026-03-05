from enum import Enum
from pydantic import BaseModel, Field
from typing import Any
import time
import uuid


class MessageType(str, Enum):
    GOAL_RECEIVED = "GOAL_RECEIVED"
    GOAL_DECOMPOSED = "GOAL_DECOMPOSED"
    GOAL_COMPLETED = "GOAL_COMPLETED"
    GOAL_FAILED = "GOAL_FAILED"
    TASK_CLAIMED = "TASK_CLAIMED"
    TASK_DONE = "TASK_DONE"
    TASK_FAILED = "TASK_FAILED"
    TASK_UNBLOCKED = "TASK_UNBLOCKED"
    STATE_PUBLISH = "STATE_PUBLISH"
    ACK = "ACK"
    EPOCH_START = "EPOCH_START"
    AGENT_JOINED = "AGENT_JOINED"
    AGENT_LEFT = "AGENT_LEFT"
    LEADER_ELECTED = "LEADER_ELECTED"
    VOTE_REQUEST = "VOTE_REQUEST"
    VOTE = "VOTE"
    CONSENSUS_REACHED = "CONSENSUS_REACHED"
    CONSENSUS_FAILED = "CONSENSUS_FAILED"


class AgoraMessage(BaseModel):
    id: str = Field(default_factory=lambda: "")
    epoch: int = 0
    agent_id: str
    type: MessageType
    payload: dict[str, Any]
    ts: float = Field(default_factory=time.time)
