# 001-状态层-Memory-Session Extraction

## 中文版：把一场对话酿成长期记忆

### 全局作用

在 Harness 架构里，Memory 属于状态层。它解决的不是“这一轮怎么答”，而是“下一轮、下一个窗口、下一个任务还能不能继承经验”。模型窗口总会满，session 总会结束；如果没有一条把会话沉淀为长期上下文的路径，Agent 每次醒来都像刚入职。

Session Extraction 是本地 harness 的第一条“做梦”支线：从已经保存的 session 里抽取稳定事实、用户偏好、项目约束和反复出现的工作方式，写入 Markdown memory。它不依赖 server、TUI、WebUI，先让本地闭环跑起来。

### 输入 / 输出 / 行为

- 输入：
  - `--session-dir`：本地 session JSONL 目录。
  - `--extract-session <session-id>`：要抽取的会话。
  - `--memory-dir`：Markdown memory 的存放目录。
  - `HARNESS_BASE_URL` / `HARNESS_API_KEY` / `HARNESS_MODEL`：真实模型配置。
- 输出：
  - `memory.md` 中新增的 bullet 记忆。
  - `--json` 下返回 `session_id`、`added` 和 `count`。
- 行为：
  - 模型只能返回 JSON 数组，或包含 `memories` / `items` / `facts` 的 JSON 对象。
  - 空项会被丢弃。
  - 和既有 memory 重复的条目会被跳过。
  - 非 JSON 输出 fail closed，不从自由文本里猜。

### 过程记录

我们先写了两个单元测试：一个证明 extractor 能把模型返回写入 memory，另一个证明空项和重复项不会污染长期记忆。随后补了 CLI smoke：先创建 session，再通过 `memory --extract-session` 抽取到 memory。最后用真实 DeepSeek 跑了一次：session 中写入“尽量使用真实 DeepSeek 验证”，extractor 成功沉淀为 Markdown memory。

### 当前实现

- 模块：`harness.memory.SessionMemoryExtractor`
- CLI：`harness memory --extract-session <session-id>`
- 存储：`MarkdownMemoryStore`，单文件 `memory.md`，带文件锁。
- 测试：
  - `tests/test_memory.py`
  - `tests/test_cli_smoke.py::test_cli_memory_extracts_from_session`

### 未来扩展计划

- 做成后台 dream：根据 session 数量、时间间隔、任务完成状态自动触发。
- 按 scope 拆分 user/project/workspace memory。
- 给每条 memory 增加 source session、timestamp、confidence、version。
- 加入“纠错型 dream”：自动发现旧 memory 与新事实冲突并提出修订。

## English Version

### Role In The Global Architecture

Memory lives in the state layer of the harness. It preserves useful context
across turns, windows, sessions, and tasks. Session extraction is the first local
"dream" path: it distills durable facts from a saved session into Markdown
memory without requiring a server or UI.

### Input / Output / Behavior

- Input: a session id, `--session-dir`, `--memory-dir`, and real model
  configuration through `HARNESS_BASE_URL`, `HARNESS_API_KEY`, and
  `HARNESS_MODEL`.
- Output: new bullet entries in `memory.md`; JSON mode returns `session_id`,
  `added`, and `count`.
- Behavior: accepts JSON arrays or JSON objects with `memories`, `items`, or
  `facts`; skips empty and duplicate items; fails closed on non-JSON output.

### Implementation Notes

The feature is implemented by `SessionMemoryExtractor` and exposed through
`harness memory --extract-session <session-id>`. Unit tests cover extraction and
deduplication. CLI smoke tests cover session-to-memory flow. A live DeepSeek run
verified that a durable preference from a real session was persisted.

### Future Work

Automatic dream scheduling, scoped memory, source/version metadata, confidence,
and model-assisted conflict repair.

