# 001-基础层-Scaffold-Research Skeleton

## 中文版：先留下一块能生长的地基

### 全局作用

对应整体架构图中的“基础层”。在任何 Agent Kernel、工具、记忆出现之前，仓库必须先有一个能承载实验的骨架：包结构、测试入口、README 和最小工程约定。没有这一步，后面每个模块都会像散落的笔记，无法持续演进。

### 输入 / 输出 / 行为

- 输入：一个空的研究仓库。
- 输出：`src/harness`、`tests`、`pyproject.toml`、README。
- 行为：建立 Python package 和 pytest 约定，让后续每个模块都能按 TDD 进入。

### 过程记录

第一步没有追求功能，而是追求“可继续”。这是 Harness 从脚本走向系统的分水岭：只要目录和测试约定固定，后面每次能力增长都可以被验证、被回滚、被讲清楚。

### 当前实现

- 对应提交：`9d8658e Initial harness research scaffold`
- 当前状态：已实现
- 验证方式：仓库可被 pytest 发现测试，源码位于 `src/harness`。

### 未来扩展计划

- 把 specs 与实现提交绑定成自动索引。
- 在 CI 中强制检查“每个实现提交都有文章”。

## English Version

The first step creates the ground where the harness can grow: source layout,
tests, project metadata, and a README. It is intentionally small, but it gives
future modules a stable place to land and a test runner to prove behavior.

