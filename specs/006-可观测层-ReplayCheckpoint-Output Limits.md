# 006-可观测层-ReplayCheckpoint-Output Limits

## 中文版：能回放，也要能刹车

### 全局作用

对应整体架构图中的 Replay、Checkpoint 和输出控制。Agent 会产生大量文本和文件变化；Harness 需要能回看发生过什么，也需要限制输出，避免上下文被工具结果淹没。

### 输入 / 输出 / 行为

- 输入：trace、workspace、工具输出。
- 输出：replay timeline、checkpoint、截断后的 tool result。
- 行为：回放关键事件；在风险操作前保存状态；长输出按限制截断。

### 过程记录

这一章补的是“操作安全感”。当 Agent 开始改文件，开发者需要知道它改了什么、能不能回退、输出会不会爆上下文。

### 当前实现

- 对应提交：`8c223cb Add replay checkpoint and output limits`
- 当前状态：已实现
- 模块：`harness.checkpoint`、`harness.trace`、`harness.tools`

### 未来扩展计划

- checkpoint 增量化。
- replay 生成更适合人读的任务故事线。

## English Version

Replay, checkpoints, and output limits make local agent actions inspectable,
recoverable, and context-safe.

