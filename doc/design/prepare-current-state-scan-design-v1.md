# Prepare 阶段基础现状扫描设计稿 V1

更新时间：2026-04-19  
状态：Implemented

## 1. 背景

当前 `prepare` 阶段已经负责判断是否启用 todo，并生成候选计划。但在实际运行中，即使不是“澄清后恢复”的场景，`prepare` 也可能缺少对当前真实进度的感知，导致：

1. 续做任务时仍像从零开始规划。
2. 已有产物没有进入计划上下文。
3. CLI 的 `[Prepare]` 摘要只能说明“要做什么”，却看不到“现在有什么”。

这会让计划与工作区现状脱节，也会放大重复规划问题。

## 2. 目标

1. 让所有 `prepare` 都具备基础现状感知。
2. 当存在 active todo 时，为 `prepare` 补充一份轻量的当前状态扫描。
3. 让 rule fallback 和 LLM prepare 两条路径都拿到相同的现状摘要。
4. 在不引入重规划状态机的前提下，让后续 planning 更贴近真实工作区状态。

## 3. 非目标

1. 不引入“多 todo / 多计划版本”的重规划机制。
2. 不新增 plan version / 多版本计划管理。
3. 不做全仓扫描或复杂资产索引。
4. 不改变现有 todo 生命周期。

## 4. 核心思路

`prepare` 不只是判断“要不要建 todo”，还应该知道：

1. 当前 todo 进度如何。
2. 已完成了哪些 subtask。
3. 还有哪些 subtask 未完成。
4. 当前有哪些与任务强相关的已知产物。

因此设计上采用“轻量当前状态扫描”：

1. 仅在存在 active todo 时扫描。
2. 扫描输入来自当前 todo markdown，而不是额外探索整个仓库。
3. 扫描结果作为 `prepare` 的标准输出字段进入后续 planning 上下文。

## 5. 扫描内容

当前状态扫描输出以下字段：

1. `todo_id`
2. `progress`
3. `completed_subtasks`
4. `unfinished_subtasks`
5. `ready_subtasks`
6. `known_artifacts`
7. `summary`
8. `abandon_subtasks`
9. `abandon_reason`

其中：

1. `completed_subtasks`
   - 从 todo 中筛出 `completed` 的步骤。
2. `unfinished_subtasks`
   - 从 todo 中筛出非 terminal 的步骤。
3. `ready_subtasks`
   - 复用依赖判定逻辑，找出当前可执行步骤。
4. `known_artifacts`
   - 从 subtask 描述、验收条件、fallback evidence 中提取路径样式 token。
5. `summary`
   - 面向 runtime 和模型消费的单行摘要。
6. `abandon_subtasks`
   - 当 `resume_from_waiting=true` 且存在 active todo 时，列出旧计划中需要废弃的未完成 subtask 编号。
7. `abandon_reason`
   - 说明这些旧 subtask 被废弃的原因。

## 6. 落点

### 6.1 Todo Tool

在 `app/tool/todo_tool/todo_tool.py` 中新增内部辅助函数：

1. `_extract_path_like_tokens`
2. `_build_current_state_scan`

并让 `prepare_task` 在存在 active todo 时始终返回：

1. `current_state_scan`
2. `current_state_summary`
3. 若 `resume_from_waiting=true`，额外返回 `abandon_subtasks / abandon_reason`

### 6.2 Runtime Prepare

在 `app/core/runtime/agent_runtime.py` 中：

1. `_run_prepare_phase` 在 active todo 存在时调用 `_build_current_state_scan`
2. rule fallback 路径回填 `current_state_scan/current_state_summary`
3. LLM prepare 路径把 `current_state_summary/current_state_scan` 一并送入 planner payload
4. 若 `resume_from_waiting=true`，prepare 结果会带上旧未完成 subtasks 的废弃列表
5. `_maybe_apply_prepared_plan` 会先把这些旧 subtask 标记为 `abandoned`，再执行新的 `plan_task(update)`
6. CLI `[Prepare]` 摘要增加一行 `当前现状：...`
7. system-visible prepare message 增加 `current_state_summary=...`

## 7. 行为变化

引入后：

1. 没有 active todo 的任务
   - 行为基本不变
   - `current_state_summary` 为空

2. 有 active todo 的任务
   - `prepare` 会返回基础现状摘要
   - 后续 planning 不再只看到 active todo id，而是能看到当前进度与已知产物

3. 用户回复澄清、以同一 run 恢复
   - `prepare` 会识别 `resume_from_waiting=true`
   - 旧计划中未完成 subtasks 会先被标记为 `abandoned`
   - 然后再在同一个 todo 下继续追加新的计划

## 8. 示例

示例摘要可能形如：

```text
当前 todo 进度 2/5 (40%)；已完成：Task 1 准备目录、Task 2 实现 CLI；未完成：Task 3 更新 README[pending]；已知产物：work/calculator_app/calculator.py、work/calculator_app/README.md
```

## 9. 测试策略

新增或更新测试覆盖：

1. `prepare_task` 在 active todo 存在时返回 `current_state_summary`
2. `prepare_task` 在 `resume_from_waiting=true` 时返回 `abandon_subtasks`
3. runtime 的 `[Prepare]` CLI 输出包含 `当前现状`
4. runtime 发给模型的 prepare message 包含 `current_state_summary=...`
5. runtime 在澄清恢复时会先把旧未完成 subtask 标记为 `abandoned`

## 10. 结论

这版方案有意保持克制：

1. 不碰重规划
2. 不改变 todo 状态机
3. 给 `prepare` 增加“当前现状感知”
4. 在澄清恢复时自动收束旧的未完成 subtask

这样可以先解决最常见的计划脱离现状问题，同时保持实现与认知成本都足够低。
