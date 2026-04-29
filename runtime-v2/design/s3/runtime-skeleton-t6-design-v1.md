# S3-T6 Runtime Skeleton 与 Finalize 主干（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S3-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 `RuntimeOrchestrator` 的最小运行骨架。

本任务只回答三件事：

1. `RuntimeOrchestrator.run(...)` 的最小时序是什么
2. `Prepare / Execute / Finalize` 三阶段如何挂入主骨架
3. runtime 最终如何收口到 `RunOutcome`

## 2. 正式结论

本任务最终结论如下：

1. `RuntimeOrchestrator.run(...)` 第一版采用极简主骨架
2. phase 切换以 `S3-T5` 为准，由 `step` 决定
3. `orchestrator` 只执行 phase 切换结果
4. `ExecutePhase` 通过 step loop 循环消费 `StepResult`
5. `FinalizePhase` 在骨架层只作为 closeout pipeline 入口
6. runtime 最终返回 `RunOutcome`

## 3. 最小骨架

第一版正式骨架如下：

```text
RuntimeHost
  -> RuntimeOrchestrator.run(input)
    -> build_initial_context()
    -> run_prepare_phase(ctx)
    -> while ctx.run_lifecycle.current_phase == "execute":
         step_result = run_execute_step(ctx)
         ctx = apply_step_result(ctx, step_result)
       end
    -> if ctx.run_lifecycle.current_phase == "finalize":
         ctx = run_finalize_phase(ctx)
    -> return RunOutcome
```

## 4. 五个骨架动作

第一版 runtime skeleton 只保留 5 个骨架动作：

1. `build_initial_context`
2. `run_prepare_phase`
3. `run_execute_step`
4. `apply_step_result`
5. `run_finalize_phase`

本任务明确规定：

1. 第一版不再引入更多 manager / resolver / scheduler 名字
2. 先把主骨架立稳，再在各自子系统中细化

## 5. `build_initial_context`

作用：

1. 创建本次 run 的 `RunContext`
2. 初始化 `run_identity`
3. 初始化 `run_lifecycle`
4. 初始化 `runtime_state`
5. 初始化 `domain_state`

这一阶段只做上下文建立，不做正式执行。

## 6. `run_prepare_phase`

`PreparePhase` 在第一版骨架中只承担 3 个作用：

1. 建立可执行入口
2. 承接启动前注入已完成后的初始运行态
3. 让上下文具备进入 `execute` 的前提

这里的“建立可执行入口”主要包括：

1. 初始 task graph 就位
2. 初始 `active_node_id` 就位
3. `RunContext` 进入可执行状态

这里的“初始 task graph 就位”在后续正式实现中，允许通过一次真实 planning 调用直接生成首批 graph 结果，而不是只保留文本 planning summary。

第一版 `PreparePhase` 的补充边界如下：

1. 主产物以 graph 层结果为主
2. 空图场景允许直接产出首批节点
3. 可以保留一个轻量 `prepare_result` 作为后续阶段消费口
4. 不在本轮引入 `replan` 回流实现
5. 不在本轮引入 prepare 内多轮循环
6. 不默认直读 skill resource

本任务明确规定：

1. `PreparePhase` 不自己切 phase
2. `PreparePhase` 只返回更新后的 `RunContext`

## 7. `run_execute_step`

`ExecutePhase` 的主骨架通过 step loop 展开。

第一版中，每一轮 execute step 只做：

1. 读取当前 `RunContext`
2. 围绕当前 `active_node` 运行一轮 `step`
3. 产出一个完整 `StepResult`

`run_execute_step` 不直接修改正式状态。

它只负责产出：

1. `StepResult`

## 8. `apply_step_result`

`apply_step_result` 是 orchestrator 的控制动作。

它负责：

1. 应用 `node_patch`
2. 应用 `TaskGraphPatch`
3. 更新 `RunContext`
4. 执行 `runtime_control`
5. 执行 `next_phase`

本任务明确规定：

1. `apply_step_result` 不做二次语义判断
2. `StepResult` 必须足够完整
3. orchestrator 只按结果执行

## 9. Phase 切换规则

第一版正式采用 `S3-T5` 的结论：

1. phase 切换由 `step` 决定
2. `StepResult.runtime_control.next_phase` 是正式切换输入
3. orchestrator 不补 phase 判断

因此：

1. `PreparePhase` 返回可执行上下文
2. `ExecutePhase` 每轮 step 明确决定是否继续 `execute` 或切入 `finalize`
3. `FinalizePhase` 作为 closeout 入口被调用

## 10. Execute Loop 的退出条件

第一版 execute loop 退出可归为 3 类：

### 10.1 Step 主动切入 `finalize`

即：

1. `StepResult.runtime_control.next_phase = "finalize"`

这是最正常的主链路收口方式。

### 10.2 Graph 已进入整图终态

例如：

1. `graph_status = completed`
2. `graph_status = abandoned`

并且 `step` 已给出进入 `finalize` 的结果。

### 10.3 Execute 前提不再成立

例如：

1. 当前 phase 已不再是 `execute`
2. 当前 graph 已进入终态
3. 当前已没有可执行主线

这里的含义不是 orchestrator 自主做业务判断，而是：

1. orchestrator 执行主循环的骨架退出条件

## 11. `run_finalize_phase`

第一版中，`FinalizePhase` 在 runtime skeleton 里只作为 closeout pipeline 入口。

也就是说，在骨架层只写：

1. 进入 finalize
2. 运行 closeout pipeline
3. 回收最终 `RunOutcome`

第一版不在 `S3-T6` 中展开：

1. handoff 内部生成细节
2. verification 内部判断细节
3. memory write 内部流程

这些属于 `S11` 与 `S8` 的展开内容。

## 12. 返回值

第一版明确规定：

1. `RuntimeOrchestrator.run(...)` 最终返回 `RunOutcome`

原因如下：

1. `RunOutcome` 已是正式收尾产物
2. 它最适合作为 host / 上层调用者的最终返回对象
3. 可以稳定对接 `S11` closeout 结构

## 13. 与其他任务的对齐

本任务与前序任务正式对齐如下：

1. 与 `S3-T5` 对齐：`step` 决定 phase 切换
2. 与 `S4-T4` 对齐：`RunContext` 是唯一正式主上下文
3. 与 `S5-T7` 对齐：graph patch 由 step 产出，store 只负责应用
4. 与 `S11` 对齐：runtime 终点是 `RunOutcome`

## 14. 对后续任务的直接输入

`S3-T6` 直接服务：

1. `S1-T5` prompt assembly 入口挂载
2. `S4-T6` 状态层骨架落位
3. `S11` finalize pipeline 细化
4. `S12` runtime 事件与测试骨架

## 15. 本任务结论摘要

可以压缩成 6 句话：

1. `RuntimeOrchestrator.run(...)` 第一版采用极简五步骨架
2. `Prepare` 负责建立可执行入口
3. `Execute` 通过 step loop 循环消费 `StepResult`
4. phase 切换由 `step` 决定，orchestrator 只执行
5. `Finalize` 在骨架层只作为 closeout pipeline 入口
6. runtime 最终返回 `RunOutcome`
