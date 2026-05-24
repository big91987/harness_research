# 001-基础层-Scaffold-Research Skeleton

## 中文版：先留下一块能生长的地基

### 全局作用

参见：[000-总览-Harness-分层架构与连载目录](000-总览-Harness-分层架构与连载目录.md)。本文位于基础层，是整个系列的第一块地基。

对应整体架构图中的“基础层”。在任何 Agent Kernel、工具、记忆出现之前，仓库必须先有一个能承载实验的骨架：包结构、测试入口、README 和最小工程约定。没有这一步，后面每个模块都会像散落的笔记，无法持续演进。

### 输入 / 输出 / 行为

- 输入：一个空的研究仓库。
- 输出：`src/harness`、`tests`、`pyproject.toml`、README。
- 行为：建立 Python package 和 pytest 约定，让后续每个模块都能按 TDD 进入。

### 实现原理与流程图

Scaffold 的关键不是“生成几个文件”，而是先定义系统生长的方向：源码放在 `src/harness`，测试放在 `tests`，项目元信息由 `pyproject.toml` 承载。这样后续每个模块都可以用同一套导入路径、同一套 pytest 入口和同一套提交粒度来演进。

```mermaid
flowchart LR
  Empty["空仓库"] --> Layout["src/harness + tests"]
  Layout --> Metadata["pyproject.toml"]
  Metadata --> Readme["README 说明入口"]
  Readme --> TDD["后续模块可 TDD 增长"]
```

### 过程记录

第一步没有追求功能，而是追求“可继续”。这是 Harness 从脚本走向系统的分水岭：只要目录和测试约定固定，后面每次能力增长都可以被验证、被回滚、被讲清楚。

### 当前实现

- 对应提交：`9d8658e Initial harness research scaffold`
- 当前状态：已实现
- 验证方式：仓库可被 pytest 发现测试，源码位于 `src/harness`。

### 测试例跑法

```bash
python3 -m pytest
PYTHONPATH=src python3 -m harness.cli --help
```

读者验证点：pytest 能发现测试；`harness.cli` 能被 Python 模块方式加载，说明包结构成立。

### 未来扩展计划

- 把 specs 与实现提交绑定成自动索引。
- 在 CI 中强制检查“每个实现提交都有文章”。

## English Version

The first step creates the ground where the harness can grow: source layout,
tests, project metadata, and a README. It is intentionally small, but it gives
future modules a stable place to land and a test runner to prove behavior.
