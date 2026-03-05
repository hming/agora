# AGORA：去中心化多 AI Agent 协调系统设计

## 定位：协调基础设施，而非 Agent 框架

**AGORA 不是一个 Agent 框架，它是 Agent 之间的协调基础设施。**

| 维度 | Agent 框架（LangGraph/AutoGen/CrewAI）| AGORA 基础设施 |
|------|--------------------------------------|---------------|
| 核心关注 | 如何构建 Agent | Agent 之间如何协调 |
| Agent 耦合 | Agent 在框架内定义 | Agent 是外部客户端，自带 LLM |
| 中心节点 | 有（Orchestrator/Supervisor） | 无（广场是日志，不是调度者）|
| 互操作性 | 框架内部封闭 | 任何语言、任何模型均可接入 |
| 智能所在 | 框架层 + Agent 层 | 纯 Agent 层，基础设施不含 LLM |
| 类比 | Rails / Django | Kafka / PostgreSQL |

**类比 Kafka**：Kafka 不关心谁是生产者、谁是消费者、消息的业务含义是什么。
AGORA 不关心 Agent 用什么模型、怎么实现、目标是什么——它只保证协调的正确性。

---

## 核心洞见：协调问题是公共知识问题

《理性的仪式》的根本命题：

> **协调失败的根源不是"缺少信息"，而是"缺少公共知识"。**

**互知（Mutual Knowledge）** 与 **公共知识（Common Knowledge）** 的区别：

| 层次 | 含义 |
|------|------|
| 互知 | A 知道 X，B 知道 X |
| 公共知识 | A 知道 X，B 知道 X，A 知道 B 知道 X，B 知道 A 知道 X，A 知道 B 知道 A 知道 X…… |

Gossip 协议只能产生互知，不能产生公共知识。
这是纯 Gossip 系统在协调压力下失败的根本原因。

Chwe 的结论：**仪式（Ritual）是人类社会低成本生产公共知识的技术。**
公开聚集、可观察的参与、全员可见的确认——这就是仪式的结构。

---

## 系统命名

**AGORA**（Adaptive Group Orchestration via Ritual Anchors）

取名自古希腊"广场"（αγορά）——城邦公民公开集会、共同见证的场所。
公共知识在广场上产生，而不在私下传递中产生。

---

## 架构总览

```
  外部 Agent 进程（用户自带，任意语言/模型）
┌──────────────────────────────────────────────────────────────┐
│  [Agent A: GPT-4]  [Agent B: Claude]  [Agent C: Llama]  ...  │
│       │  Python SDK        │  Node SDK       │  REST API      │
└───────┼────────────────────┼─────────────────┼───────────────┘
        │   WebSocket / HTTP │                 │
════════╪════════════════════╪═════════════════╪══════════════
        │      AGORA 基础设施（本系统边界）     │
        ▼                    ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    AGORA Protocol Gateway                    │
│         JOIN · CLAIM_TASK · PUBLISH_RESULT · ACK            │
├─────────────────────────────────────────────────────────────┤
│  Agent Registry  │  Task Graph Engine  │  Epoch Scheduler   │
│  （能力 + 心跳）  │  （DAG 依赖调度）    │  （仪式触发）       │
├─────────────────────────────────────────────────────────────┤
│               Layer 3：仲裁层（稀有路径）                    │
│         Leader Election → Threshold → Consensus             │
├─────────────────────────────────────────────────────────────┤
│               Layer 2：任务层                               │
│            Lock/Lease → 按能力路由 → Market/Auction          │
├─────────────────────────────────────────────────────────────┤
│               Layer 1：节律层（Epoch）                       │
│      工作期（自治） ──→ 仪式期（广场同步）                   │
├─────────────────────────────────────────────────────────────┤
│       Layer 0：广场（Agora）—— 公共知识层                    │
│         Append-Only 公共日志，所有 Agent 可见                │
└─────────────────────────────────────────────────────────────┘
        │  Redis Streams（当前实现）
        │  Kafka / NATS（生产扩展选项）
```

**系统边界说明**：
- AGORA 基础设施边界内：协调机制、日志、任务调度、Epoch、仲裁
- AGORA 基础设施边界外：Agent 的 LLM 选型、Agent 的实现语言、目标的业务含义、任务的拆解逻辑

---

## AGORA Protocol

Agent 通过标准化协议接入广场，协议与语言/模型无关。

### 连接握手

```
Client → Server:  JOIN { agent_id, capabilities: ["code", "search", "write"], version: "1.0" }
Server → Client:  WELCOME { epoch: 5, peers: ["agent-abc", "agent-def"] }
```

### 核心消息类型（Agent → 广场）

| 消息 | 触发时机 | 必填字段 |
|------|---------|---------|
| `JOIN` | Agent 启动时 | `agent_id`, `capabilities` |
| `CLAIM_TASK` | 领取任务后 | `task_id` |
| `PUBLISH_RESULT` | 任务完成时 | `task_id`, `result` |
| `REPORT_FAILURE` | 任务失败时 | `task_id`, `error` |
| `STATE_PUBLISH` | Epoch 仪式期 | `epoch`, `peers` |
| `ACK` | 确认 peer 状态 | `epoch`, `ack_target` |
| `LEAVE` | Agent 退出时 | `agent_id` |

### 核心消息类型（广场 → Agent）

| 消息 | 触发时机 |
|------|---------|
| `TASK_AVAILABLE` | 新任务可认领，附 `capabilities` 过滤 |
| `TASK_UNBLOCKED` | 依赖任务完成，阻塞解除 |
| `EPOCH_START` | 新 Epoch 开始，触发仪式期 |
| `PEER_UPDATE` | 其他 Agent 加入/离开 |

### 传输层

- **当前实现**：WebSocket 长连接（JSON）
- **生产选项**：NATS JetStream、gRPC 双向流
- **任务提交**：HTTP REST（`POST /tasks`）接受 Task Graph JSON

---

## Agent Registry

Agent Registry 追踪所有已连接 Agent 的元数据，支持按能力路由任务。

### Agent 记录结构

```json
{
  "agent_id": "agent-abc123",
  "capabilities": ["code_generation", "web_search", "data_analysis"],
  "status": "running",
  "current_task": "task-42",
  "epoch": 7,
  "last_heartbeat": 1709500000
}
```

### 能力路由

任务定义时可声明所需能力：

```json
{
  "id": "task-42",
  "description": "搜索并汇总最新论文",
  "required_capabilities": ["web_search"],
  "depends_on": []
}
```

广场在 `TASK_AVAILABLE` 广播时，仅通知声明了匹配能力的 Agent。
无能力声明的任务对所有 Agent 可见（向后兼容）。

### 心跳与失效检测

Agent 每 10 秒发送心跳（或通过 WebSocket keepalive 隐式心跳）。
超过 3 个心跳周期（30 秒）未响应的 Agent 被标记为 `inactive`，
其持有的任务 Lease 自动释放，广场广播 `AGENT_LEFT`。

---

## 应用层 vs 基础设施层

**以下功能不属于 AGORA 基础设施核心，属于应用层：**

| 功能 | 应用层实现 | 备注 |
|------|-----------|------|
| 目标拆解（Goal Decomposition） | PlannerAgent 或用户侧 Agent | 基础设施接受已拆解的 Task Graph |
| LLM 调用 | 每个 Agent 自行管理 | 基础设施不含任何 LLM |
| 任务结果聚合 | 聚合 Agent 订阅 Agora 日志 | 基础设施只存储原始结果 |
| 业务逻辑 | 完全在 Agent 侧 | 基础设施只关心协调正确性 |

**任务提交三条路径：**

| 路径 | 方式 | 适用场景 |
|------|------|---------|
| Path A | `POST /goal` → 内部 PlannerAgent 自动分解 | 快速开始、演示 |
| Path B | `POST /goal {spawn_planner:false}` → 外部 Agent claim decompose 任务 → `POST /tasks` | 外部 LLM 做规划 |
| Path C | 直接 `POST /tasks` 提交 Task Graph | 手动分解、程序化提交 |

`GoalDecomposer` 已降级为 PlannerAgent 内部工具，`POST /tasks` 是面向外部的标准接口。

---

## Layer 0：广场（公共知识层）

**这是整个系统的基础设施，也是最关键的设计决策。**

广场是一个 **公开的、可追加的共享日志**：
- 任何 Agent 的写入对所有 Agent 可见
- 读取者列表本身是公开的（谁在监听，所有人知道）
- Agent 收到消息后必须公开 ACK

实现载体可以是：Kafka Topic、Redis Streams、共享数据库的 event log。

**为何这能产生公共知识？**

```
Agent A 向广场发布状态 S
→ Agent B 收到 S，在广场公开 ACK
→ Agent C 收到 S，在广场公开 ACK
→ Agent A 看到所有 ACK
→ Agent B 看到 Agent A 和 C 的 ACK
→ 无限递归闭合：公共知识达成
```

这正是 Chwe 描述的仪式结构：**公开场合 + 可观察的参与 + 全员可见的确认**。

---

## Layer 1：节律层（Epoch）

时间划分为固定长度的 **Epoch（纪元）**。每个 Epoch 分两个阶段：

### 工作期（Work Phase）

- Agent 自主执行任务
- 使用本地缓存的上一 Epoch 状态作为基准（Sticky Convention，机制 #6）
- 无需实时协调，成本接近零

### 仪式期（Ritual Phase）—— Epoch 边界

这是产生公共知识的"仪式"时刻：

```
1. 所有 Agent 向广场发布本 Epoch 的状态摘要
2. 所有 Agent 公开 ACK 其他 Agent 的状态
3. 确定性规则解决任何冲突（见下）
4. 新 Epoch 状态成为公共知识
5. 开始下一个工作期
```

**确定性冲突解决规则（无需投票）：**
- 版本号更高者优先
- 版本号相同：Agent ID 哈希最小者优先
- 保证所有 Agent 独立运行相同规则，得出相同结论

**节律设计原则（Chwe）：**
仪式必须有可预测的节奏。Agent 知道"何时"会有仪式，降低不确定性，减少防御性行为。

---

## Layer 2：任务层（环境仲裁）

工作期内的任务分配，完全通过环境仲裁，**无需 Agent 间直接协调**：

### 正常路径：Lock/Lease（机制 #11）

```
任务发布到广场
→ Agent 原子性申请 Lease（TTL = 工作期长度）
→ 获得 Lease 的 Agent 执行任务
→ 执行结果发布广场
→ 未获得的 Agent 继续找下一个任务
```

Lock 是"环境即裁决者"的实现：没有 Agent 需要说服其他 Agent，环境直接判定。

### 降级路径：Market/Auction（机制 #12）

当任务超时无人认领（所有 Agent 忙碌）时：
- 任务广播竞价请求到广场
- Agent 报出自身当前负载（容量出价）
- 出价最低负载者获得任务

市场价格成为协调信号，无需中心调度。

---

## Layer 3：仲裁层（仅在真实冲突时触发）

**90% 的场景 Layer 1 + Layer 2 已足够，仲裁层是稀有路径。**

### 升级顺序

```
Level 0: 显著焦点（Focal Point）
  └─ 是否存在"明显正确"的答案？（机制 #7）
  └─ 成本：零

Level 1: 临时领导者选举（机制 #2）
  └─ 针对该决策选出一个短期权威
  └─ 使用确定性规则选举（无需投票轮次）：当前活跃 Agent 中 ID 最小者
  └─ 成本：O(n) 一轮广场广播

Level 2: 门限共识（机制 #4）
  └─ 需要 ≥ ⌈n/2⌉+1 个 Agent 签名
  └─ 适用于领导者不可达的情况
  └─ 成本：O(n) 消息

Level 3: 多数共识（机制 #3）
  └─ 完整 Raft/Paxos 流程
  └─ 仅用于系统级状态变更（如 Agent 加入/退出）
  └─ 成本：O(n log n)
```

**关键设计原则**：仲裁层的每一次决策结果，必须发布到广场，产生公共知识。
否则"仲裁结果"只是互知，无法真正终止争议。

---

## 失效处理

| 失效场景 | 响应机制 |
|----------|----------|
| Agent 宕机 | Sticky Convention 继续；下一 Epoch 仪式期检测到缺失 ACK；触发 Level 1 领导者选举 |
| 网络分区 | 各分区内部继续自治；网络恢复后，通过 Epoch 边界仪式 + 门限共识合并状态 |
| 状态分叉 | Epoch 边界确定性规则收敛；若无法收敛则升级仲裁 |
| 拜占庭 Agent | 广场日志是公开的，异常行为可被所有 Agent 独立验证；门限机制自然排除少数异常节点 |
| 广场（Layer 0）故障 | 唯一的单点风险；降级到临时 Leader 模式，用 Leader 的日志作为临时广场 |

---

## 各协调机制的成本-频率权衡

```
频率
  高 │  Sticky Convention ──── 工作期默认（几乎零成本）
     │  Lock/Lease ─────────── 任务分配（O(1) 原子操作）
     │  Epoch Ritual ──────────仪式期同步（O(n) 广播）
     │  Deterministic Rule ─── 冲突自动解决（零通信成本）
     │
     │  Leader Election ─────── 罕见冲突（O(n) 一轮）
     │  Threshold ──────────── 更罕见（O(n) 多轮）
  低 │  Full Consensus ──────── 极罕见系统变更（O(n²)）
     └────────────────────────────────────────────────→ 成本
```

---

## 设计总结：三个核心原则

### 原则一：公共知识优先
每一次重要的状态转变，必须经过广场（公开广播 + 公开确认），
而不仅仅是点对点通知。这是 Chwe 的核心教训。

### 原则二：仪式即基础设施
Epoch 边界的仪式期不是"开销"，是系统产生公共知识的必要机制。
通过固定节奏降低不确定性，通过公开参与构建共同基准。

### 原则三：默认自治 + 稀有协调
绝大多数时间，Agent 依赖本地缓存的公共知识独立运行（Sticky Convention）。
协调机制只在必要时触发，且总是从成本最低的级别开始升级。

---

## 与原方案对比

| 机制 | 单独使用的问题 | AGORA 中的角色 |
|------|--------------|---------------|
| 固定调度者 | 单点风险 | 不使用 |
| Gossip | 只产生互知，非公共知识 | 不作为主干 |
| 区块链 | 成本极高 | Layer 0 的精神原型，不直接使用 |
| 多数共识 | 成本高，不适合高频 | 仅用于系统级变更 |
| 确定性规则 | 需要候选集合一致 | Epoch 仪式后候选集已是公共知识，安全使用 |
| Sticky Convention | 无法处理变更 | 工作期默认，Epoch 边界触发更新 |
| Leader Election | 失效后需重选 | 仅作短期仲裁，不持有全局权威 |

**AGORA 的本质：用仪式（Epoch）生产公共知识，用公共知识替代权威。**

---

## 里程碑计划

| 阶段 | 内容 | 状态 |
|------|------|------|
| M1：基础链路 | Agora 广场 + Agent 任务循环 + WebSocket 广播 | ✅ 完成 |
| M2：节律层 | Epoch 仪式期（STATE_PUBLISH + ACK + 公共知识产生）| ✅ 完成 |
| M3：DAG 调度 | `depends_on` 依赖图 + `TASK_UNBLOCKED` | ✅ 完成 |
| M4：Agent Registry | 能力声明 + 按能力路由 + 心跳检测 | ✅ 完成（心跳检测→M4b）|
| M5：Protocol SDK | Python SDK（外部 Agent 接入库）+ `/x/` REST API | ✅ 完成 |
| M6：仲裁层 | Leader Election + Threshold Consensus | ✅ 完成 |
| M7a：目标完成检测 | GOAL_COMPLETED 消息 + 结果聚合 + 前端完成横幅 | ✅ 完成 |
| M7b：Node.js SDK | `sdk/nodejs/agora_sdk.mjs` + demo | ✅ 完成 |
| M8：React 前端 | Vite + React + Tailwind；消息流 + Agent 面板 + 仲裁 UI | ✅ 完成 |
| M9：任务重试 + GOAL_FAILED | 重试耗尽 → 级联清理下游任务 → GOAL_FAILED 横幅 | ✅ 完成 |
| M10：Claude Code 集成 | PlannerAgent + POST /tasks + cc_worker.py + AGORA Skill | ✅ 完成 |
| M11：生产化 | Kafka 替换 Redis Streams | 🔲 待开发 |
