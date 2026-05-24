# 009-评测层-Verify-Local Verification Runner

## 中文版：一条命令跑完本地闸门

### 全局作用

对应整体架构图中的 Verify。随着模块增多，手动记测试命令会越来越不可靠。`verify` 把 config validation、pytest、compile、smoke test 收到一条命令里，成为本地 harness 的总闸门。

### 输入 / 输出 / 行为

- 输入：work dir、verify options。
- 输出：每个 gate 的 pass/fail 和 overall。
- 行为：顺序运行配置校验、测试、编译、mock smoke；后续支持 live smoke。

### 过程记录

这是从“会写代码”到“会交付”的一步。每次改动后，我们都希望能用同一条命令回答：这个本地 harness 还健康吗？

### 当前实现

- 对应提交：`f5ad945 Add local verification runner`
- 当前状态：已实现
- 模块：`harness.verify`
- CLI：`harness verify`

### 未来扩展计划

- 增加分层 verify profile。
- 将 specs 覆盖率纳入 verify。

## English Version

`verify` collects local gates into one command: config validation, tests,
compile checks, and smoke runs.

