# 007-治理层-ArtifactsAudit-Logging

## 中文版：产物和行为都要留下账本

### 全局作用

对应整体架构图中的 Artifacts 和 Audit。Trace 记录“发生了什么”，Audit 更关心“谁被允许做了什么”，Artifacts 则把重要文件产物登记成可验证对象。

### 输入 / 输出 / 行为

- 输入：工具调用、审批决策、产物路径。
- 输出：audit JSONL、artifact metadata。
- 行为：记录 tool call、approval、文件 hash、产物校验状态。

### 过程记录

当 Harness 进入可执行阶段，治理不能晚到。任何文件改动、危险工具、重要产物都应该有账本，这也是未来 server 多用户权限的前置条件。

### 当前实现

- 对应提交：`68e6d58 Add artifacts and audit logging`
- 当前状态：已实现
- 模块：`harness.audit`、`harness.artifacts`

### 未来扩展计划

- artifact provenance graph。
- audit 与用户/角色权限系统打通。

## English Version

Artifacts and audit logs create accountability: what was produced, who was
allowed to do what, and whether outputs still verify.

