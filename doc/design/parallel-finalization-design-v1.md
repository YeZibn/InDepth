# Runtime 结束阶段并行收尾设计稿（V1）

更新时间：2026-04-17  
状态：Implemented（已落地）

## 1. 背景与问题

当前 Runtime 在完成主执行后，结束阶段采用串行收尾：
1. `finalize_completed_run(...)`
2. `_finalize_task_memory(...)`
3. `_capture_user_preferences(...)`
4. `finalize_memory_compaction(...)`

此外，`emit_event(...)` 在 `task_finished / task_judged / verification_skipped` 上还会同步触发 `generate_postmortem(...)`，进一步拉长结束路径。

这带来两个问题：
1. 结束总耗时接近多个收尾动作的串行总和。
2. `finalize` 压缩会被 verification、system memory、user preference、postmortem 全部前置阻塞。

## 2. 目标

本方案目标：
1. 保持主判定链路串行完成，先拿到最终 `judgement/handoff/status`。
2. 将结束后的独立收尾动作改为并行执行。
3. 所有并行任务完成后，再统一返回 `run()` 结果。
4. 移除 `emit_event(...)` 中对 postmortem 的强同步副作用，改由 Runtime 显式调度。

## 3. 非目标

本次不做：
1. 不把 verification 本身并行化。
2. 不改变 `task_finished -> verification -> task_judged` 的主事件顺序。
3. 不改变 final answer 的返回语义。
4. 不将结束阶段改成 fire-and-forget 后台任务；仍然 wait 全部完成再返回。

## 4. 并行边界

### 4.1 保持串行的部分

以下步骤仍在主线程串行执行：
1. `finalize_completed_run(...)`
2. `task_finished` 事件发出
3. verification 判定
4. `task_judged` / `verification_failed` 等终态事件写入

原因：
1. 后续收尾动作依赖 `task_finished_status` 与最终 handoff。
2. verification 结果本身属于主执行链路，不适合延后。

### 4.2 改为并行的部分

在 `finalize_completed_run(...)` 返回后，并行启动以下任务：
1. `generate_postmortem(task_id, run_id)`
2. `_finalize_task_memory(...)`
3. `_capture_user_preferences(...)`
4. `finalize_memory_compaction(...)`

并行模型：
1. 使用 `ThreadPoolExecutor`
2. 主线程 `wait(futures)` 后统一返回

## 5. 设计细节

### 5.1 emit_event 去副作用

当前问题：
1. `emit_event()` 会在部分事件类型上直接同步调用 `generate_postmortem(...)`

调整：
1. `emit_event()` 新增参数 `generate_postmortem_artifacts: bool = True`
2. 默认保持现有行为
3. 但在 `finalize_completed_run(...)` 中，对 `task_finished` 与 `task_judged` 显式传 `False`

这样可以：
1. 保留其他调用方兼容
2. 避免 Runtime completed path 在发事件时被 postmortem 卡住

### 5.2 Runtime 并行收尾入口

新增薄封装：
1. `_generate_run_postmortem(task_id, run_id)`
2. `_run_parallel_completed_finalizers(...)`

职责：
1. 调度 4 个结束任务
2. 统一等待 futures
3. 捕获异常并记录 trace，不中断其他收尾任务

### 5.3 Postmortem 语义调整

并行后，postmortem 生成时可能与：
1. system memory finalize
2. user preference capture
3. final compaction

存在时间重叠。

V1 取舍：
1. postmortem 的主语义聚焦于“主执行链路与评估结论”
2. 不再要求它一定覆盖所有后置 memory/user-preference 收尾事件
3. verifier 不再依赖同轮 postmortem 作为强前置证据

## 6. 风险与缓解

风险 1：postmortem 可能看不到并发后续事件。  
缓解：
1. 明确 postmortem 的核心职责是记录主执行链路与最终 judgement
2. memory / preference 的细节仍会落在事件流中

风险 2：并行收尾中的某一项失败后，错误被吞掉。  
缓解：
1. future 统一 `result()`，在 Runtime trace 中记录失败原因
2. 单个收尾任务失败不影响其他收尾继续执行

风险 3：SQLite / 文件写入出现轻微并发竞争。  
缓解：
1. 当前各模块本身使用短连接/独立文件写入，冲突面较小
2. V1 先基于现有实现验证，若后续发现竞争，再做更细粒度锁控制

## 7. 测试计划

至少覆盖：
1. Runtime 完成后会调度 4 个并行收尾任务
2. 并行收尾会等待全部结束后再返回
3. 既有 eval / bootstrap / main_agent / observability 回归继续通过

## 8. 实现结果

已按本稿落地：
1. `emit_event()` 已支持关闭同步 postmortem 副作用
2. `task_finished / task_judged` 在 completed path 中不再同步生成 postmortem
3. Runtime 结束后会并行执行：
   - postmortem 生成
   - task memory finalize
   - user preference capture
   - final memory compaction
4. 主线程会等待全部完成后再返回 `run()`
