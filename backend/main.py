import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agora.models import AgoraMessage, MessageType
from agora.stream import AgoraStream
from agent.runtime import AgentRuntime
from arbitration.manager import ArbitrationManager
from epoch.manager import EpochManager
from tasks.queue import TaskQueue, TASK_READY_KEY, TASK_WAITING_KEY, COMPLETED_KEY, GOAL_TASKS_KEY, GOAL_META_KEY

load_dotenv()

# --- Globals ---
_r: redis.Redis | None = None
agora: AgoraStream | None = None
task_queue: TaskQueue | None = None
runtime: AgentRuntime | None = None
arbitration: ArbitrationManager | None = None
_ws_clients: list[WebSocket] = []


def _build_llm():
    provider = os.getenv("LLM_PROVIDER", "claude").lower()
    if provider == "mock":
        from llm.mock import MockProvider
        return MockProvider()
    from llm.claude import ClaudeProvider
    return ClaudeProvider()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _r, agora, task_queue, runtime, arbitration

    _r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=False)
    agora = AgoraStream(_r)
    task_queue = TaskQueue(_r)
    llm = _build_llm()
    runtime = AgentRuntime(agora, task_queue, llm)
    arbitration = ArbitrationManager(agora, runtime)

    epoch_manager = EpochManager(agora, runtime, arbitration=arbitration)

    broadcast_task = asyncio.create_task(_broadcast_loop())
    epoch_task = asyncio.create_task(epoch_manager.run())
    heartbeat_task = asyncio.create_task(_heartbeat_checker())

    yield

    broadcast_task.cancel()
    epoch_task.cancel()
    heartbeat_task.cancel()
    runtime.stop_all()
    await _r.aclose()


app = FastAPI(title="AGORA", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- WebSocket broadcast loop ---

async def _broadcast_loop():
    last_id = "$"
    while True:
        try:
            pairs = await agora.read_new(last_id, timeout_ms=200)
            for mid, msg in pairs:
                last_id = mid
                data = json.dumps(msg.model_dump(), ensure_ascii=False)
                dead = []
                for ws in list(_ws_clients):
                    try:
                        await ws.send_text(data)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    _ws_clients.remove(ws)
        except Exception:
            await asyncio.sleep(0.1)


HEARTBEAT_TIMEOUT = float(os.getenv("HEARTBEAT_TIMEOUT", "30"))  # seconds
HEARTBEAT_CHECK_INTERVAL = 10.0


async def _heartbeat_checker():
    """
    每 10 秒扫描一次 registry，将超时未活跃的 agent 标记为 stopped，
    并把它们持有的任务放回队列。
    仅影响外部 agent（内部 asyncio agent 有自己的 finally 清理逻辑）。
    """
    import logging
    log = logging.getLogger("heartbeat_checker")

    while True:
        await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)
        stale = runtime.registry.stale_agents(HEARTBEAT_TIMEOUT)
        for rec in stale:
            log.warning("Agent %s stale (%.0fs), evicting", rec.agent_id, HEARTBEAT_TIMEOUT)
            runtime.registry.mark_stopped(rec.agent_id)

            # 任务重试入队；超过上限则级联失败
            if rec.current_task_data:
                requeued = await task_queue.try_requeue(rec.current_task_data)
                if requeued:
                    log.warning("Requeued task %s for retry", rec.current_task)
                else:
                    log.warning("Task %s exceeded max retries after heartbeat timeout, cascading failure", rec.current_task)
                    failed_goals, cascaded = await task_queue.mark_failed(rec.current_task_data["id"])
                    for ct in cascaded:
                        await agora.publish(AgoraMessage(
                            agent_id="system", type=MessageType.TASK_FAILED,
                            payload={"task_id": ct["id"], "error": f"dependency failed: {rec.current_task}"},
                            ts=time.time(),
                        ))
                    for goal_id in failed_goals:
                        await runtime._publish_goal_failed(goal_id, rec.current_task_data["id"])

            await agora.publish(AgoraMessage(
                agent_id=rec.agent_id,
                type=MessageType.AGENT_LEFT,
                payload={"agent_id": rec.agent_id, "reason": "heartbeat_timeout"},
                ts=time.time(),
            ))


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    # Send backlog so new connections see history
    history = await agora.get_all()
    for msg in history:
        await websocket.send_text(json.dumps(msg.model_dump(), ensure_ascii=False))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# --- REST API ---

class GoalRequest(BaseModel):
    goal: str
    agent_count: int = 2
    capabilities: list[str] = []
    spawn_planner: bool = True  # False 时不启动内部 PlannerAgent，由外部 Agent 承接分解


class TasksRequest(BaseModel):
    tasks: list[dict]
    goal_id: str | None = None
    goal: str = ""


class SpawnRequest(BaseModel):
    count: int = 1
    capabilities: list[str] = []


@app.post("/goal")
async def submit_goal(req: GoalRequest):
    goal_id = f"goal-{uuid.uuid4().hex[:8]}"

    await agora.publish(AgoraMessage(
        agent_id="system", type=MessageType.GOAL_RECEIVED,
        payload={"goal": req.goal, "goal_id": goal_id}, ts=time.time(),
    ))

    decompose_task = {
        "id": f"decompose-{goal_id}",
        "type": "decompose",
        "goal": req.goal,
        "goal_id": goal_id,
        "description": f"将目标分解为子任务：{req.goal}",
        "required_capabilities": ["planning"],
        "depends_on": [],
    }
    await task_queue.push([decompose_task])

    agents = []
    if req.spawn_planner:
        agents.append(runtime.spawn_planner())
    agents += [runtime.spawn(capabilities=req.capabilities) for _ in range(req.agent_count)]

    return {
        "goal_id": goal_id,
        "goal": req.goal,
        "agents": [a.agent_id for a in agents],
    }


@app.post("/tasks")
async def submit_tasks(req: TasksRequest):
    """直接提交已分解好的 Task Graph，跳过 LLM 分解步骤。
    可由外部 Planner Agent 或手动调用。"""
    goal_id = req.goal_id or f"goal-{uuid.uuid4().hex[:8]}"

    await task_queue.push(req.tasks)

    if req.tasks:
        await task_queue.register_goal(goal_id, req.goal, [t["id"] for t in req.tasks])
        await agora.publish(AgoraMessage(
            agent_id="system",
            type=MessageType.GOAL_DECOMPOSED,
            payload={"goal_id": goal_id, "goal": req.goal, "tasks": req.tasks},
            ts=time.time(),
        ))

    return {
        "goal_id": goal_id,
        "pushed": len(req.tasks),
        "tasks": [t["id"] for t in req.tasks],
    }


@app.post("/agents/spawn")
async def spawn_agents(req: SpawnRequest):
    agents = [runtime.spawn(capabilities=req.capabilities) for _ in range(req.count)]
    return {"agents": [a.agent_id for a in agents]}


@app.delete("/agents/{agent_id}")
async def stop_agent(agent_id: str):
    runtime.stop(agent_id)
    return {"stopped": agent_id}


@app.get("/agents")
async def list_agents():
    return runtime.status()


@app.get("/debug/tasks")
async def debug_tasks():
    result = {}
    for aid, t in runtime._asyncio_tasks.items():
        exc = t.exception() if t.done() else None
        result[aid] = {
            "done": t.done(),
            "cancelled": t.cancelled(),
            "exception": repr(exc) if exc else None,
        }
    return result


@app.get("/agora")
async def get_log():
    msgs = await agora.get_all()
    return [m.model_dump() for m in msgs]


@app.get("/tasks/pending")
async def pending_tasks():
    return {
        "pending": await task_queue.pending_count(),
        "ready": await task_queue.ready_count(),
        "waiting": await task_queue.waiting_count(),
    }


# --- External Agent API (/x/) ---
# These endpoints let any external process act as an AGORA agent
# without being an internal asyncio task.

class RegisterRequest(BaseModel):
    agent_id: str | None = None
    capabilities: list[str] = []


class TaskResultRequest(BaseModel):
    result: str


class TaskErrorRequest(BaseModel):
    error: str


@app.post("/x/agents/register")
async def ext_register(req: RegisterRequest):
    agent_id = req.agent_id or f"ext-{uuid.uuid4().hex[:6]}"
    runtime.registry.register(agent_id, req.capabilities)
    await agora.publish(AgoraMessage(
        agent_id=agent_id, type=MessageType.AGENT_JOINED,
        payload={"agent_id": agent_id, "capabilities": req.capabilities},
        ts=time.time(),
    ))
    return {"agent_id": agent_id}


@app.post("/x/agents/{agent_id}/claim")
async def ext_claim(agent_id: str):
    rec = runtime.registry._agents.get(agent_id)
    caps = rec.capabilities if rec else []
    task = await task_queue.claim(caps)
    if task:
        runtime.registry.touch(agent_id, current_task=task["id"], current_task_data=task)
        await agora.publish(AgoraMessage(
            agent_id=agent_id, type=MessageType.TASK_CLAIMED,
            payload={"task_id": task["id"], "description": task.get("description", "")},
            ts=time.time(),
        ))
    return {"task": task}


@app.post("/x/agents/{agent_id}/tasks/{task_id}/done")
async def ext_task_done(agent_id: str, task_id: str, req: TaskResultRequest):
    runtime.registry.clear_task(agent_id)
    await agora.publish(AgoraMessage(
        agent_id=agent_id, type=MessageType.TASK_DONE,
        payload={"task_id": task_id, "result": req.result},
        ts=time.time(),
    ))
    unblocked, completed_goals = await task_queue.mark_done(task_id)
    for t in unblocked:
        await agora.publish(AgoraMessage(
            agent_id="system", type=MessageType.TASK_UNBLOCKED,
            payload={"task_id": t["id"], "description": t.get("description", "")},
            ts=time.time(),
        ))
    for goal_id in completed_goals:
        await runtime._publish_goal_completed(goal_id)
    return {"ok": True, "unblocked": len(unblocked), "completed_goals": completed_goals}


@app.post("/x/agents/{agent_id}/tasks/{task_id}/failed")
async def ext_task_failed(agent_id: str, task_id: str, req: TaskErrorRequest):
    runtime.registry.clear_task(agent_id)
    await agora.publish(AgoraMessage(
        agent_id=agent_id, type=MessageType.TASK_FAILED,
        payload={"task_id": task_id, "error": req.error},
        ts=time.time(),
    ))
    failed_goals, cascaded = await task_queue.mark_failed(task_id)
    for ct in cascaded:
        await agora.publish(AgoraMessage(
            agent_id="system", type=MessageType.TASK_FAILED,
            payload={"task_id": ct["id"], "error": f"dependency failed: {task_id}"},
            ts=time.time(),
        ))
    for goal_id in failed_goals:
        await runtime._publish_goal_failed(goal_id, task_id)
    return {"ok": True, "cascaded": len(cascaded), "failed_goals": failed_goals}


@app.post("/x/agents/{agent_id}/heartbeat")
async def ext_heartbeat(agent_id: str):
    runtime.registry.touch(agent_id)
    rec = runtime.registry._agents.get(agent_id)
    return {"ok": True, "epoch": rec.epoch if rec else 0}


@app.delete("/x/agents/{agent_id}")
async def ext_leave(agent_id: str):
    runtime.registry.mark_stopped(agent_id)
    await agora.publish(AgoraMessage(
        agent_id=agent_id, type=MessageType.AGENT_LEFT,
        payload={"agent_id": agent_id},
        ts=time.time(),
    ))
    return {"ok": True}


# --- Arbitration API ---

class ProposeRequest(BaseModel):
    topic: str
    value: str
    proposer: str = "system"


class VoteRequest(BaseModel):
    proposal_id: str
    approve: bool


@app.get("/arbitration/leader")
async def get_leader():
    return {"leader": arbitration.current_leader()}


@app.get("/arbitration/proposals")
async def list_proposals():
    return arbitration.all_proposals()


@app.post("/arbitration/propose")
async def create_proposal(req: ProposeRequest):
    p = await arbitration.propose(req.topic, req.value, req.proposer)
    return p.to_dict()


@app.post("/arbitration/vote")
async def cast_vote(req: VoteRequest):
    return await arbitration.vote("system", req.proposal_id, req.approve)


# External agents vote via their own endpoint
@app.post("/x/agents/{agent_id}/vote")
async def ext_vote(agent_id: str, req: VoteRequest):
    return await arbitration.vote(agent_id, req.proposal_id, req.approve)


@app.delete("/reset")
async def reset():
    runtime.stop_all()
    # Delete all known keys plus any goal tracking keys
    goal_keys = await _r.keys("agora:goals:*")  # tasks + meta
    keys_to_del = ["agora:log", TASK_READY_KEY, TASK_WAITING_KEY, COMPLETED_KEY] + [
        k.decode() if isinstance(k, bytes) else k for k in goal_keys
    ]
    await _r.delete(*keys_to_del)
    runtime.agents.clear()
    runtime._asyncio_tasks.clear()
    runtime.registry.clear()
    arbitration.clear()
    return {"ok": True}


# Serve frontend — prefer built React app (dist/), fall back to legacy HTML
_base = os.path.join(os.path.dirname(__file__), "..", "frontend")
_dist = os.path.join(_base, "dist")
frontend_dir = _dist if os.path.isdir(_dist) else _base
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
