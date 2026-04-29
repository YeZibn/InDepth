# Solver / ExecutePhase 实现说明

## 当前范围

当前 `ExecutePhase` 已从早期最小推进链升级为正式 `Solver` 主链。

当前已实现：

1. `RuntimeSolver`
2. `SolverResult`
3. graph 级 execute 主循环
4. 单 node 多轮 step solve
5. node 状态收口后的 graph 回写
6. `CompletionEvaluator`
7. `RuntimeReflexion`
8. judge 基座复用
9. node 级 `request_replan` 上抬与当前 node 收口

对应代码：

1. [src/rtv2/solver/runtime_solver.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/runtime_solver.py)
2. [src/rtv2/solver/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/models.py)
3. [src/rtv2/solver/completion_evaluator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/completion_evaluator.py)
4. [src/rtv2/solver/reflexion.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/reflexion.py)
5. [src/rtv2/judge/base.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/judge/base.py)
6. [src/rtv2/orchestrator/runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
7. [tests/test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)

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
4. `CompletionEvaluator`
   - 负责 node 进入 `completed` 前的独立完成判定
5. `RuntimeReflexion`
   - 负责失败诊断、下一步建议和 memory 写入输入生成
   - 当前已接入统一 prompt + runtime memory 主链

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
4. `control_signal`
   - 当前 solve 是否向上抛显式控制信号
   - 第一版只保留 `request_replan`

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
   - 先构造 `CompletionCheckInput`
   - 再调用 `CompletionEvaluator`
   - evaluator `pass` 才正式收为 `completed`
   - evaluator `fail` 时转入 `RuntimeReflexion`
3. `blocked`
   - 先转入 `RuntimeReflexion`
4. `failed`
   - 先转入 `RuntimeReflexion`

## 完成判定与反思链路

当前 `Solver` 在 node 级的正式顺序如下：

1. actor 正常执行 step
2. 若 `status_signal = ready_for_completion`
   - orchestrator 额外生成 `CompletionCheckInput`
   - `CompletionEvaluator` 做独立判定
3. evaluator `pass`
   - 当前 node 收为 `completed`
4. evaluator `fail`
   - 生成 `ReflexionInput`
   - `RuntimeReflexion` 返回：
     - `summary`
     - `next_attempt_hint`
     - `action`
   - solver 再消费该动作
5. 若 step 直接 `blocked / failed`
   - 同样先过 `RuntimeReflexion`

当前 `RuntimeReflexion` 已不再只依赖局部硬编码失败摘要。

当前执行链路中：

1. orchestrator 会为 node 级 reflexion 组装三段 prompt
2. prompt 会注入：
   - 当前失败锚点
   - issues
   - task 级 runtime memory
3. `RuntimeReflexion` 消费的是主链 prompt，而不是孤立小 prompt

当前 `ReflexionAction` 的 solver 消费规则为：

1. `retry_current_node`
   - 继续当前 node
2. `mark_blocked`
   - 当前 node 收为 `blocked`
3. `mark_failed`
   - 当前 node 收为 `failed`
4. `request_replan`
   - 当前 node 会先正式收为 `failed`
   - 再显式上抛 `SolverControlSignal.REQUEST_REPLAN`

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
3. solver 显式请求 `request_replan`：
   - orchestrator 写入正式 `request_replan`
   - 回流 `prepare`

## 当前保护与边界

当前已加入：

1. `max_steps_per_node = 20`
2. 步数超限时当前统一收为 `blocked`
3. stale `active_node_id` 不再强行复用
4. `CompletionEvaluator.max_rounds = 10`
5. `RuntimeReflexion.max_rounds = 10`
6. node 级 reflexion 已接入统一 prompt + memory 主链

当前尚未进入：

1. `abandoned` 与 replan 的共存语义
2. subagent
3. parallel node execution

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
9. evaluator `pass / fail`
10. reflexion memory 写入
11. `request_replan` 控制信号上抛
