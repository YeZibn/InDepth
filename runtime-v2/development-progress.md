# runtime-v2 开发进度记录

## 文档目标

本文档用于记录 `runtime-v2` 从设计进入开发后的实际落地进度。

记录原则：

- 只记录已经完成或正在推进的开发工作
- 设计稿已完成不等于开发已完成，两者必须明确区分
- 每完成一个可独立验收的小模块，就在本文档补充一次
- 每次补充尽量包含时间、范围、结果、验证、遗留问题和下一步
- 不预先锁定过远的开发顺序，后续模块在讨论定稿后再追加记录

---

## 当前总体状态

- 项目阶段：设计阶段已闭环，已进入增量实现
- 设计文档状态：`S1 ~ S12` 第一版设计稿已完成
- 开发状态：已完成模块 01、模块 02、模块 03、模块 04、模块 05、模块 06
- 当前重点：讨论并推进模块 07，继续按子任务逐个对齐后再落地

---

## 当前已讨论并定稿的模块

### 模块 01：新实现工作区与目录骨架

- 模块目标：
  - 在 `runtime-v2` 下建立独立的新实现工作区
  - 固定新的包根、测试目录和各主模块代码落点
  - 先补最小说明文档，作为后续增量实现入口
- 已定子任务：
  - 任务 01：确认第一批实现范围
  - 任务 02：确定新代码包名与模块落点
  - 任务 03：建立最小目录骨架与占位文件
  - 任务 04：明确旧实现与新骨架的并存方式

### 模块 02：状态层与宿主标识层最小正式结构

- 模块目标：
  - 先把 runtime-v2 主链需要的最小正式状态结构落成代码
  - 固定 `RunContext` 的一级区块边界
  - 固定 host 管理的 `session_id / task_id / run_id` 最小承载对象
- 已定子任务：
  - 任务 01：实现 `RunIdentity`
  - 任务 02：实现 `RunLifecycle`
  - 任务 03：实现 `RuntimeState`
  - 任务 04：实现 `DomainState`
  - 任务 05：实现极简 `RunContext`
  - 任务 06：实现 `VerificationState`
  - 任务 07：实现宿主标识结构与 `session_id / task_id / run_id` 对应关系

### 模块 03：Task Graph 最小状态骨架

- 模块目标：
  - 先把 task graph 的最小正式状态表达落成代码
  - 收紧 `DomainState.task_graph_state` 的正式类型边界
  - 先固定 graph 与 node 的状态语义，不提前进入 patch、store 或 orchestrator 行为
- 已定子任务：
  - 任务 01：实现 `TaskGraphState`
  - 任务 02：实现 `TaskGraphNode`
  - 任务 03：实现 `TaskGraphStatus / NodeStatus`

当前进度：

- 任务 01：已完成
- 任务 02：已完成
- 任务 03：已完成

### 模块 04：Task Graph Patch 与最小 Store 骨架

- 模块目标：
  - 定义 step 对 task graph 的正式修改结果结构
  - 定义 task graph 的最小读写边界与状态持有层
  - 让 graph 状态具备“可被正式修改、可被正式保存”的基础能力
- 已定子任务：
  - 任务 01：实现 `TaskGraphPatch`
  - 任务 02：实现 `NodePatch`
  - 任务 03：实现 `TaskGraphStore` 接口
  - 任务 04：实现内存版 `TaskGraphStore`

当前进度：

- 任务 01：已完成
- 任务 02：已完成
- 任务 03：已完成
- 任务 04：已完成

### 模块 05：RuntimeHost 最小主链骨架

- 模块目标：
  - 建立宿主层正式入口对象
  - 先打通“发起一次新 run”的最小宿主主链
  - 保持 host 作为外层唯一正式执行入口，不提前扩展复杂等待状态机
- 已定子任务：
  - 任务 01：实现 `RuntimeHost` 最小类壳
  - 任务 02：实现 `start_task(...)`
  - 任务 03：实现 `submit_user_input(...)`
  - 任务 04：实现默认 task 自动补建

当前进度：

- 任务 01：已完成
- 任务 02：已完成
- 任务 03：已完成
- 任务 04：已完成

### 模块 06：RuntimeOrchestrator 最小执行主链骨架

- 模块目标：
  - 建立 orchestrator 的正式执行主链骨架
  - 从 `StartRunIdentity` 进入一次真实 run，而不是继续返回纯 stub
  - 先打通最小 `prepare -> execute -> finalize` 链路，不提前引入 prompt、tool、verification 等复杂能力
- 已定子任务：
  - 任务 01：实现 `build_initial_context(...)`
  - 任务 02：正式替换 `RuntimeOrchestrator.run(...)` stub
  - 任务 03：实现 `prepare / execute / finalize` 最小 phase 壳
  - 任务 04：实现 orchestrator 到 `HostRunResult` 的真实返回收口

当前进度：

- 任务 01：已完成
- 任务 02：已完成
- 任务 03：已完成
- 任务 04：已完成

### 模块 07：Execute Phase 最小任务图推进

- 模块目标：
  - 让 execute phase 开始真正推进 task graph，而不再只是简单切 phase
  - 为后续 prompt/tool/model 接线之前，先建立最小任务图推进闭环
  - 先让 execute 能够选择节点、初始化空图、推进节点状态并回写 graph
- 已定子任务：
  - 任务 01：选择当前执行节点
  - 任务 02：空图初始化最小节点
  - 任务 03：最小 node 状态推进
  - 任务 04：execute 结果回写 graph

当前进度：

- 任务 01：已完成
- 任务 02：已完成
- 任务 03：已完成
- 任务 04：已完成

### 模块 08：TaskGraphStore patch 提交链增强

- 模块目标：
  - 把当前已经打通的 `execute -> patch -> apply_patch(...) -> graph` 链路，与现有设计稿重新对齐
  - 先收口 patch 提交链的正式设计边界，再逐步进入实现
  - 在设计对齐基础上，逐步完成 patch 合并、基础校验、状态流转校验与 orchestrator 集成收口
- 已定子任务：
  - 任务 01：对接现有设计稿并收口 patch 提交链设计
  - 任务 02：实现 patch 合并语义
  - 任务 03：实现 patch 基础一致性校验
  - 任务 04：实现状态流转校验与 orchestrator 集成收口

当前进度：

- 任务 01：已完成
- 任务 02：未开始
- 任务 03：未开始
- 任务 04：未开始

---

## 开发记录

### 2026-04-27

#### 记录 018：完成模块 08 的任务 01 patch 提交链设计对接与收口

- 状态：已完成
- 范围：完成模块 08 的第一个子任务，对接当前 `TaskGraphStore.apply_patch(...)` 相关设计稿与现有实现思路，收口 patch 提交链的正式设计边界，不进入代码实现
- 结果：
  - 已确认 `artifacts / evidence` 不再沿用裸 `string` 作为正式设计目标
  - 已确定统一最小引用结构：
    - `ResultRef { ref_id, ref_type, title, content }`
  - 已确认当前执行推进阶段仍只开放以下节点执行结果字段：
    - `node_status`
    - `block_reason`
    - `failure_reason`
    - `notes`
    - `artifacts`
    - `evidence`
  - 已确认当前模块只处理执行推进 patch 提交链，不进入图结构重规划
  - 已确认 `TaskGraphStore.apply_patch(...)` 是当前执行推进阶段的正式 graph 提交边界，职责包括：
    - patch merge
    - 基础一致性校验
    - 状态流转校验
  - 已确认当前模块虽然不实现 `StepResult`，但未来 `StepResult.patch` 的 graph 变更部分应收敛为 `TaskGraphPatch`
  - 已同步更新设计稿：
    - `runtime-v2/design/s3/step-orchestrator-contract-t5-design-v1.md`
    - `runtime-v2/design/s5/task-graph-transition-rules-t5-design-v1.md`
    - `runtime-v2/design/s5/task-graph-skeleton-store-t7-design-v1.md`
- 验证结果：
  - 本任务为设计对接与收口任务，无代码执行验证
- 遗留问题：
  - 当前代码模型中的 `artifacts / evidence` 仍是 `list[str]`
  - 需要在后续实现任务中升级到正式引用结构并补测试
- 下一步：
  - 进入模块 08 的任务 02：实现 patch 合并语义

### 2026-04-27

#### 记录 017：完成模块 07 的任务 04 execute 结果最小回写 graph

- 状态：已完成
- 范围：完成 execute phase 最小任务图推进模块中的第四个子任务，只落最小 patch write-back 闭环，不提前引入 `StepResult`、ReAct step 正式执行模型或更强的 store 校验策略
- 结果：
  - 已在 `runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py` 为 `RuntimeOrchestrator` 引入 `TaskGraphStore` 依赖
  - 已在 `run_execute_phase(...)` 打通最小回写链路：
    - 空图时调用 `initialize_minimal_graph(...)` 产出 patch
    - 选中 node 时调用 `advance_node_minimally(...)` 产出 patch
    - patch 非空时通过 `graph_store.apply_patch(...)` 正式写回 graph
    - 用最新 graph 覆盖 `context.domain_state.task_graph_state`
    - patch 若带 `active_node_id`，则同步 `runtime_state.active_node_id`
  - 已同步更新 host / orchestrator 测试构造方式，使 orchestrator 显式持有 graph store
  - 已同步更新 orchestrator 实现说明：
    - `runtime-v2/implementation/orchestrator.md`
- 验证结果：
  - 已补 execute 初始化 patch 回写、节点推进 patch 回写、graph version 递增与 runtime active 对齐测试
  - 尝试执行：
    - `python3 -m unittest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_host.py`
  - 当前环境阻塞：
    - 系统默认 `python3` 为 3.9
    - 项目代码使用 `dataclass(slots=True)`，需 Python 3.10+
    - 因此当前未能在本机完成自动化测试跑通
- 遗留问题：
  - `TaskGraphStore.apply_patch(...)` 仍未进入执行推进专用的合并与状态流转校验增强
  - `StepResult` 与 step 正式执行协议仍属于后续模块
- 下一步：
  - 进入下一模块或后续子任务时，再单独推进 `apply_patch(...)` 规则增强

### 2026-04-27

#### 记录 016：完成模块 07 的任务 03 最小 node 状态推进

- 状态：已完成
- 范围：完成 execute phase 最小任务图推进模块中的第三个子任务，只落最小 node 状态推进 patch 生成和 execute 内的 runtime active 对齐，不提前进入 graph 写回
- 结果：
  - 已在 `runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py` 落地 `advance_node_minimally(...)`
  - 当前最小推进规则已明确：
    - `pending -> ready`，前提是依赖节点全部 `completed`
    - `ready -> running`
    - `running -> completed`
    - 其他状态返回 `None`
  - 当前已明确：
    - 缺失依赖节点时显式抛错
    - 当前不写 notes / artifacts / evidence 占位内容
    - `advance_node_minimally(...)` 不写 `runtime_state`
  - 当前 execute 内已明确：
    - 在选中 node 后，先同步 `runtime_state.active_node_id`
  - 已同步更新 orchestrator 实现说明：
    - `runtime-v2/implementation/orchestrator.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py`
  - 已补依赖完成/未完成、缺失依赖、状态推进和 runtime active 对齐测试
- 遗留问题：
  - execute 结果回写 graph 还未进入实现
- 下一步：
  - 进入模块 07 的任务 04：讨论并实现 execute 结果回写 graph

### 2026-04-27

#### 记录 015：完成模块 07 的任务 02 空图初始化最小节点

- 状态：已完成
- 范围：完成 execute phase 最小任务图推进模块中的第二个子任务，只落空图时的最小初始化 patch 生成，不提前进入节点状态推进或 graph 写回
- 结果：
  - 已在 `runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py` 落地 `initialize_minimal_graph(...)`
  - 当前仅在 `task_graph_state.nodes` 为空时触发
  - 当前只生成 1 个最小初始 node
  - 初始 node 当前已明确：
    - `name = "Handle user request"`
    - `kind = "execution"`
    - `description = run_identity.user_input`
    - `node_status = ready`
    - `owner = "main"`
    - `dependencies = []`
    - `order = 1`
  - 当前返回 `TaskGraphPatch`
  - 当前 patch 同时回写 `active_node_id`
  - 当前已明确：
    - 空图初始化既是兜底，也是第一版最小起始策略
    - 不直接改 graph
    - 不写 store
    - 不改 `graph_status`
  - 已同步更新 orchestrator 实现说明：
    - `runtime-v2/implementation/orchestrator.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py`
  - 已补空图生成 patch 和非空图返回 `None` 的测试
- 遗留问题：
  - 最小 node 状态推进还未进入实现
  - execute 结果回写 graph 还未进入实现
- 下一步：
  - 进入模块 07 的任务 03：讨论并实现最小 node 状态推进

### 2026-04-27

#### 记录 014：完成模块 07 的任务 01 选择当前执行节点

- 状态：已完成
- 范围：完成 execute phase 最小任务图推进模块中的第一个子任务，只落 execute 内部的最小规则选择器，不提前进入空图初始化、状态推进或 graph 回写
- 结果：
  - 已在 `runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py` 落地 `select_active_node(...)`
  - 当前正式选择优先级已明确：
    - 优先 `runtime_state.active_node_id`
    - 其次 `task_graph_state.active_node_id`
    - 再其次第一个 `ready / running` node
    - 若无可执行 node，则返回 `None`
  - 当前已明确：
    - `select_active_node(...)` 不接 LLM
    - 不自动把 `pending` 提升成 `ready`
    - 不修改 runtime 或 graph 状态
    - 不写 patch
    - 不调用 store
  - 当前已明确：
    - 若 runtime active node 引用失效，则显式抛错
    - 若 graph active node 引用失效，则显式抛错
  - 已同步更新 orchestrator 实现说明：
    - `runtime-v2/implementation/orchestrator.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py`
  - 已补优先级、空结果和失效引用报错测试
- 遗留问题：
  - 空图初始化最小节点还未进入实现
  - 最小 node 状态推进还未进入实现
  - execute 结果回写 graph 还未进入实现
- 下一步：
  - 进入模块 07 的任务 02：讨论并实现空图初始化最小节点

### 2026-04-27

#### 记录 013：完成模块 06 的任务 02 `RuntimeOrchestrator.run(...)`、任务 03 最小 phase 壳与任务 04 返回收口

- 状态：已完成
- 范围：完成 RuntimeOrchestrator 主链骨架模块中的任务 02、任务 03 和任务 04，正式替换 `run(...)` stub，落最小 `prepare -> execute -> finalize` 主链，并收口为真实 `HostRunResult`
- 结果：
  - 已在 `runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py` 正式替换 `RuntimeOrchestrator.run(...)` stub
  - 当前 `run(...)` 调用顺序已明确：
    - `build_initial_context(...)`
    - `run_prepare_phase(...)`
    - `run_execute_phase(...)`
    - `run_finalize_phase(...)`
  - 已落最小 phase 壳：
    - `run_prepare_phase(...)`
    - `run_execute_phase(...)`
    - `run_finalize_phase(...)`
  - 当前最小状态推进规则已明确：
    - `PREPARE -> EXECUTE`
    - `EXECUTE -> FINALIZE`
    - `result_status = "completed"`
    - `stop_reason = "execute_finished"`
  - 当前 phase 顺序不对时显式抛错
  - 当前 orchestrator 返回已不再使用 `runtime_state = "stub"`
  - 当前最小真实返回已明确：
    - `runtime_state = "completed"`
    - `output_text = ""`
  - 已同步更新 orchestrator 实现说明：
    - `runtime-v2/implementation/orchestrator.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py`
  - 已补主链调用、phase 推进和乱序报错测试
- 遗留问题：
  - phase 内部仍然只是最小状态推进，不包含真实执行逻辑
  - prompt / tool / verification 还未进入主链
- 下一步：
  - 讨论下一个小模块边界，决定是否开始 prompt/tool/model 接线，或先细化 execute phase

### 2026-04-27

#### 记录 012：完成模块 06 的任务 01 `build_initial_context(...)`

- 状态：已完成
- 范围：完成 RuntimeOrchestrator 主链骨架模块中的第一个子任务，只落初始上下文构建，不提前进入真实 phase 执行
- 结果：
  - 已在 `runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py` 落地 `build_initial_context(...)`
  - `build_initial_context(...)` 当前正式从 `StartRunIdentity` 组装最小 `RunContext`
  - 当前组装结果已明确：
    - `run_identity` 直接映射自 `StartRunIdentity`
    - `run_lifecycle` 初始化为 `running + PREPARE`
    - `runtime_state` 初始化为空运行时控制壳
    - `domain_state` 初始化为空领域壳
  - 当前初始 `TaskGraphState` 已明确：
    - 新建空 graph
    - `nodes = []`
    - `active_node_id = ""`
    - `graph_status = active`
    - `version = 1`
  - 当前已明确：
    - `graph_id` 不复用 `task_id`
    - `graph_id` 由 orchestrator 内部生成
  - 已新增 orchestrator 实现说明：
    - `runtime-v2/implementation/orchestrator.md`
  - 已同步实现说明入口：
    - `runtime-v2/implementation/README.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py`
  - 已补初始上下文结构和 `graph_id` 递增测试
- 遗留问题：
  - `RuntimeOrchestrator.run(...)` 仍然是 stub
  - `prepare / execute / finalize` 还未进入实现
- 下一步：
  - 进入模块 06 的任务 02：正式替换 `RuntimeOrchestrator.run(...)` stub

### 2026-04-26

#### 记录 011：完成模块 05 的任务 03 `submit_user_input(...)` 与任务 04 默认 task 自动补建

- 状态：已完成
- 范围：完成 RuntimeHost 主链骨架模块中的任务 03 和任务 04，正式落地宿主唯一执行入口 `submit_user_input(...)`，并一并收口默认 task 自动补建
- 结果：
  - 已在 `runtime-v2/src/rtv2/host/interfaces.py` 落地 `HostRunResult`
  - 已在 `runtime-v2/src/rtv2/host/runtime_host.py` 落地 `submit_user_input(user_input: str)`
  - 已在 `submit_user_input(...)` 内正式接入默认 task 自动补建
  - `submit_user_input(...)` 当前行为已明确：
    - 若当前没有 `task_id`，先自动补建默认 task
    - 默认 task 自动补建直接复用 `start_task()`
    - 通过 `HostIdGenerator.create_run_id()` 生成新的 `run_id`
    - 组装 `StartRunIdentity`
    - 调用 `orchestrator.run(...)`
    - 回写 `host_state.active_run_id`
    - 返回最小 `HostRunResult`
  - `HostRunResult` 当前正式固定以下字段：
    - `task_id`
    - `run_id`
    - `runtime_state`
    - `output_text`
  - 已在 `runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py` 落地最小宿主可调用入口 `run(...)`
  - 当前 orchestrator 返回显式占位结果：
    - `runtime_state = "stub"`
    - `output_text = ""`
  - 当前占位值已显式标注为 stub，不伪装成真实执行完成链路
  - 已同步更新宿主实现说明：
    - `runtime-v2/implementation/host.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_host.py`
  - 已补默认 task 自动补建和复用已有 task 的提交测试
- 遗留问题：
  - orchestrator 仍然只是宿主可调用 stub，尚未进入真实 phase 主链
  - 等待后重开新 run 的宿主逻辑还未进入实现
- 下一步：
  - 讨论下一个小模块边界，决定是否转入 orchestrator 真正主链骨架

### 2026-04-26

#### 记录 010：完成模块 05 的任务 02 `start_task(...)`

- 状态：已完成
- 范围：完成 RuntimeHost 主链骨架模块中的第二个子任务，只落 `start_task(...)` 的最小宿主任务切换行为，不提前进入执行链路
- 结果：
  - 已在 `runtime-v2/src/rtv2/host/runtime_host.py` 落地 `start_task(label: str = "")`
  - `start_task(...)` 当前保留 `label` 参数，但不持久化
  - 当前行为已明确：
    - 复用当前 `session_id`
    - 通过 `HostIdGenerator.create_task_id()` 生成新的 `task_id`
    - 回写 `host_state.current_task_id`
    - 清空 `host_state.active_run_id`
    - 返回 `HostTaskRef`
  - 当前已明确：
    - `start_task(...)` 不触发 `orchestrator`
    - `start_task(...)` 不调用 `graph_store`
  - 已同步更新宿主实现说明：
    - `runtime-v2/implementation/host.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_host.py`
  - 已补首次切换与重复切换测试
- 遗留问题：
  - `submit_user_input(...)` 还未进入实现
  - 默认 task 自动补建还未进入实现
- 下一步：
  - 进入模块 05 的任务 03：讨论并实现 `submit_user_input(...)`

### 2026-04-26

#### 记录 009：完成模块 05 的任务 01 `RuntimeHost` 最小类壳

- 状态：已完成
- 范围：完成 RuntimeHost 主链骨架模块中的第一个子任务，只落 `RuntimeHost` 最小类壳、显式 ID 生成器依赖和 `get_host_state()`，不提前实现 `start_task(...)` 或 `submit_user_input(...)`
- 结果：
  - 已在 `runtime-v2/src/rtv2/host/runtime_host.py` 落地 `RuntimeHost`
  - 已在 `runtime-v2/src/rtv2/host/interfaces.py` 落地 `HostIdGenerator`
  - `RuntimeHost` 当前正式挂接以下成员：
    - `host_state`
    - `graph_store`
    - `orchestrator`
    - `id_generator`
  - `RuntimeHost` 当前通过 `HostIdGenerator.create_session_id()` 在初始化时生成 `session_id`
  - 当前已落正式方法：
    - `get_host_state()`
  - `get_host_state()` 当前返回宿主状态快照，不直接暴露内部状态对象
  - 已同步更新宿主实现说明：
    - `runtime-v2/implementation/host.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_host.py`
  - 已补 host 初始化与快照返回测试
- 遗留问题：
  - `start_task(...)` 还未进入实现
  - `submit_user_input(...)` 还未进入实现
  - 默认 task 自动补建还未进入实现
- 下一步：
  - 进入模块 05 的任务 02：讨论并实现 `start_task(...)`

### 2026-04-26

#### 记录 008：完成模块 04 的任务 04 `InMemoryTaskGraphStore`

- 状态：已完成
- 范围：完成 task graph patch/store 模块中的第四个子任务，正式落地内存版 `TaskGraphStore`，只实现已定稿的最小读写与 patch 应用规则，不扩展调度能力
- 结果：
  - 已在 `runtime-v2/src/rtv2/task_graph/store.py` 落地 `InMemoryTaskGraphStore`
  - 内部当前使用 `dict[str, TaskGraphState]` 持有 graph
  - `save_graph` 当前采用整图覆盖保存
  - `apply_patch` 当前基于已有 graph 生成更新后的新快照
  - 当前实现已明确以下错误规则：
    - graph 不存在时，`apply_patch` 抛错
    - `node_updates` 指向不存在 node 时抛错
    - `new_nodes` 出现重复 `node_id` 时抛错
    - `active_node_id` 指向更新后不存在 node 时抛错
  - 当前实现采用快照语义，避免外部对象直接污染 store 内部状态
  - 已同步更新 task graph 实现说明：
    - `runtime-v2/implementation/task-graph.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_in_memory_task_graph_store.py`
  - 已补保存、读取、patch 应用和错误路径测试
- 遗留问题：
  - 更完整的 patch 应用细则还未上升为单独规范文档
  - 仍未进入 orchestrator 或 host 对 graph store 的正式接线
- 下一步：
  - 讨论下一个小模块边界，决定是否开始 `RuntimeHost` 或 orchestrator 主链骨架

### 2026-04-26

#### 记录 007：完成模块 04 的任务 03 `TaskGraphStore` 接口

- 状态：已完成
- 范围：完成 task graph patch/store 模块中的第三个子任务，只落 `TaskGraphStore` 接口契约，不提前实现内存版 store
- 结果：
  - 已在 `runtime-v2/src/rtv2/task_graph/store.py` 落地 `TaskGraphStore`
  - `TaskGraphStore` 当前采用 `Protocol`
  - 当前正式固定以下 6 个接口：
    - `get_graph`
    - `save_graph`
    - `apply_patch`
    - `get_node`
    - `get_active_node`
    - `list_nodes`
  - store 当前明确只承担 graph 读写边界，不承担调度、推理或自动修复能力
  - 当前已明确：
    - `apply_patch` 找不到 `graph_id` 时，后续实现应抛错
    - `save_graph` 返回 `None`
  - 已同步更新 task graph 实现说明：
    - `runtime-v2/implementation/task-graph.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_task_graph_store_interface.py`
  - 已补接口方法和类型注解契约测试
- 遗留问题：
  - 内存版 `TaskGraphStore` 还未进入实现
  - patch 应用细则还未进入实现
- 下一步：
  - 进入模块 04 的任务 04：讨论并实现内存版 `TaskGraphStore`

### 2026-04-26

#### 记录 006：完成模块 04 的任务 02 `NodePatch`

- 状态：已完成
- 范围：完成 task graph patch/store 模块中的第二个子任务，正式落地 `NodePatch` 的字段级更新范围，不提前进入 store
- 结果：
  - 已在 `runtime-v2/src/rtv2/task_graph/models.py` 将 `NodePatch` 从过渡壳层收紧为正式字段级更新对象
  - `NodePatch` 当前正式固定以下字段：
    - `node_id`
    - `node_status`
    - `owner`
    - `dependencies`
    - `order`
    - `artifacts`
    - `evidence`
    - `notes`
    - `block_reason`
    - `failure_reason`
  - `NodePatch` 当前只允许修改运行时可变字段
  - 第一版明确不允许通过 `NodePatch` 修改：
    - `graph_id`
    - `name`
    - `kind`
    - `description`
  - `dependencies` 当前按整字段替换处理
  - `artifacts / evidence / notes` 当前按整字段替换处理
  - `None` 当前统一表达“不修改”
  - 已同步更新 task graph 实现说明：
    - `runtime-v2/implementation/task-graph.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_task_graph_state.py`
  - 已补 `NodePatch` 的最小字段与默认值测试
- 遗留问题：
  - `TaskGraphStore` 还未进入实现
  - graph patch 应用规则还未进入实现
- 下一步：
  - 进入模块 04 的任务 03：讨论并实现 `TaskGraphStore` 接口

### 2026-04-26

#### 记录 005：完成模块 04 的任务 01 `TaskGraphPatch`

- 状态：已完成
- 范围：完成 task graph patch/store 模块中的第一个子任务，只落 `TaskGraphPatch` 本体，并用过渡型 `NodePatch` 壳层承接 `node_updates`，不提前实现 `NodePatch` 的完整字段集合，也不进入 store
- 结果：
  - 已在 `runtime-v2/src/rtv2/task_graph/models.py` 落地 `TaskGraphPatch`
  - `TaskGraphPatch` 当前正式固定以下字段：
    - `node_updates`
    - `new_nodes`
    - `active_node_id`
    - `graph_status`
  - `node_updates` 当前保留为数组
  - `new_nodes` 当前直接使用完整 `TaskGraphNode`
  - `active_node_id` 当前使用 `None` 表达“不修改”
  - `graph_status` 当前使用 `None` 表达“不修改”
  - 第一版明确不引入：
    - `graph_notes`
    - `remove_nodes`
    - `replace_nodes`
    - `version_bump`
    - 调度控制字段
  - 已新增过渡型 `NodePatch` 壳层，当前只固定 `node_id`
  - 已同步更新 task graph 实现说明：
    - `runtime-v2/implementation/task-graph.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_task_graph_state.py`
  - 已补 patch 的默认值与最小字段测试
- 遗留问题：
  - `NodePatch` 还未收紧到正式字段级更新结构
  - `TaskGraphStore` 还未进入实现
  - graph patch 应用规则还未进入实现
- 下一步：
  - 进入模块 04 的任务 02：讨论并实现 `NodePatch`

### 2026-04-26

#### 记录 004：完成模块 03 的任务 02 `TaskGraphNode`

- 状态：已完成
- 范围：完成 task graph 最小状态骨架中的第二个子任务，正式落地 `TaskGraphNode`，并同步收口其直接依赖的 `NodeStatus`，不提前进入 patch 或 store
- 结果：
  - 已在 `runtime-v2/src/rtv2/task_graph/models.py` 落地 `TaskGraphNode`
  - 已引入 `NodeStatus`
  - `TaskGraphNode` 当前正式固定以下字段：
    - `node_id`
    - `graph_id`
    - `name`
    - `kind`
    - `description`
    - `node_status`
    - `owner`
    - `dependencies`
    - `order`
    - `artifacts`
    - `evidence`
    - `notes`
    - `block_reason`
    - `failure_reason`
  - `owner` 第一版固定为 `str`
  - `artifacts / evidence` 第一版固定为 `list[str]`
  - `dependencies` 第一版固定为依赖 `node_id` 列表
  - `NodeStatus` 当前按 8 个正式状态收口：
    - `pending`
    - `ready`
    - `running`
    - `blocked`
    - `paused`
    - `completed`
    - `failed`
    - `abandoned`
  - 因为 `NodeStatus` 是 `TaskGraphNode` 的直接依赖，因此模块 03 的任务 03 在本次一并完成，不再单独拆出独立代码落地
  - `TaskGraphState.nodes` 已从过渡态 `list[Any]` 收紧为 `list[TaskGraphNode]`
  - 已同步更新 task graph 实现说明：
    - `runtime-v2/implementation/task-graph.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_task_graph_state.py`
  - 已补 node 默认值与最小字段测试
- 遗留问题：
  - `TaskGraphPatch` 与 `TaskGraphStore` 还未进入实现
  - graph patch 应用规则还未进入实现
- 下一步：
  - 进入下一个模块讨论，决定是否开始 patch / store 的最小正式结构

### 2026-04-26

#### 记录 003：完成模块 03 的任务 01 `TaskGraphState`

- 状态：已完成
- 范围：完成 task graph 最小状态骨架中的第一个子任务，只落 `TaskGraphState` 与其直接依赖的图级状态，不提前实现 `TaskGraphNode`、`NodeStatus`、patch 或 store
- 结果：
  - 已在 `runtime-v2/src/rtv2/task_graph/models.py` 落地 `TaskGraphState`
  - 已引入图级状态枚举 `TaskGraphStatus`
  - `TaskGraphState` 当前正式固定 5 个字段：
    - `graph_id`
    - `nodes`
    - `active_node_id`
    - `graph_status`
    - `version`
  - 当前 `nodes` 先保持 `list` 结构
  - 当前 `active_node_id` 保留在 `TaskGraphState` 中
  - 当前 `graph_status` 固定为 `active / blocked / completed / abandoned`
  - 当前 `version` 从第一版即进入正式结构
  - 已新增 task graph 实现说明文档：
    - `runtime-v2/implementation/task-graph.md`
  - 已同步实现说明入口：
    - `runtime-v2/implementation/README.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_task_graph_state.py`
  - 预期与默认字段测试已补齐
- 遗留问题：
  - `nodes` 当前仍是过渡态 `list[Any]`，等待 `TaskGraphNode` 子任务收紧
  - `NodeStatus` 还未正式收口
  - `TaskGraphPatch` 与 `TaskGraphStore` 还未进入实现
- 下一步：
  - 进入模块 03 的任务 02：讨论并实现 `TaskGraphNode`

### 2026-04-26

#### 记录 002：完成模块 02 状态层与宿主标识层最小正式结构

- 状态：已完成
- 范围：完成状态层与宿主标识层的第一批正式类型落地，只收口最小结构，不提前实现 host 行为、task graph 行为或 orchestrator 行为
- 结果：
  - 状态模型已集中落在 `runtime-v2/src/rtv2/state/models.py`
  - 已正式落地 `RunIdentity`、`RunLifecycle`、`RuntimeState`、`DomainState`、`VerificationState`、`RunContext`
  - `RunContext` 已固定为 4 个一级区块：
    - `run_identity`
    - `run_lifecycle`
    - `runtime_state`
    - `domain_state`
  - 宿主标识结构已落在 `runtime-v2/src/rtv2/host/interfaces.py`
  - 已正式落地 `RuntimeHostState`、`HostTaskRef`、`StartRunIdentity`
  - 已新增状态层与宿主层的实现说明文档：
    - `runtime-v2/implementation/state.md`
    - `runtime-v2/implementation/host.md`
  - 已同步实现说明入口：
    - `runtime-v2/implementation/README.md`
- 验证结果：
  - `python3 -m pytest /Users/yezibin/Project/InDepth/runtime-v2/tests/test_run_identity.py /Users/yezibin/Project/InDepth/runtime-v2/tests/test_host_identity.py`
  - 结果：`13 passed`
- 遗留问题：
  - `task_graph_state` 当前仍是过渡态引用，尚未收紧到正式 `TaskGraphState`
  - 尚未实现 `RuntimeHost` 方法
  - 尚未实现 `task_id / run_id` 的生成策略
  - 尚未实现默认 task 自动补建和等待后重开新 run 的宿主行为
- 下一步：
  - 先讨论下一个小模块的边界，再决定是否进入 `TaskGraphState` 的最小正式类型

### 2026-04-26

#### 记录 001：完成模块 01 新实现工作区与目录骨架

- 状态：已完成
- 范围：完成 `runtime-v2` 新实现工作区的建立、目录骨架初始化，以及最小说明文档落地
- 结果：
  - 已创建 `runtime-v2/src/rtv2/` 作为新实现包根
  - 已建立以下目录骨架：
    - `host`
    - `state`
    - `task_graph`
    - `orchestrator`
    - `tools`
    - `prompting`
    - `finalize`
    - `memory`
    - `subagent`
  - 已建立 `runtime-v2/tests/` 独立测试目录
  - 已补顶层说明文档：
    - `runtime-v2/README.md`
    - `runtime-v2/implementation/README.md`
- 验证结果：
  - 目录骨架与包路径已可用
  - 后续状态层与宿主标识层代码已在该工作区内继续落地
- 遗留问题：
  - 各模块当时仅建立占位结构，尚未进入正式实现
  - 需要按小模块方式继续推进，而不是预排完整开发顺序
- 下一步：
  - 进入状态层与标识层的最小正式结构落地
