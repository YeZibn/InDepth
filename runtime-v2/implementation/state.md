# 状态层实现说明

## 当前范围

当前状态层已正式落地四组最小类型：

1. `RunIdentity`
2. `RunLifecycle`
3. `RuntimeState`
4. `DomainState`

对应代码：

1. [src/rtv2/state/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/state/models.py)
2. [tests/test_run_identity.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_run_identity.py)

## 为什么先实现 `RunIdentity`

状态层实现顺序不是随意的。当前优先实现 `RunIdentity`，原因是：

1. 它是 `RunContext` 的最小锚点。
2. 它同时连接 `RuntimeHost` 和 `RuntimeOrchestrator`。
3. `session_id / task_id / run_id` 的语义如果不先稳定，后面 host、task graph 和事件链都会漂。

## `RunIdentity` 的作用

`RunIdentity` 用于表达一次具体 run 的最小正式标识与输入锚点。

当前字段包括：

1. `session_id`
2. `task_id`
3. `run_id`
4. `user_input`
5. `goal`

它当前承担两类职责：

1. 标识职责：
   明确这次 run 属于哪个 session、哪个 task、哪个具体执行实例。
2. 锚点职责：
   为后续 orchestrator、finalize 和 closeout 提供这次 run 的输入目标锚点。

## 当前设计思想

当前对 `RunIdentity` 的实现思想有 4 条：

1. 它是轻量正式对象，不混入运行中临时状态。
2. 它只表达稳定身份和目标锚点，不表达 phase、graph 或工具结果。
3. 它优先服务主链控制，而不是服务调试展示。
4. 它采用 dataclass + slots 的最小实现，先保证结构稳定，再扩展周边类型。

## 当前边界

当前 `RunIdentity` 明确不负责：

1. phase/lifecycle 状态
2. task graph 执行位置
3. tool 或 subagent 结果
4. finalize / handoff / verification 状态

## `RunLifecycle` 的作用

`RunLifecycle` 用于表达一次 run 当前所处的生命周期与 phase 控制信息。

当前字段包括：

1. `lifecycle_state`
2. `current_phase`
3. `result_status`
4. `stop_reason`

它当前承担两类职责：

1. 控制职责：
   为 orchestrator 和 phase/step 组件提供统一的运行阶段判断入口。
2. 收口职责：
   为 finalize 和 host 侧结果消费提供最小结果状态与停止原因。

## 为什么当前就实现 `RunLifecycle`

当前优先补 `RunLifecycle`，原因是：

1. `S4` 已经明确移除了独立 `PhaseState`。
2. `S3` 当前正式骨架依赖 `run_lifecycle.current_phase` 驱动 step loop。
3. 如果没有 `RunLifecycle`，后面 `RuntimeOrchestrator` 会缺少正式 phase 控制对象。

## 当前设计思想

当前对 `RunLifecycle` 的实现思想有 4 条：

1. 它只保留第一版主链需要的最小 lifecycle / phase 信息。
2. 它替代旧设计中独立 `PhaseState` 的正式地位。
3. 它优先服务 orchestrator 控制，而不是服务复杂的历史追踪。
4. phase 当前采用显式枚举值，先固定主链三阶段。

## 当前边界

当前 `RunLifecycle` 明确不负责：

1. task graph 推进细节
2. tool 或 subagent 结果
3. verification 细节
4. closeout 正文内容

这些内容会在后续类型中分别进入：

1. `RunLifecycle`
2. `RuntimeState`
3. `DomainState`
4. `RunContext`

## `RuntimeState` 的作用

`RuntimeState` 用于表达主链执行过程中需要长期挂载的最小运行控制状态。

当前字段包括：

1. `active_node_id`
2. `compression_state`
3. `external_signal_state`
4. `finalize_return_input`

它当前承担三类职责：

1. 执行定位职责：
   用 `active_node_id` 表达当前主执行焦点。
2. 运行保障职责：
   用 `compression_state` 表达上下文压缩与预算状态。
3. 外部输入桥接职责：
   用 `external_signal_state` 和 `finalize_return_input` 承接等待信号与 finalize 返工输入。

## 为什么当前就实现 `RuntimeState`

当前优先补 `RuntimeState`，原因是：

1. `S4-T4` 已经把它定义为极简 `RunContext` 的正式一级区块。
2. `S3` 的 step loop 需要正式读取 `active_node_id`。
3. `S2-T5` 的“等待后重开新 run”口径需要正式的外部信号挂点。
4. `S11` 的 finalize fail 回灌 execute 需要正式的 `finalize_return_input`。

## 当前设计思想

当前对 `RuntimeState` 的实现思想有 4 条：

1. 只保留主链真正长期需要的运行控制状态。
2. 压缩状态、外部信号和 finalize 回灌统一归到 runtime 控制层，不分散到别处。
3. `SignalRef` 只保存引用，不保存完整正文内容。
4. 先用轻量 dataclass + enum 固定结构，再在后续步骤接入行为逻辑。

## 当前边界

当前 `RuntimeState` 明确不负责：

1. task graph 正式结构本体
2. tool 或 subagent 结果正文
3. verification 结果正文
4. closeout 正文产物

这些内容会在后续类型中分别进入：

1. `DomainState`
2. `RunOutcome`
3. handoff / finalize 相关结构

## `DomainState` 的作用

`DomainState` 用于承接极简 `RunContext` 中仍然需要长期挂载的领域态。

当前字段包括：

1. `task_graph_state`
2. `verification_state`

其中：

1. `task_graph_state` 是执行骨架主位
2. `verification_state` 是按需出现的轻量验证态

## 为什么当前就实现 `DomainState`

当前优先补 `DomainState`，原因是：

1. `RunContext` 的四大一级区块里，`domain_state` 是最后一个未落代码的主位
2. `S4-T4` 已经明确 verification 不进入一级主状态，而是挂在 `domain_state`
3. 后续 `RunContext` 的实现需要一个稳定的 domain 壳层

## 当前设计思想

当前对 `DomainState` 的实现思想有 4 条：

1. 先把领域态壳层立住，再分别细化内部对象
2. `verification_state` 保持轻量，不扩成完整 closeout 产物
3. 当前不跨步骤提前实现完整 `TaskGraphState`
4. 因此当前先让 `DomainState` 承接 task graph 对象引用，等 Step 03 再收紧到正式 `TaskGraphState`

## 当前边界

当前 `DomainState` 明确不负责：

1. task graph patch 应用逻辑
2. verification 结果正文
3. handoff / closeout 主体
4. runtime 控制字段

## 下一步

状态层下一步预计继续落以下类型：

1. 极简 `RunContext`
2. Step 03 中再把 `task_graph_state` 收紧到正式 `TaskGraphState`
