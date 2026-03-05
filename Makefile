.PHONY: redis dev install reset frontend ui test demo cc-workers cc-goal

redis:
	docker compose up -d redis

install:
	cd backend && pip install -e ".[test]"
	cd frontend && npm install

dev:
	cd backend && eval "$$(pyenv init -)" && python3 -m uvicorn main:app --reload --port 8000

# 单独开发前端（热重载，代理到 backend:8000）
ui:
	cd frontend && npm run dev

# 构建 React 前端到 frontend/dist/（backend 自动使用）
frontend:
	cd frontend && npm run build

reset:
	curl -X DELETE http://localhost:8000/reset

test:
	cd backend && pytest tests/ -v

demo:
	LLM_PROVIDER=mock python3 scripts/demo.py

# 启动 N 个 Claude Code Worker（默认 3 个）
# 可选参数：N=5  PLANNER=1  CAPS="code search"
# 示例：make cc-workers N=4 PLANNER=1
cc-workers:
	@N=$(or $(N),3); \
	echo "启动 $$N 个 Claude Code Worker...（Ctrl+C 停止全部）"; \
	trap 'kill 0' INT TERM; \
	for i in $$(seq 1 $$N); do \
	  python3 scripts/cc_worker.py \
	    $(if $(PLANNER),--planner,) \
	    $(if $(CAPS),--capabilities $(CAPS),) & \
	done; \
	wait

# 提交目标给 AGORA，由 Claude Code Worker 执行（不启动内部 Worker）
# 示例：make cc-goal GOAL="调研并总结 AGORA 架构的优缺点"
cc-goal:
	@test -n "$(GOAL)" || (echo "用法: make cc-goal GOAL='你的目标'" && exit 1)
	curl -s -X POST http://localhost:8000/goal \
	  -H "Content-Type: application/json" \
	  -d '{"goal": "$(GOAL)", "agent_count": 0, "spawn_planner": $(if $(PLANNER),false,true)}' \
	  | python3 -m json.tool
