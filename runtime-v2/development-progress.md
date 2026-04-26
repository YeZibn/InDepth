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
- 开发状态：已完成模块 01、模块 02、模块 03；模块 04 正在推进
- 当前重点：推进模块 04，并按子任务逐个对齐后再落地

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
- 任务 04：未开始

---

## 开发记录

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
