# 宿主标识层实现说明

## 当前范围

当前宿主层只正式落地了标识与输入映射相关的最小结构，还没有进入 `RuntimeHost` 行为实现。

当前已实现：

1. `RuntimeHostState`
2. `HostTaskRef`
3. `StartRunIdentity`

对应代码：

1. [src/rtv2/host/interfaces.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/host/interfaces.py)
2. [tests/test_host_identity.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_host_identity.py)

## 为什么先落宿主标识结构

当前先落这组结构，原因是：

1. `Step 02` 需要把 `session_id / task_id / run_id` 的正式承载位置补完整。
2. `Step 04` 的 `RuntimeHost` 行为实现需要依赖稳定的数据边界，而不应边写方法边改结构。
3. `S2-T3 / T4 / T5` 已经把“host 管理标识、等待后重开新 run”的口径定死，适合先固化成最小正式类型。

## `RuntimeHostState` 的作用

`RuntimeHostState` 用于暴露宿主当前绑定快照。

当前字段包括：

1. `session_id`
2. `current_task_id`
3. `active_run_id`

它当前承担两类职责：

1. 宿主快照职责：
   给 CLI / API 一个最小可读的 host 绑定状态。
2. 生命周期锚点职责：
   体现 `session -> task -> run` 的当前宿主绑定关系。

## `HostTaskRef` 的作用

`HostTaskRef` 用于表达 `start_task(...)` 一类宿主操作的最小返回。

当前只保留：

1. `task_id`

原因是第一版 `start_task(...)` 本身不负责启动 runtime，只负责切换宿主当前任务上下文。

## `StartRunIdentity` 的作用

`StartRunIdentity` 用于表达 host 在启动一次新 run 时，传给 runtime 的最小标识输入。

当前字段包括：

1. `session_id`
2. `task_id`
3. `run_id`
4. `user_input`

它当前承担两类职责：

1. 输入映射职责：
   把 host 管理的三层标识和本轮用户输入收口成一次正式 `start-run` 输入。
2. 边界约束职责：
   明确 runtime core 只消费这些宿主标识，不负责自行生成。

## 当前设计思想

当前对宿主标识层的实现思想有 4 条：

1. 先固化标识结构，不提前实现 host 行为。
2. `session_id / task_id / run_id` 的生成职责继续明确留在 host。
3. 等待后继续推进仍然只表现为新的 `StartRunIdentity`，不引入 `resume-run` 结构。
4. 字段先保持最小，不把历史记录、标签、诊断信息混入第一版正式对象。

## 当前边界

当前宿主标识层明确不负责：

1. `RuntimeHost` 方法实现
2. `task_id / run_id` 实际生成策略
3. 默认 task 自动补建逻辑
4. 等待后重开新 run 的宿主行为编排

这些内容会在 `Step 04` 再正式落地。

## 下一步

宿主层下一步预计进入：

1. `RuntimeHost` 最小接口与行为骨架
2. `start_task(...)` / `submit_user_input(...)` / `reset_session()` 的最小实现
3. “等待后重开新 run” 的宿主前置处理
