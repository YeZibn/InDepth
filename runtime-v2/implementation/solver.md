# Solver / ExecutePhase 实现说明

## 当前范围

当前 `ExecutePhase` 已从早期最小推进链升级为正式 `Solver` 主链。

当前已实现：

1. `RuntimeSolver`
2. `SolverResult`
3. graph 级 execute 主循环
4. 单 node 多轮 step solve
5. node 状态收口后的 graph 回写

对应代码：

1. [src/rtv2/solver/runtime_solver.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/runtime_solver.py)
2. [src/rtv2/solver/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/models.py)
3. [src/rtv2/orchestrator/runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
4. [tests/test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)

## 结构分工

当前职责边界如下：

1. `ReActStepRunner`
   - 只负责单轮 actor step
   - 输入 `step_prompt`
   - 输出 `ReActStepOutput`
2. `RuntimeSolver`
   - 只负责单个 node 的 solve 循环
   - 处理 `pending / ready / running` 的最小推进
   - 根据 `StepStatusSignal` 收口 node 状态
3. `RuntimeOrchestrator.run_execute_phase(...)`
   - 负责 graph 级外层循环
   - 负责选择当前可执行 node
   - 负责消费 `SolverResult` 并回写 graph
   - 负责 graph 终态收口

## `SolverResult` 的作用

当前 `SolverResult` 是 `RuntimeSolver` 返回给 `ExecutePhase` 的最小正式交接对象。

字段如下：

1. `final_step_result`
   - 当前 node 最后一轮正式结果
   - graph patch 继续挂在这里
2. `final_node_status`
   - 当前 solve 收口后的 node 终态
3. `step_count`
   - 当前 node 在本次 solve 内实际消耗的 step 数

当前不额外引入：

1. `active_node_id`
2. 独立 `patch`
3. graph 级状态

这些继续留在 orchestrator / graph 层处理。

## `RuntimeSolver` 的当前规则

### `pending`

当前 `pending` node 的最小处理为：

1. 检查依赖是否全部 `completed`
2. 若未满足，则本次 solve 返回 `None patch`
3. 若满足，则产出 `pending -> ready` patch
4. 本次 solve 立即返回给 graph 层，不继续同轮进入 ReAct

### `ready`

当前 `ready` node 的最小处理为：

1. 先产出一个 `ready -> running` patch
2. 在同一次 solve 中继续进入 running loop

### `running`

当前 `running` node 的处理为：

1. 反复调用 `ReActStepRunner.run_step(...)`
2. 每轮构造新的 `step_id`
3. 把当前 node prompt 传入 step runner
4. 根据 `StepStatusSignal` 决定是否继续或收口

当前收口规则如下：

1. `progressed`
   - 继续下一轮
2. `ready_for_completion`
   - 当前 node 收为 `completed`
3. `blocked`
   - 当前 node 收为 `blocked`
4. `failed`
   - 当前 node 收为 `failed`

## patch 挂载策略

当前 graph patch 继续通过 `StepResult.patch` 承接。

当前实现里：

1. 如果 ReAct step 已经返回 patch，则 solver 直接消费
2. 如果 ReAct step 未返回 patch，则 solver 在必要时补最小 node status patch
3. 若 node 先经历了 `ready -> running`，solver 会把这个过渡 patch 合并到最终 `StepResult.patch`

这保证 graph 层只需要继续消费 `final_step_result.patch`。

## ExecutePhase 外层循环

当前 `run_execute_phase(...)` 的正式行为如下：

1. 选择 `ready / running` node
2. 调用 `RuntimeSolver.solve_current_node(...)`
3. 应用 `SolverResult.final_step_result.patch`
4. 刷新 `runtime_state.active_node_id`
5. 若还有可执行 node，则继续
6. 若没有可执行 node，则收口 graph 终态

当前 graph 终态规则：

1. 全部 node `completed`：
   - graph 收为 `completed`
2. 仍有未完成 node 但无可继续推进节点：
   - graph 收为 `blocked`

## 当前保护与边界

当前已加入：

1. `max_steps_per_node = 20`
2. 步数超限时当前统一收为 `blocked`
3. stale `active_node_id` 不再强行复用

当前尚未进入：

1. `Completion Evaluator`
2. `Reflexion`
3. `Re-plan`
4. subagent
5. parallel node execution

## 当前测试覆盖

当前已覆盖：

1. `pending -> ready`
2. `pending` 依赖未完成时不推进
3. 缺失依赖时报错
4. `ready -> running -> completed`
5. `blocked / failed` 信号收口
6. 步数超限收为 `blocked`
7. execute graph 级循环与 graph 终态
8. host 测试对 solver 主链的最小集成
