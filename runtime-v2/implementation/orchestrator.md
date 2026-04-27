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
   - 先产出最小 `TaskGraphPatch | None`
   - 若 patch 非空，则通过 `TaskGraphStore.apply_patch(...)` 正式回写 graph
   - 用返回的新 graph 覆盖 `context.domain_state.task_graph_state`
   - 若 patch 带 `active_node_id`，则同步 `runtime_state.active_node_id`
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

## `initialize_minimal_graph(...)` 的作用

`initialize_minimal_graph(...)` 用于在当前 graph 为空时，产出第一版最小起始节点 patch。

当前规则如下：

1. 只有 `task_graph_state.nodes` 为空时才触发
2. 当前只新增 1 个最小初始 node
3. 初始 node 当前固定为：
   - `name = "Handle user request"`
   - `kind = "execution"`
   - `description = run_identity.user_input`
   - `node_status = ready`
   - `owner = "main"`
   - `dependencies = []`
   - `order = 1`
4. 当前返回 `TaskGraphPatch`
5. patch 当前同时回写 `active_node_id`

当前这一步明确：

1. 空图初始化既是兜底，也是第一版最小起始策略
2. 当前不直接改 graph
3. 当前不写 store
4. 当前不改 `graph_status`

## `advance_node_minimally(...)` 的作用

`advance_node_minimally(...)` 用于在不接 LLM、不接 tool 的前提下，给当前被选中的 node 产出最小状态推进 patch。

当前最小规则如下：

1. `pending -> ready`
   - 前提：所有依赖节点都已经 `completed`
2. `ready -> running`
3. `running -> completed`
4. 其他状态当前返回 `None`

当前这一步明确：

1. 缺失依赖节点时显式抛错
2. 当前不写 `runtime_state`
3. `runtime_state.active_node_id` 由 `run_execute_phase(...)` 在选中 node 后负责同步
4. 当前不写 notes / artifacts / evidence 占位内容

## 当前 execute 补充规则

当前 `run_execute_phase(...)` 在选中 node 后，会先同步：

1. `runtime_state.active_node_id = selected_node.node_id`

当前 execute 结果回写 graph 的最小链路如下：

1. 空图时：
   - 调用 `initialize_minimal_graph(...)`
   - 拿到初始化 patch
   - 通过 `graph_store.apply_patch(...)` 写回 graph
2. 已有选中 node 时：
   - 调用 `advance_node_minimally(...)`
   - 拿到最小推进 patch
   - 通过 `graph_store.apply_patch(...)` 写回 graph
3. patch 写回完成后：
   - `context.domain_state.task_graph_state` 被替换为最新 graph
   - 若 patch 指定 `active_node_id`，则同步到 `runtime_state.active_node_id`

当前这一步明确：

1. orchestrator 现在正式依赖 `TaskGraphStore`
2. 当前只打通最小 write-back 闭环
3. 当前不引入 `StepResult`
4. 当前不引入更完整的 patch 合并/强校验策略

## 下一步

orchestrator 层下一步预计进入：

1. `TaskGraphStore.apply_patch(...)` 的执行推进合并与校验增强
