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
- 开发状态：已完成模块 01、模块 02
- 当前重点：下一步进入新的小模块讨论，再决定后续实现范围

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

---

## 开发记录

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
