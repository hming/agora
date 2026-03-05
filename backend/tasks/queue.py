import json
import redis.asyncio as redis

TASK_READY_KEY   = "agora:tasks:ready"    # List  — tasks ready to claim
TASK_WAITING_KEY = "agora:tasks:waiting"  # Hash  — task_id → JSON, waiting on deps
COMPLETED_KEY    = "agora:tasks:completed"  # Set — completed task IDs
GOAL_TASKS_KEY   = "agora:goals:tasks:{}"  # Set  — remaining task_ids per goal
GOAL_META_KEY    = "agora:goals:meta:{}"   # Hash — goal metadata (goal text etc.)


class TaskQueue:
    def __init__(self, r: redis.Redis):
        self.r = r

    async def register_goal(self, goal_id: str, goal_text: str, task_ids: list[str]) -> None:
        """Register a goal and its task_ids for completion tracking."""
        key = GOAL_TASKS_KEY.format(goal_id)
        meta_key = GOAL_META_KEY.format(goal_id)
        if task_ids:
            await self.r.sadd(key, *task_ids)
        await self.r.hset(meta_key, mapping={"goal": goal_text, "total": len(task_ids)})

    async def push(self, tasks: list[dict]) -> None:
        """Push tasks, holding back any whose dependencies are not yet met."""
        for task in tasks:
            deps = [d for d in task.get("depends_on", []) if d]
            if not deps:
                await self.r.rpush(TASK_READY_KEY, json.dumps(task, ensure_ascii=False))
            else:
                await self.r.hset(TASK_WAITING_KEY, task["id"], json.dumps(task, ensure_ascii=False))

    # Lua script: atomically find & remove first task whose required_capabilities
    # are all satisfied by the agent's capabilities (empty reqs = open to all).
    _CLAIM_SCRIPT = """
local key = KEYS[1]
local tasks = redis.call('LRANGE', key, 0, -1)
local caps_set = {}
for i = 1, #ARGV do caps_set[ARGV[i]] = true end
for _, raw in ipairs(tasks) do
    local ok = true
    local task = cjson.decode(raw)
    local reqs = task['required_capabilities']
    if reqs and #reqs > 0 then
        for _, r in ipairs(reqs) do
            if not caps_set[r] then ok = false; break end
        end
    end
    if ok then
        redis.call('LREM', key, 1, raw)
        return raw
    end
end
return nil
"""

    async def claim(self, capabilities: list[str] | None = None) -> dict | None:
        """Atomically claim the next ready task matching the agent's capabilities."""
        caps = capabilities or []
        raw = await self.r.eval(self._CLAIM_SCRIPT, 1, TASK_READY_KEY, *caps)
        if raw is None:
            return None
        return json.loads(raw)

    async def mark_done(self, task_id: str) -> tuple[list[dict], list[str]]:
        """
        Mark a task as completed.
        Returns (unblocked_tasks, completed_goal_ids).
        Callers should publish TASK_UNBLOCKED for each unblocked task,
        and GOAL_COMPLETED for each completed goal.
        """
        await self.r.sadd(COMPLETED_KEY, task_id)
        unblocked = await self._unblock_waiting()
        completed_goals = await self._check_goal_completion(task_id)
        return unblocked, completed_goals

    async def _check_goal_completion(self, task_id: str) -> list[str]:
        """Remove task_id from all goal sets; return IDs of goals that just completed."""
        # Scan all goal tracking keys
        completed = []
        cursor = 0
        pattern = "agora:goals:tasks:*"
        while True:
            cursor, keys = await self.r.scan(cursor, match=pattern, count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                removed = await self.r.srem(key_str, task_id)
                if removed:
                    remaining = await self.r.scard(key_str)
                    if remaining == 0:
                        goal_id = key_str.split("agora:goals:tasks:")[-1]
                        completed.append(goal_id)
            if cursor == 0:
                break
        return completed

    async def mark_failed(self, task_id: str) -> tuple[list[str], list[dict]]:
        """
        将任务标记为终态失败（重试耗尽），并级联清理所有依赖它的等待任务。

        Returns (failed_goal_ids, cascaded_tasks)：
          - failed_goal_ids：因此进入失败状态的 goal id 列表
          - cascaded_tasks：从 TASK_WAITING 中清除的下游任务列表（供调用方发 TASK_FAILED）
        """
        # BFS：找出所有需要级联失败的任务
        newly_failed = {task_id}
        all_cascaded: list[dict] = []

        while newly_failed:
            # 扫描 TASK_WAITING，找依赖了 newly_failed 中任意任务的任务
            waiting_raw = await self.r.hgetall(TASK_WAITING_KEY)
            next_wave: set[str] = set()
            for tid_b, raw_b in waiting_raw.items():
                tid = tid_b.decode() if isinstance(tid_b, bytes) else tid_b
                raw = raw_b.decode() if isinstance(raw_b, bytes) else raw_b
                task = json.loads(raw)
                deps = set(task.get("depends_on", []))
                if deps & newly_failed:  # 有任意依赖已失败
                    await self.r.hdel(TASK_WAITING_KEY, tid)
                    all_cascaded.append(task)
                    next_wave.add(tid)
            newly_failed = next_wave

        # 从目标跟踪 Set 中移除所有失败任务（原始 + 级联）
        all_failed_ids = {task_id} | {t["id"] for t in all_cascaded}
        failed_goals: list[str] = []
        cursor = 0
        pattern = "agora:goals:tasks:*"
        while True:
            cursor, keys = await self.r.scan(cursor, match=pattern, count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                removed_total = sum([
                    await self.r.srem(key_str, fid) for fid in all_failed_ids
                ])
                # 只有实际移除了任务、且 Set 现已空，才算 goal 失败
                if removed_total > 0:
                    remaining = await self.r.scard(key_str)
                    if remaining == 0:
                        goal_id = key_str.split("agora:goals:tasks:")[-1]
                        if goal_id not in failed_goals:
                            failed_goals.append(goal_id)
            if cursor == 0:
                break

        return failed_goals, all_cascaded

    async def get_goal_meta(self, goal_id: str) -> dict:
        meta_key = GOAL_META_KEY.format(goal_id)
        raw = await self.r.hgetall(meta_key)
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }

    async def _unblock_waiting(self) -> list[dict]:
        """Move waiting tasks whose all deps are now completed into the ready queue."""
        waiting_raw = await self.r.hgetall(TASK_WAITING_KEY)
        if not waiting_raw:
            return []

        unblocked = []
        for tid_b, raw_b in waiting_raw.items():
            tid = tid_b.decode() if isinstance(tid_b, bytes) else tid_b
            raw = raw_b.decode() if isinstance(raw_b, bytes) else raw_b
            task = json.loads(raw)
            deps = [d for d in task.get("depends_on", []) if d]

            if not deps:
                # Shouldn't happen, but handle gracefully
                await self.r.hdel(TASK_WAITING_KEY, tid)
                await self.r.rpush(TASK_READY_KEY, json.dumps(task, ensure_ascii=False))
                unblocked.append(task)
                continue

            # Check all deps in one round-trip
            results = await self.r.smismember(COMPLETED_KEY, *deps)
            if all(results):
                await self.r.hdel(TASK_WAITING_KEY, tid)
                await self.r.rpush(TASK_READY_KEY, json.dumps(task, ensure_ascii=False))
                unblocked.append(task)

        return unblocked

    async def requeue(self, task: dict) -> None:
        """把任务放回 ready 队列头部（优先处理）。用于 agent 失效时释放 Lease。"""
        await self.r.lpush(TASK_READY_KEY, json.dumps(task, ensure_ascii=False))

    MAX_RETRIES = 3

    async def try_requeue(self, task: dict) -> bool:
        """
        失败重试：retry_count+1 后放回队列头部。
        Returns True 如果已重新入队，False 如果已超过 max_retries。
        """
        task = dict(task)
        retry_count = task.get("retry_count", 0) + 1
        max_retries = task.get("max_retries", self.MAX_RETRIES)
        if retry_count > max_retries:
            return False
        task["retry_count"] = retry_count
        await self.r.lpush(TASK_READY_KEY, json.dumps(task, ensure_ascii=False))
        return True

    async def pending_count(self) -> int:
        ready = await self.r.llen(TASK_READY_KEY)
        waiting = await self.r.hlen(TASK_WAITING_KEY)
        return ready + waiting

    async def ready_count(self) -> int:
        return await self.r.llen(TASK_READY_KEY)

    async def waiting_count(self) -> int:
        return await self.r.hlen(TASK_WAITING_KEY)
