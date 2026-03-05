#!/usr/bin/env python3
"""
cc_worker.py — 以 Claude Code 为执行引擎的 AGORA 外部 Agent

每个任务通过 `claude -p` 调用 Claude Code 执行，结果上报回 AGORA。
支持普通任务执行，以及带 --planner 选项后承接 decompose 任务。

用法：
    python scripts/cc_worker.py                      # 普通 worker
    python scripts/cc_worker.py --planner            # 同时承接分解任务
    python scripts/cc_worker.py --capabilities code search
    python scripts/cc_worker.py --agent-id my-agent-1
    python scripts/cc_worker.py --url http://remote:8000
"""

import asyncio
import json
import logging
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sdk", "python"))
from agora_sdk import AgoraAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cc_worker")

AGORA_URL = os.getenv("AGORA_URL", "http://localhost:8000")

WORKER_PROMPT = """你是 AGORA 多 Agent 系统中的一个执行 Agent。
请独立完成下面分配给你的任务，给出具体、可用的结果。
不要提问，自行做出合理假设。"""

PLANNER_PROMPT = """你是 AGORA 多 Agent 系统中的规划 Agent。
请将下面的目标分解为具体的、可并行执行的子任务。

输出格式要求——只输出 JSON 数组，不要有任何说明文字：
[
  {"id": "task_1", "description": "...", "depends_on": []},
  {"id": "task_2", "description": "...", "depends_on": ["task_1"]}
]

规则：
- id 用 task_1, task_2, ... 命名
- 尽量让任务可并行（depends_on 尽量少）
- 每个任务描述清晰、可独立执行"""


async def run_claude(prompt: str, system: str) -> str:
    """调用 claude -p 执行任务，返回输出文本。"""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", f"{system}\n\n{prompt}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip() or f"claude 退出码 {proc.returncode}"
        raise RuntimeError(err)
    return stdout.decode().strip()


async def make_handler(agent: AgoraAgent, is_planner: bool):
    """构造任务处理函数。"""

    async def handler(task: dict) -> str:
        task_type = task.get("type")

        # decompose 任务：分解目标并提交子任务
        if task_type == "decompose" and is_planner:
            goal = task["goal"]
            goal_id = task["goal_id"]

            log.info("[planner] 开始分解目标: %s", goal[:80])
            raw = await run_claude(f"目标：{goal}", PLANNER_PROMPT)

            # 解析 JSON
            start, end = raw.find("["), raw.rfind("]") + 1
            if start == -1 or end <= start:
                raise RuntimeError(f"分解结果不是合法 JSON 数组: {raw[:200]}")
            subtasks = json.loads(raw[start:end])

            # 提交子任务给 AGORA
            import httpx
            async with httpx.AsyncClient() as http:
                r = await http.post(
                    f"{agent.base_url}/tasks",
                    json={"goal_id": goal_id, "goal": goal, "tasks": subtasks},
                    timeout=30,
                )
                r.raise_for_status()

            log.info("[planner] 分解完成，提交 %d 个子任务", len(subtasks))
            return f"分解为 {len(subtasks)} 个子任务"

        # 普通任务：直接执行
        desc = task.get("description", str(task))
        log.info("[worker] 执行任务: %s", desc[:80])
        result = await run_claude(f"任务：{desc}", WORKER_PROMPT)
        return result

    return handler


async def main():
    parser = argparse.ArgumentParser(description="Claude Code AGORA Worker")
    parser.add_argument("--url", default=AGORA_URL, help="AGORA 服务地址")
    parser.add_argument("--capabilities", nargs="*", default=[], help="声明能力")
    parser.add_argument("--agent-id", default=None, help="指定 agent ID")
    parser.add_argument("--planner", action="store_true", help="同时承接 decompose 任务")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()

    capabilities = args.capabilities or []
    if args.planner and "planning" not in capabilities:
        capabilities = ["planning"] + capabilities

    agent = AgoraAgent(
        base_url=args.url,
        capabilities=capabilities,
        agent_id=args.agent_id,
        poll_interval=args.poll_interval,
    )

    mode = "planner+worker" if args.planner else "worker"
    print(f"\nClaude Code AGORA Agent 启动 [{mode}]")
    print(f"  服务地址：{args.url}")
    print(f"  能力：{capabilities or '全部'}")
    print("  按 Ctrl+C 停止\n")

    handler = await make_handler(agent, args.planner)
    try:
        await agent.run(handler)
    except KeyboardInterrupt:
        agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
