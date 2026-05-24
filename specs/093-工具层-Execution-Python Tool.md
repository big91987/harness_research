# 093-工具层-Execution-Python Tool

## 中文版：给 Agent 一支安全的 Python 笔

### 整体架构引用

参见：[000-总览-Harness-分层架构与连载目录](000-总览-Harness-分层架构与连载目录.md)。本文位于工具层的 Execution 分支，并通过 Sandbox Runner 接入安全边界。

### 全局作用

工具层是 Harness 的手脚。文件工具让 Agent 能读写项目，搜索工具让它能定位信息，执行工具让它能计算、验证、生成中间结果。过去本地 harness 已经有 `bash`，但很多 Agent 任务并不需要完整 shell：数据处理、JSON 整形、轻量脚本、快速校验，用 Python 更直接，也更接近真实 coding agent 的日常工作流。

`python` 工具属于高风险执行工具，所以它不能绕过沙箱。它和 `bash` 一样必须走 sandbox runner；runner 不存在时 fail closed，不允许退回宿主机裸跑。

### 输入 / 输出 / 行为

- 输入：
  - `code`：要执行的 Python 代码，必填。
  - `stdin`：传给 Python 进程的标准输入，可选。
  - `cwd`：workspace 内的工作目录，可选，默认 `.`。
  - `env`：显式注入的环境变量，可选。
  - `timeout_seconds`：执行超时，可选，受全局最大超时限制。
- 输出：
  - stdout + stderr 的文本结果。
  - 非 0 退出码会变成 `ToolResult(is_error=True)`。
- 行为：
  - 权限要求为 `danger`。
  - `sandbox_required=True`。
  - `coding` profile 暴露该工具；`safe` profile 不暴露。
  - sandbox runner 使用 macOS `sandbox-exec`，只允许写 workspace，拒绝常见宿主敏感路径读取。

### 过程记录

我们先写红测试：registry 里应该出现 `python`，它必须要求 `danger` 权限和 sandbox runner；配置 runner 后能在 workspace 写文件；sandbox runner 自己也要能处理 `tool=python`。红点集中在两个地方：工具注册表没有 `python`，runner 只接受 `bash`。随后把 `python` 接到同一条 JSON runner 协议里，保持和 `bash` 一致的 fail-closed 行为。

### 当前实现

| 项 | 状态 |
|---|---|
| 层 | 工具层 |
| 模块 | Execution |
| 子模块 | Python Tool |
| 实现状态 | 已实现 |
| 对应提交 | `965af80 Add sandboxed python tool` |

- 模块：
  - `harness.tools._python`
  - `harness.sandbox_runner.run_request`
- CLI：
  - `harness tools --call python --permission danger --sandbox-runner ...`
  - Agent loop 中模型也能通过 tool call 调用 `python`。
- 测试：
  - `tests/test_tools_workspace.py::test_python_requires_danger_permission_and_sandbox_runner`
  - `tests/test_tools_workspace.py::test_python_runs_through_configured_sandbox_runner`
  - `tests/test_sandbox_runner.py::test_sandbox_runner_runs_python_inside_workspace`

### 未来扩展计划

- 增加 Node.js 执行工具，复用同一 sandbox runner 协议。
- 为 Python 工具增加 artifact capture，把生成文件自动登记到 artifact store。
- 增加包依赖白名单和网络禁用/启用开关。
- 把执行类工具抽象成统一 `sandboxed_process`，减少 `bash` / `python` 重复代码。

## English Version

### Role In The Global Architecture

The tool layer gives the agent hands. The `python` tool is a high-risk execution
tool for local computation, data shaping, quick validation, and scriptable coding
workflows. It must use the same sandbox boundary as `bash`.

### Input / Output / Behavior

- Input: `code`, optional `stdin`, `cwd`, `env`, and `timeout_seconds`.
- Output: combined stdout/stderr text; non-zero exits become tool errors.
- Behavior: requires `danger`, is marked `sandbox_required`, appears in the
  `coding` profile, and fails closed when no sandbox runner is configured.

### Implementation Notes

`harness.tools._python` sends a JSON request with `tool=python` to the configured
sandbox runner. The bundled macOS runner executes `sys.executable -c <code>`
inside `sandbox-exec`, permitting writes only under the workspace and denying
common sensitive host reads.

### Future Work

Node.js execution, artifact capture, dependency/network policy, and a shared
`sandboxed_process` abstraction for execution tools.
