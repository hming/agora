"""
TaskQueue 单元测试

使用 fakeredis 模拟 Redis，不依赖真实服务。
覆盖：任务入队/claim、DAG 解锁、重试、级联失败、目标完成/失败检测。
"""

import pytest
import fakeredis
import fakeredis.aioredis
from tasks.queue import TaskQueue


@pytest.fixture
async def q():
    r = fakeredis.aioredis.FakeRedis(decode_responses=False, lua_modules={"cjson"})
    return TaskQueue(r)


# ── 基础入队与 claim ──────────────────────────────────────────────

async def test_push_and_claim(q):
    await q.push([{"id": "t1", "description": "do something", "depends_on": []}])
    task = await q.claim()
    assert task is not None
    assert task["id"] == "t1"


async def test_claim_empty_returns_none(q):
    assert await q.claim() is None


async def test_push_multiple_fifo(q):
    tasks = [
        {"id": "t1", "description": "first", "depends_on": []},
        {"id": "t2", "description": "second", "depends_on": []},
    ]
    await q.push(tasks)
    assert (await q.claim())["id"] == "t1"
    assert (await q.claim())["id"] == "t2"


# ── 能力路由 ──────────────────────────────────────────────────────

async def test_claim_with_matching_capability(q):
    await q.push([{"id": "t1", "description": "x", "depends_on": [],
                   "required_capabilities": ["code"]}])
    assert await q.claim(["code"]) is not None


async def test_claim_skips_unmatched_capability(q):
    await q.push([{"id": "t1", "description": "x", "depends_on": [],
                   "required_capabilities": ["code"]}])
    assert await q.claim(["search"]) is None


async def test_claim_open_task_by_any_agent(q):
    await q.push([{"id": "t1", "description": "x", "depends_on": []}])
    assert await q.claim(["code"]) is not None


# ── DAG 依赖解锁 ──────────────────────────────────────────────────

async def test_dependent_task_held_until_dep_done(q):
    await q.push([
        {"id": "t1", "description": "root", "depends_on": []},
        {"id": "t2", "description": "child", "depends_on": ["t1"]},
    ])
    # t2 还在等待
    assert await q.waiting_count() == 1
    assert (await q.claim())["id"] == "t1"

    # 完成 t1，t2 应解锁
    unblocked, _ = await q.mark_done("t1")
    assert len(unblocked) == 1
    assert unblocked[0]["id"] == "t2"

    assert (await q.claim())["id"] == "t2"


async def test_multi_dep_task_waits_for_all(q):
    await q.push([
        {"id": "t1", "description": "a", "depends_on": []},
        {"id": "t2", "description": "b", "depends_on": []},
        {"id": "t3", "description": "c", "depends_on": ["t1", "t2"]},
    ])
    await q.mark_done("t1")
    assert await q.waiting_count() == 1  # t3 仍在等 t2

    unblocked, _ = await q.mark_done("t2")
    assert any(t["id"] == "t3" for t in unblocked)


# ── 目标完成检测 ───────────────────────────────────────────────────

async def test_goal_completed_when_all_tasks_done(q):
    await q.push([
        {"id": "t1", "description": "a", "depends_on": []},
        {"id": "t2", "description": "b", "depends_on": []},
    ])
    await q.register_goal("goal-1", "test goal", ["t1", "t2"])

    _, goals = await q.mark_done("t1")
    assert goals == []  # 还剩 t2

    _, goals = await q.mark_done("t2")
    assert "goal-1" in goals


async def test_goal_not_completed_until_all_done(q):
    await q.push([{"id": "t1", "description": "a", "depends_on": []},
                  {"id": "t2", "description": "b", "depends_on": []}])
    await q.register_goal("goal-1", "test goal", ["t1", "t2"])
    _, goals = await q.mark_done("t1")
    assert goals == []


# ── 重试机制 ──────────────────────────────────────────────────────

async def test_try_requeue_increments_retry_count(q):
    task = {"id": "t1", "description": "x", "depends_on": []}
    requeued = await q.try_requeue(task)
    assert requeued is True
    claimed = await q.claim()
    assert claimed["retry_count"] == 1


async def test_try_requeue_respects_max_retries(q):
    task = {"id": "t1", "description": "x", "depends_on": [],
            "retry_count": 3, "max_retries": 3}
    requeued = await q.try_requeue(task)
    assert requeued is False
    assert await q.claim() is None  # 没有入队


async def test_try_requeue_default_max_retries(q):
    task = {"id": "t1", "description": "x", "depends_on": []}
    # 默认 MAX_RETRIES=3，前三次成功，第四次失败
    for i in range(1, 4):
        t = dict(task, retry_count=i - 1)
        assert await q.try_requeue(t) is True
        await q.claim()  # 消耗掉，避免干扰

    t = dict(task, retry_count=3)
    assert await q.try_requeue(t) is False


# ── 级联失败 ──────────────────────────────────────────────────────

async def test_mark_failed_cascades_to_dependents(q):
    await q.push([
        {"id": "t1", "description": "root", "depends_on": []},
        {"id": "t2", "description": "child", "depends_on": ["t1"]},
        {"id": "t3", "description": "grandchild", "depends_on": ["t2"]},
    ])
    await q.register_goal("goal-1", "test goal", ["t1", "t2", "t3"])

    # t1 彻底失败
    failed_goals, cascaded = await q.mark_failed("t1")

    cascaded_ids = {t["id"] for t in cascaded}
    assert "t2" in cascaded_ids
    assert "t3" in cascaded_ids
    assert "goal-1" in failed_goals
    assert await q.waiting_count() == 0  # TASK_WAITING 已清空


async def test_mark_failed_no_cascade_without_dependents(q):
    await q.push([{"id": "t1", "description": "x", "depends_on": []}])
    await q.register_goal("goal-1", "g", ["t1"])

    failed_goals, cascaded = await q.mark_failed("t1")
    assert cascaded == []
    assert "goal-1" in failed_goals


async def test_mark_failed_does_not_affect_independent_tasks(q):
    await q.push([
        {"id": "t1", "description": "a", "depends_on": []},
        {"id": "t2", "description": "b", "depends_on": []},  # 独立任务
    ])
    await q.register_goal("goal-1", "g", ["t1", "t2"])

    failed_goals, cascaded = await q.mark_failed("t1")
    # t2 不依赖 t1，不应被级联
    assert all(t["id"] != "t2" for t in cascaded)
    # goal 还有 t2 未完成/失败，不应被标为 failed
    assert failed_goals == []


# ── 目标失败检测 ───────────────────────────────────────────────────

async def test_goal_failed_only_when_set_becomes_empty(q):
    await q.push([
        {"id": "t1", "description": "a", "depends_on": []},
        {"id": "t2", "description": "b", "depends_on": []},
    ])
    await q.register_goal("goal-1", "g", ["t1", "t2"])

    # t1 失败，t2 还在 ready queue
    failed_goals, _ = await q.mark_failed("t1")
    assert failed_goals == []  # goal 还有 t2

    # t2 也失败，goal 这才失败
    failed_goals, _ = await q.mark_failed("t2")
    assert "goal-1" in failed_goals


# ── pending / ready / waiting counts ─────────────────────────────

async def test_counts(q):
    await q.push([
        {"id": "t1", "description": "a", "depends_on": []},
        {"id": "t2", "description": "b", "depends_on": ["t1"]},
    ])
    assert await q.ready_count() == 1
    assert await q.waiting_count() == 1
    assert await q.pending_count() == 2
