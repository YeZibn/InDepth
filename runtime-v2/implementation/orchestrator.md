# RuntimeOrchestrator 实现说明

## 当前范围

当前 orchestrator 层已正式落地初始上下文构建、真实 `PreparePhase` planner 链、graph 级 `ExecutePhase / Solver` 主循环以及真实 `FinalizePhase / Verification` 收口链。

当前已实现：

1. `RuntimeOrchestrator`
2. `build_initial_context(...)`
3. `run(...)` 最小真实主链
4. `run_prepare_phase(...)`
5. `run_execute_phase(...)`
6. `run_finalize_phase(...)`
7. `prepare` planner payload -> `PrepareResult.patch` 规范化与回写
8. `SolverResult` 消费与 graph 终态收口
9. finalize generator 与 verifier 编排
10. `request_replan` 控制链路与主链回流

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

这表示主 runtime 链已具备：

1. `prepare` 的真实 planning
2. `execute` 的 graph 级求解循环
3. `finalize` 的真实验证与 host 收口

## 当前 phase 规则

当前三阶段的最小规则如下：

1. `run_prepare_phase(...)`
   - 要求输入 phase 为 `PREPARE`
   - 追加 `run-start` memory entry
   - 构造 prepare prompt
   - 发起单次 planner model 调用
   - 将 planner payload 规范化成 `PrepareResult`
   - 将 `PrepareResult.patch` 回写到正式 graph
   - 回写 `run_identity.goal`
   - 回写 `runtime_state.prepare_result`
   - 追加轻量 prepare memory entry
   - 推进到 `EXECUTE`
2. `run_execute_phase(...)`
   - 要求输入 phase 为 `EXECUTE`
   - 选择当前 `ready / running` node
   - 调用 `RuntimeSolver.solve_current_node(...)`
   - 消费 `SolverResult.final_step_result.patch`
   - 刷新 `runtime_state.active_node_id`
   - 若收到 `request_replan`，则回流 `PREPARE`
   - 若无可执行 node，则收口 graph 终态
   - 推进到 `FINALIZE`
   - 写入：
     - `result_status = "completed"`
     - `stop_reason = "execute_finished"`
3. `run_finalize_phase(...)`
   - 要求输入 phase 为 `FINALIZE`
   - 要求 graph 全部 `completed`
   - 调 finalize generator 生成 `final_output / graph_summary`
   - 组装 `Handoff`
   - 调独立 `RuntimeVerifier`
   - verifier `fail` 时先过 run 级 `Reflexion`
   - 根据最终动作收口为 `HostRunResult` 或回流 `PREPARE`
4. phase 顺序不对时，当前显式抛错

## 当前边界

当前 orchestrator 层明确不负责：

1. prepare 内多轮循环
2. 非空图下更复杂的替换式 planning 策略
3. finalize 内 tool loop
4. `abandoned` 与 replan 的共存语义
5. phase 间复杂闭环

这些内容会在后续模块继续落地。

## `select_active_node(...)` 的作用

`select_active_node(...)` 用于作为 execute phase 内部的最小规则选择器，决定当前应推进哪个 node。

当前规则按优先级如下：

1. 优先读取 `runtime_state.active_node_id`
2. 否则读取 `task_graph_state.active_node_id`
3. 否则返回第一个 `node_status in {ready, running}` 的 node
4. 若仍无可执行 node，则返回 `None`

当前这一步明确：

1. 不接 LLM
2. 不自动把 `pending` 提升成 `ready`
3. 不修改 runtime 或 graph 状态
4. 不写 patch
5. 不调用 store
6. 若 active node 引用失效，则显式抛错

## 当前 execute / solver 主循环

当前 `run_execute_phase(...)` 已不再自己做 node 内状态推进，而是改为 graph 层编排。

当前主循环如下：

1. `select_active_node(...)` 选择当前 `ready / running` node
2. `runtime_state.active_node_id` 同步为当前 node
3. 调用 `RuntimeSolver.solve_current_node(...)`
4. 通过 `_apply_solver_result(...)` 消费 `final_step_result.patch`
5. 通过 `_refresh_runtime_active_node(...)` 重新选择下一可执行 node
6. 若无可执行 node，则 `_finalize_execute_graph_status(...)`

当前这一步明确：

1. orchestrator 负责 graph 级循环
2. solver 负责 node 级循环
3. graph patch 继续只从 `StepResult.patch` 进入 graph store
4. stale `active_node_id` 当前会被忽略，而不是卡死在已完成 node 上
5. solver 若上抛 `request_replan`，orchestrator 会写入正式 `request_replan` 状态并回流 `prepare`

## `select_active_node(...)` 的当前规则补充

当前优先级仍然是：

1. `runtime_state.active_node_id`
2. `task_graph_state.active_node_id`
3. 第一个 `ready / running` node

但当前新增约束：

1. 只有目标 node 当前状态仍为 `ready / running` 时，active id 才继续有效
2. 若 active id 指向 `completed / blocked / failed` 节点，则回退到重新选择

## graph 终态收口

当前 `_finalize_execute_graph_status(...)` 的规则如下：

1. 若 graph 非空且全部 node 都是 `completed`
   - graph 收为 `completed`
   - active node 置空
2. 否则
   - graph 收为 `blocked`
   - active node 置空

## 当前 finalize 主链

当前 `run_finalize_phase(...)` 的正式规则如下：

1. graph 必须全部 `completed`
2. finalize generator 当前使用独立 `finalize_model_provider`
3. verifier 当前使用独立 `RuntimeVerifier`
4. 两条链都禁止 tool call
5. verifier verdict 为 `pass` 时：
   - `result_status = "pass"`
   - `stop_reason = "finalize_passed"`
   - host result 返回 `completed + final_output`
6. verifier verdict 为 `fail` 时：
   - 先写入 `finalize_return_input`
   - 再进入 run 级 `Reflexion`
7. run 级 `Reflexion.action = request_replan` 时：
   - 写入正式 `request_replan`
   - 回流 `prepare -> execute -> finalize`
8. run 级 `Reflexion.action = finish_failed` 时：
   - `result_status = "fail"`
   - `stop_reason = "final_verification_failed"`
   - host result 返回 `failed + empty output`

当前这一步明确：

1. finalize generator 与 verifier 已经分开挂载
2. verifier 是独立边界对象，不复用 execute 当前的 `ReActStepRunner`
3. verification fail 不再直接回退 execute
4. verification fail 第一版通过 run 级 `Reflexion` 决定：
   - `request_replan`
   - `finish_failed`

## 当前 replan 回流

当前 orchestrator 已正式接入最小 `request_replan` 回流。

当前规则如下：

1. `request_replan` 正式挂在 `runtime_state`
2. 第一次 `prepare` 仍支持空图初始化
3. replan 场景下允许在非空图上再次运行 `prepare`
4. 当前不先清空 graph
5. graph 继续通过新的 `prepare_result.patch` 在当前 graph 基础上修改
6. replan 成功后新的 `prepare_result` 直接覆盖旧结果
7. `prepare` 成功消费后才会清空 `runtime_state.request_replan`
8. replan 失败时保留旧 graph、旧 `prepare_result` 和 `request_replan`
9. replan 成功后 `runtime_state.active_node_id` 与 graph `active_node_id` 都以新 patch 为准重同步

## prepare fallback 的当前工程语义

当前当 prepare planner model 调用失败时：

1. 只有在初始 planning 场景，orchestrator 才会直接构造单节点最小 `TaskGraphPatch`
2. `goal` 收敛为旧 `goal` 或当前 `user_input`
3. replan 场景第一版完全禁止 fallback

这只是工程 fallback，不改变 prepare 的正式 planner 主语义。

## 当前 prepare 错误收口

当前已新增轻量结构化 `prepare` 失败承载：

1. `runtime_state.prepare_failure`

当前第一版错误类型固定为：

1. `planner_model_error`
2. `planner_payload_parse_error`
3. `planner_contract_error`
4. `planner_graph_semantic_error`
5. `planner_noop_patch`

当前规则如下：

1. 只有 `planner_model_error` 在初始 planning 场景允许 fallback
2. payload 解析失败、contract 失败、graph 语义失败、no-op patch 全部按硬失败收口

## 下一步

orchestrator 层下一步预计进入：

1. prepare payload 到 patch 的校验细化与错误分类增强
2. 非空图 / replan 场景下更复杂的 prepare patch 策略
3. finalize / verification 的更细分 run-level closeout 动作
