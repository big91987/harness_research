# 000-总览-Harness-分层架构与连载目录

## 中文版：先把地图摊开

我们要做的不是一堆工具函数，而是一个本地优先的 Agent Harness。费曼学习法的第一步，是把一个复杂系统讲到“初学者也能沿着线索复现”。所以这个系列不按代码文件写，而按 Harness 的分层职责写：模型之外，Agent 能行动、能记住、能治理、能复盘的部分，都逐步落成可运行模块。

### 整体分层架构图

![Harness Engineering Arch v2](images/Harness%20Engineering%20Arch%20v2.png)

这张图是本系列的母图。后续每一篇实现文章都要回到这张图，说明当前模块落在哪一层、解决哪条主干能力、哪些能力还只是预留。

按这张图，我们不再把 Harness 简化成“CLI + Kernel + Tools”，而是分成六层：

1. Experience & Gateway Layer：体验与网关层，解决人、IDE、Web、API、消息和设备节点如何接入。
2. Agent Control Plane：控制平面，解决代理、工具、技能、策略、配置、Session、队列和 Workflow 如何被注册、路由和编排。
3. Harness Runtime：Agent 运行时，解决 Agent Loop、规划、执行、工具编排、上下文、记忆、状态、流式运行、多 Agent 和模型路由。
4. Execution & Security Infrastructure：执行与安全基础设施，解决 sandbox、workspace、shell、浏览器、网络、审批、密钥、产物、元数据、事件和缓存。
5. Knowledge & Business Data：知识与业务数据，解决知识库、向量库、图谱、本体、文档、业务系统、搜索检索和连接器。
6. Observability / Evaluation / Ops：可观测、评测与运维，解决日志、追踪、指标、成本、审计、回放、诊断、回归、发布和服务化。

右侧 Cross-cutting 表示横切关注点：Security / Governance / Quality / Lifecycle。它不是单独一层，而是贯穿所有层的约束。

### 当前实现状态表

| 架构层 | 图中模块 | 当前状态 | 已实现能力 / 缺口 |
|---|---|---:|---|
| 1. Experience & Gateway Layer | TUI / CLI | 已实现 | CLI 已覆盖 run、tools、sessions、memory、skills、tasks、runs、trace、audit、eval、doctor、verify、init |
| 1. Experience & Gateway Layer | Web UI / Console | 未开始 | 后续做本地 Harness Server 后再接 Web 工作台 |
| 1. Experience & Gateway Layer | IDE Bridge | 未开始 | 预留给编辑器插件或 IDE sidecar |
| 1. Experience & Gateway Layer | API / SDK | 未开始 | 目前只有 Python 包内接口，尚未形成稳定 SDK/API |
| 1. Experience & Gateway Layer | Messaging Gateway / Channel Adapters | 未开始 | 预留给消息入口、多渠道接入和 channel protocol |
| 1. Experience & Gateway Layer | Device / Node Runtime | 未开始 | 预留给多节点、端侧或远端执行节点 |
| 1. Experience & Gateway Layer | Human Approval | 部分实现 | CLI prompt approval 已有；UI 化、队列化审批未做 |
| 2. Agent Control Plane | Agent Registry | 未开始 | 当前是单 Agent 本地运行，尚未做 Agent 注册中心 |
| 2. Agent Control Plane | Tool / MCP Registry | 已实现 | 本地 tool registry、工具 profile、metadata CLI；MCP adapter 未做 |
| 2. Agent Control Plane | Skill / Plugin Registry | 已实现 | 本地 skill registry、检索、注入；plugin 生命周期未做 |
| 2. Agent Control Plane | Policy & Permission | 已实现 | permission mode、tool policy、approval、fail closed、audit context |
| 2. Agent Control Plane | Config / Feature Flags | 已实现 | harness config、env override、config validation；feature flag 仍较轻 |
| 2. Agent Control Plane | Session Routing | 部分实现 | session resume/import/export/compact 已有；跨 Agent/session router 未做 |
| 2. Agent Control Plane | Scheduler / Queue | 已实现 | run ledger、queued run、worker、drain、diagnose、failure clean |
| 2. Agent Control Plane | Workflow | 未开始 | 目前不是图式 workflow engine，只有 task ledger 和 run queue |
| 3. Harness Runtime | Agent Loop / Query Engine | 已实现 | turn loop、model call、tool call、session save、fail-fast |
| 3. Harness Runtime | Planner | 未开始 | 当前让模型自然规划，未实现显式 planner 模块 |
| 3. Harness Runtime | Executor | 已实现 | tool dispatch、tool validation、execution result 回填 |
| 3. Harness Runtime | Tool Orchestration | 部分实现 | 单轮多工具与 profile 已有；复杂工具 DAG / fan-out 未做 |
| 3. Harness Runtime | Context Manager | 已实现 | session history、active task context、handoff、bundle、compaction |
| 3. Harness Runtime | Context Budget / Compact | 已实现 | usage tracking、token/cost budget、session compact |
| 3. Harness Runtime | Memory Manager | 已实现 | Markdown memory、session extraction、memory locks |
| 3. Harness Runtime | State Machine | 部分实现 | task/run state 已有；通用 state machine 未抽象 |
| 3. Harness Runtime | Streaming Runtime | 未开始 | 当前未实现 token streaming / event streaming runtime |
| 3. Harness Runtime | Multi-agent / Subagent | 未开始 | 预留给多 Agent 协作、subagent 委托 |
| 3. Harness Runtime | Model Gateway / Router | 部分实现 | OpenAI-compatible client、DeepSeek live 验证、retry；多模型路由未做 |
| 4. Execution & Security Infrastructure | Sandbox Policy | 已实现 | macOS sandbox-exec runner、workspace boundary、敏感路径拒读、fail closed |
| 4. Execution & Security Infrastructure | Workspace / Filesystem | 已实现 | path guard、read/write/append/edit/diff/move/copy/delete/list/grep |
| 4. Execution & Security Infrastructure | Shell / Process Runner | 已实现 | bash 通过 sandbox runner 执行，支持 cwd/env/profile |
| 4. Execution & Security Infrastructure | Browser / Computer Use | 未开始 | 预留给浏览器自动化和计算机使用工具，按策略必须走 sandbox/runner |
| 4. Execution & Security Infrastructure | Network Policy | 未开始 | 目前未做网络域名/出口策略 |
| 4. Execution & Security Infrastructure | Approval Runtime | 部分实现 | prompt approval 已有；集中式 approval service 未做 |
| 4. Execution & Security Infrastructure | Secrets / Credentials | 未开始 | 目前依赖环境变量，未做 secrets vault |
| 4. Execution & Security Infrastructure | Artifact Store | 已实现 | artifact register/query/verify、checkpoint artifact manifest |
| 4. Execution & Security Infrastructure | Metadata Store | 部分实现 | JSONL/JSON 本地状态已有；统一 metadata store 未抽象 |
| 4. Execution & Security Infrastructure | Event Bus | 未开始 | 当前没有独立事件总线 |
| 4. Execution & Security Infrastructure | Cache | 未开始 | 目前没有统一 cache 模块 |
| 5. Knowledge & Business Data | Knowledge Base | 部分实现 | Markdown memory 可作为轻量知识库；业务 KB 未做 |
| 5. Knowledge & Business Data | Vector DB | 未开始 | 尚未接向量数据库 |
| 5. Knowledge & Business Data | Graph / Ontology | 未开始 | 尚未做图谱/本体 |
| 5. Knowledge & Business Data | Documents | 部分实现 | session bundle/artifact 可存文档；文档解析管线未做 |
| 5. Knowledge & Business Data | Business Systems | 未开始 | 预留给企业业务系统连接 |
| 5. Knowledge & Business Data | Search / Retrieval | 部分实现 | grep/list/search 工具已有；语义检索未做 |
| 5. Knowledge & Business Data | Connectors | 未开始 | 预留给外部系统 connector |
| 6. Observability / Evaluation / Ops | Logs | 已实现 | audit log、trace log、session JSONL |
| 6. Observability / Evaluation / Ops | Tracing / OTel | 部分实现 | 本地 trace/query/session summary 已有；OTel 未接 |
| 6. Observability / Evaluation / Ops | Rollout Trace | 部分实现 | turn id、run ledger、checkpoint lifecycle trace 已有；发布追踪未做 |
| 6. Observability / Evaluation / Ops | Metrics | 部分实现 | usage/cost、summary 已有；统一 metrics backend 未做 |
| 6. Observability / Evaluation / Ops | Token / Cost | 已实现 | usage parsing、cost tracking、budget check/enforcement |
| 6. Observability / Evaluation / Ops | Audit | 已实现 | audit filter、summary、turn context |
| 6. Observability / Evaluation / Ops | Replay / Debugging | 已实现 | replay checkpoint、trace-derived golden、run diagnostics |
| 6. Observability / Evaluation / Ops | Eval Harness | 已实现 | eval suite、golden regression、verify runner、live smoke |
| 6. Observability / Evaluation / Ops | Regression / Golden Traces | 已实现 | golden cases、trace-derived eval、doctor checks |
| 6. Observability / Evaluation / Ops | Doctor / Diagnostics | 已实现 | doctor JSON、sandbox probe、run directory check、config validation |
| 6. Observability / Evaluation / Ops | Install / Update | 部分实现 | init scaffold 已有；install/update channel 未做 |
| 6. Observability / Evaluation / Ops | Migration | 未开始 | 尚未做 state/schema migration |
| 6. Observability / Evaluation / Ops | Daemon / Service | 未开始 | 后续 Harness Server / daemon 阶段实现 |
| 6. Observability / Evaluation / Ops | Release Channels | 未开始 | 后续发布通道治理 |

### 文章编号规则

每个实现节点对应一篇文章。文件名和一级标题必须完全一致，格式为：

`NNN-层-模块-子模块.md`

每篇文章都要包含：

- 全局作用：这个模块在上图中的位置。
- 输入 / 输出 / 行为：可以被工程验证的接口。
- 实现原理：用面向中文技术读者的语言讲清楚模块为什么这样设计。
- 实现流程图：至少一张 Mermaid 流程图，说明数据、控制流或状态流。
- 过程记录：当时为什么做、测试怎么红、怎么变绿。
- 当前实现：代码、CLI、测试、验证方式。
- 测试例跑法：给读者一条或多条可复制命令，能在本仓库验证这一章。
- 未来扩展：留给 server、多 worker、UI 或更强治理的方向。

### 单篇文章验收表

| 检查项 | 要求 |
|---|---|
| 文件名 / Title | 文件名去掉 `.md` 后必须等于一级标题 |
| 架构引用 | 必须链接回本文，并说明自己位于哪一层 |
| 实现原理 | 不能只写一句话，要解释设计取舍 |
| 流程图 | 必须有 Mermaid 图，读者能顺着图复述模块行为 |
| 输入输出 | 必须列清输入、输出、错误行为 |
| 当前实现 | 必须列代码模块、CLI 或测试入口 |
| 测试跑法 | 必须给可复制命令 |
| 未来扩展 | 必须说明后续 server / 多 worker / UI / 治理方向之一 |

## English Version

This series documents the local-first harness from zero to one. Each article maps
one implementation step to the global layered architecture above, using a
Feynman-style explanation: why it exists, what it takes as input, what it
produces, how it behaves, how we verified it, and what should come next.
