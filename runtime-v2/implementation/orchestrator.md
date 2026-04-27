# RuntimeOrchestrator 实现说明

## 当前范围

当前 orchestrator 层已正式落地初始上下文构建和最小 `prepare -> execute -> finalize` 主链骨架，但还没有进入真实 prompt/tool/verification 驱动的执行链。

当前已实现：

1. `RuntimeOrchestrator`
2. `build_initial_context(...)`
3. `run(...)` 最小真实主链
4. `run_prepare_phase(...)`
5. `run_execute_phase(...)`
6. `run_finalize_phase(...)`

对应代码：

1. [src/rtv2/orchestrator/runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
2. [tests/test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)

## 为什么先落 `build_initial_context(...)`

当前先落 `build_initial_context(...)`，原因是：

1. orchestrator 要从 `StartRunIdentity` 进入真实 run，必须先有正式 `RunContext` 组装入口。
2. 先把上下文组装钉住，后面的 prepare / execute / finalize 才有稳定输入。
3. `RunLifecycle`、`RuntimeState`、`DomainState` 的职责边界需要通过实际组装过程落到代码里。

## `build_initial_context(...)` 的作用

`build_initial_context(...)` 用于把一次宿主发起的新 run 输入转换成最小正式 `RunContext`。

当前组装规则如下：

1. `run_identity`
   - 直接从 `StartRunIdentity` 映射得到
2. `run_lifecycle`
   - `lifecycle_state = "running"`
   - `current_phase = RunPhase.PREPARE`
3. `runtime_state`
   - 当前初始化为空运行时控制壳
4. `domain_state`
   - 当前初始化为最小领域壳
   - 内含一个新的空 `TaskGraphState`

## 当前设计结论

当前这一步已经定稿的边界如下：

1. 初始 `RunContext` 从 `PREPARE` phase 开始
2. 初始 `TaskGraphState` 为空 graph
3. `graph_id` 不复用 `task_id`
4. `graph_id` 当前由 orchestrator 内部生成
5. 当前不通过 host 生成 `graph_id`

## `run(...)` 的当前作用

当前 `run(...)` 已不再直接返回 stub，而是正式调用最小 phase 链。

当前调用顺序如下：

1. `build_initial_context(...)`
2. `run_prepare_phase(...)`
3. `run_execute_phase(...)`
4. `run_finalize_phase(...)`

当前返回：

1. `runtime_state = "completed"`
2. `output_text = ""`

这表示：

1. 宿主入口和 orchestrator 主链骨架都已打通
2. 但 phase 内部仍然只是最小状态推进

## 当前 phase 规则

当前三阶段的最小规则如下：

1. `run_prepare_phase(...)`
   - 要求输入 phase 为 `PREPARE`
   - 推进到 `EXECUTE`
2. `run_execute_phase(...)`
   - 要求输入 phase 为 `EXECUTE`
   - 推进到 `FINALIZE`
   - 写入：
     - `result_status = "completed"`
     - `stop_reason = "execute_finished"`
3. `run_finalize_phase(...)`
   - 要求输入 phase 为 `FINALIZE`
   - 收口为最小 `HostRunResult`
4. phase 顺序不对时，当前显式抛错

## 当前边界

当前 orchestrator 层明确不负责：

1. 真实 `prepare` 逻辑
2. 真实 `execute` 逻辑
3. 真实 `finalize` 逻辑
4. prompt / tool / verification 接线
5. phase 间状态推进闭环

这些内容会在模块 06 后续子任务中继续落地。

## 下一步

orchestrator 层下一步预计进入：

1. 正式替换 `run(...)` stub
2. `prepare / execute / finalize` 最小 phase 壳
3. orchestrator 到 `HostRunResult` 的真实返回收口
