"""
scripts/demo.py — AGORA 端到端演示

自动完成完整流程：提交目标 → 等待所有任务完成/失败 → 打印结果摘要。
不依赖浏览器，命令行即可验证系统是否工作正常。

用法：
    # Mock LLM（无需 API Key）
    LLM_PROVIDER=mock python scripts/demo.py

    # 真实 Claude
    python scripts/demo.py

    # 自定义目标
    python scripts/demo.py --goal "解释什么是量子纠缠" --agents 2

    # 安静模式（只输出最终结果）
    python scripts/demo.py --quiet
"""

import asyncio
import argparse
import json
import time
import sys
import os
from urllib.request import urlopen, Request
from urllib.error import URLError

BASE_URL = os.getenv("AGORA_URL", "http://localhost:8000")
WS_URL = BASE_URL.replace("http", "ws") + "/ws"

RESET_AFTER = True   # 演示结束后自动重置（可用 --no-reset 关闭）


# ── HTTP 工具 ─────────────────────────────────────────────────────

def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = Request(f"{BASE_URL}{path}", data=data,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def delete(path: str) -> dict:
    req = Request(f"{BASE_URL}{path}", method="DELETE")
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get(path: str) -> dict:
    with urlopen(f"{BASE_URL}{path}", timeout=10) as r:
        return json.loads(r.read())


# ── WebSocket 监听 ────────────────────────────────────────────────

async def watch(goal_id: str, quiet: bool, timeout: float = 300.0) -> dict:
    """
    通过 WebSocket 监听 Agora 消息流，直到目标完成或失败。
    返回结果摘要字典。
    """
    try:
        import websockets
    except ImportError:
        print("  [提示] 安装 websockets 以获得实时输出：pip install websockets")
        return await _poll_fallback(goal_id, quiet, timeout)

    summary = {
        "goal_id": goal_id,
        "status": "unknown",
        "tasks_done": 0,
        "tasks_failed": 0,
        "task_results": {},
        "elapsed": 0.0,
    }
    start = time.time()

    async with websockets.connect(WS_URL) as ws:
        while True:
            elapsed = time.time() - start
            if elapsed > timeout:
                summary["status"] = "timeout"
                summary["elapsed"] = elapsed
                return summary

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            msg = json.loads(raw)
            mtype = msg.get("type", "")
            p = msg.get("payload", {})

            if not quiet:
                _print_msg(msg)

            if mtype == "TASK_DONE":
                summary["tasks_done"] += 1
                summary["task_results"][p.get("task_id", "?")] = p.get("result", "")

            elif mtype == "TASK_FAILED":
                summary["tasks_failed"] += 1

            elif mtype == "GOAL_COMPLETED" and p.get("goal_id") == goal_id:
                summary["status"] = "completed"
                summary["elapsed"] = time.time() - start
                return summary

            elif mtype == "GOAL_FAILED" and p.get("goal_id") == goal_id:
                summary["status"] = "failed"
                summary["elapsed"] = time.time() - start
                return summary


async def _poll_fallback(goal_id: str, quiet: bool, timeout: float) -> dict:
    """websockets 未安装时，轮询 /agora 端点。"""
    summary = {"goal_id": goal_id, "status": "unknown",
               "tasks_done": 0, "tasks_failed": 0, "task_results": {}, "elapsed": 0.0}
    start = time.time()
    seen: set[str] = set()

    while time.time() - start < timeout:
        await asyncio.sleep(2)
        msgs = get("/agora")
        for msg in msgs:
            mid = msg.get("id", "")
            if mid in seen:
                continue
            seen.add(mid)
            mtype = msg.get("type", "")
            p = msg.get("payload", {})

            if not quiet:
                _print_msg(msg)

            if mtype == "TASK_DONE":
                summary["tasks_done"] += 1
                summary["task_results"][p.get("task_id", "?")] = p.get("result", "")
            elif mtype == "TASK_FAILED":
                summary["tasks_failed"] += 1
            elif mtype == "GOAL_COMPLETED" and p.get("goal_id") == goal_id:
                summary["status"] = "completed"
                summary["elapsed"] = time.time() - start
                return summary
            elif mtype == "GOAL_FAILED" and p.get("goal_id") == goal_id:
                summary["status"] = "failed"
                summary["elapsed"] = time.time() - start
                return summary

    summary["elapsed"] = time.time() - start
    summary["status"] = "timeout"
    return summary


def _print_msg(msg: dict) -> None:
    mtype = msg.get("type", "")
    agent = (msg.get("agent_id") or "").replace("agent-", "")
    p = msg.get("payload", {})
    ts = time.strftime("%H:%M:%S", time.localtime(msg.get("ts", time.time())))

    COLOR = {
        "GOAL_RECEIVED":    "\033[35m",
        "GOAL_DECOMPOSED":  "\033[35m",
        "GOAL_COMPLETED":   "\033[32m",
        "GOAL_FAILED":      "\033[31m",
        "TASK_CLAIMED":     "\033[34m",
        "TASK_DONE":        "\033[32m",
        "TASK_FAILED":      "\033[31m",
        "TASK_UNBLOCKED":   "\033[36m",
        "AGENT_JOINED":     "\033[32m",
        "AGENT_LEFT":       "\033[90m",
        "EPOCH_START":      "\033[33m",
        "LEADER_ELECTED":   "\033[33m",
    }
    RESET = "\033[0m"
    color = COLOR.get(mtype, "\033[90m")

    # 摘要文字
    if mtype == "GOAL_RECEIVED":
        detail = str(p.get("goal", ""))[:60]
    elif mtype == "GOAL_DECOMPOSED":
        detail = f"{len(p.get('tasks', []))} tasks"
    elif mtype in ("GOAL_COMPLETED", "GOAL_FAILED"):
        detail = str(p.get("goal", ""))[:60]
    elif mtype == "TASK_CLAIMED":
        detail = f"[{p.get('task_id')}] {str(p.get('description',''))[:50]}"
    elif mtype == "TASK_DONE":
        detail = f"[{p.get('task_id')}] {str(p.get('result',''))[:60]}"
    elif mtype == "TASK_FAILED":
        retry = f" (attempt {p['retry_count']})" if p.get("retry_count") else ""
        detail = f"[{p.get('task_id')}] {p.get('error','')}{retry}"
    elif mtype == "EPOCH_START":
        detail = f"epoch {p.get('epoch')}  · {len(p.get('agents',[]))} agents"
    elif mtype == "LEADER_ELECTED":
        detail = f"leader: {str(p.get('leader','')).replace('agent-','')}"
    else:
        detail = ""

    print(f"  {ts}  {color}{mtype:<22}{RESET}  {agent:<10}  {detail}")


# ── 主流程 ────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="AGORA 端到端演示")
    parser.add_argument("--goal", default="用三句话解释什么是公共知识，以及它与互知的区别",
                        help="提交的目标（默认为示例目标）")
    parser.add_argument("--agents", type=int, default=2,
                        help="启动的内置 Agent 数量（默认 2）")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="等待超时秒数（默认 120）")
    parser.add_argument("--quiet", action="store_true",
                        help="安静模式，不打印每条消息")
    parser.add_argument("--no-reset", dest="reset", action="store_false",
                        help="演示结束后不自动重置系统")
    args = parser.parse_args()

    # 检查后端是否在运行
    try:
        get("/tasks/pending")
    except URLError:
        print(f"\n❌  无法连接到 {BASE_URL}")
        print("    请先运行：make dev\n")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  AGORA 端到端演示")
    print(f"{'='*60}")
    print(f"  目标：{args.goal}")
    print(f"  Agent 数量：{args.agents}")
    print(f"{'='*60}\n")

    # 提交目标
    print("▶  提交目标...")
    resp = post("/goal", {"goal": args.goal, "agent_count": args.agents})
    goal_id = resp["goal_id"]
    print(f"   goal_id：{goal_id}")
    print(f"   agents：{', '.join(resp.get('agents', []))}")
    print()

    # 监听直到完成
    if not args.quiet:
        print("▶  实时消息流：\n")

    summary = await watch(goal_id, quiet=args.quiet, timeout=args.timeout)

    # 打印结果摘要
    elapsed = summary["elapsed"]
    status = summary["status"]
    print(f"\n{'='*60}")
    if status == "completed":
        print(f"  ✅  目标完成  ({elapsed:.1f}s)")
    elif status == "failed":
        print(f"  ❌  目标失败  ({elapsed:.1f}s)")
    elif status == "timeout":
        print(f"  ⏱   超时  ({elapsed:.1f}s)")
    print(f"  任务完成：{summary['tasks_done']}  失败：{summary['tasks_failed']}")

    if summary["task_results"] and not args.quiet:
        print(f"\n  任务结果：")
        for tid, result in summary["task_results"].items():
            print(f"  [{tid}] {result[:120]}")
    print(f"{'='*60}\n")

    # 重置
    if args.reset:
        delete("/reset")
        print("  系统已重置（--no-reset 可跳过）\n")

    sys.exit(0 if status == "completed" else 1)


if __name__ == "__main__":
    asyncio.run(main())
