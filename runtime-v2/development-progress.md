# runtime-v2 开发进度记录

## 文档目标

本文档用于记录 `runtime-v2` 从设计进入开发后的实际落地进度。

记录原则：

- 只记录已经完成或正在推进的开发工作
- 设计稿已完成不等于开发已完成，两者必须明确区分
- 开发推进按可独立验收的步骤组织
- 每个步骤下再拆若干可执行的小任务
- 每次更新尽量包含时间、范围、结果、验证、遗留问题和下一步

---

## 当前总体状态

- 项目阶段：设计阶段已闭环，进入实现前准备
- 设计文档状态：`S1 ~ S12` 的第一版子任务设计稿已全部落文档
- 开发状态：尚未开始正式实现
- 当前重点：按主干优先顺序进入开发落地，并持续记录实际进度

---

## 开发步骤总览

| Step | 说明 | 设计状态 | 开发状态 | 备注 |
| --- | --- | --- | --- | --- |
| Step 01 | 实现前对齐与目录骨架 | 已完成 | 未开始 | 先把落地目标和代码骨架入口固定 |
| Step 02 | 状态层与标识层落地 | 已完成 | 未开始 | 对应 `S2/S4` 主干基础 |
| Step 03 | Task Graph Skeleton 落地 | 已完成 | 未开始 | 对应 `S5` 的 state/store 骨架 |
| Step 04 | RuntimeHost 与 Start-Run 主链路 | 已完成 | 未开始 | 对应 `S2-T2/T3/T4/T5` |
| Step 05 | RuntimeOrchestrator Skeleton | 已完成 | 未开始 | 对应 `S3` 主编排骨架 |
| Step 06 | Tool / Prompt 主挂点接入 | 已完成 | 未开始 | 对应 `S1/S6/S7` 主挂点 |
| Step 07 | Finalize / Verification 主干 | 已完成 | 未开始 | 对应 `S11` 收尾主干 |
| Step 08 | Memory Hook 主挂点接入 | 已完成 | 未开始 | 对应 `S8` 的 run-start / finalize hooks |
| Step 09 | SubAgent Skeleton 落地 | 已完成 | 未开始 | 对应 `S10` 整组结构 |
| Step 10 | 事件、测试与实现复核 | 已完成 | 未开始 | 对应 `S12` 工程化闭环 |

---

## 开发步骤拆解

### Step 01：实现前对齐与目录骨架

目标：

- 明确第一批实现的代码落点
- 确认设计口径已经统一
- 为后续逐步替换旧实现预留新骨架位置

当前确定的代码落点：

- `runtime-v2/design/`：保留设计稿
- `runtime-v2/src/host/`：宿主入口与 host 状态
- `runtime-v2/src/state/`：正式状态模型
- `runtime-v2/src/task_graph/`：task graph 状态与 store
- `runtime-v2/src/orchestrator/`：runtime orchestrator 主骨架
- `runtime-v2/src/tools/`：tool 主挂点
- `runtime-v2/src/prompting/`：prompt assembly 主挂点
- `runtime-v2/src/finalize/`：finalize / verification 主挂点
- `runtime-v2/src/memory/`：memory hooks 主挂点
- `runtime-v2/src/subagent/`：subagent 主骨架
- `runtime-v2/tests/`：runtime-v2 独立测试

子任务：

- 任务 01：确认 `runtime-v2` 第一批实现范围
- 任务 02：确定新代码应落在哪些包或模块下
- 任务 03：补最小目录骨架与占位文件
- 任务 04：确认旧实现与新骨架的并存策略

当前状态：

- 设计已完成
- 开发未开始

### Step 02：状态层与标识层落地

目标：

- 先把正式状态结构落成代码
- 为 host、orchestrator、task graph 提供统一类型底座

子任务：

- 任务 01：实现 `RunIdentity`
- 任务 02：实现 `RunLifecycle`
- 任务 03：实现 `RuntimeState`
- 任务 04：实现 `DomainState`
- 任务 05：实现极简 `RunContext`
- 任务 06：实现 `VerificationState`
- 任务 07：实现宿主标识结构与 `session_id / task_id / run_id` 对应关系

当前状态：

- 设计已完成
- 开发未开始

### Step 03：Task Graph Skeleton 落地

目标：

- 把正式执行骨架最小落地
- 替代当前隐式 todo/runtime 混合控制语义

子任务：

- 任务 01：实现 `TaskGraphState`
- 任务 02：实现 `TaskGraphNode`
- 任务 03：实现 `TaskGraphPatch / NodePatch`
- 任务 04：实现最小 `TaskGraphStore` 接口
- 任务 05：补一个内存版 `TaskGraphStore`
- 任务 06：补 graph patch 应用规则的最小测试

当前状态：

- 设计已完成
- 开发未开始

### Step 04：RuntimeHost 与 Start-Run 主链路

目标：

- 先把宿主入口与新 run 启动链打通
- 明确第一版“等待后重开新 run”的行为

子任务：

- 任务 01：实现 `RuntimeHost` 最小接口
- 任务 02：实现 `start_task(...)`
- 任务 03：实现 `submit_user_input(...)`
- 任务 04：实现默认 task 自动补建
- 任务 05：实现新的 `run_id` 生成与传递
- 任务 06：实现“等待后重开新 run”的最小宿主逻辑
- 任务 07：补 host 状态与标识生命周期测试

当前状态：

- 设计已完成
- 开发未开始

### Step 05：RuntimeOrchestrator Skeleton

目标：

- 把 `prepare -> execute step loop -> finalize` 主骨架落成代码
- 让 runtime 主链真正具备最小可运行结构

子任务：

- 任务 01：实现 `RuntimeOrchestrator` 最小类壳
- 任务 02：实现 `build_initial_context`
- 任务 03：实现 `run_prepare_phase`
- 任务 04：实现 `run_execute_step`
- 任务 05：实现 `apply_step_result`
- 任务 06：实现 `run_finalize_phase`
- 任务 07：补 orchestrator 最小流程测试

当前状态：

- 设计已完成
- 开发未开始

### Step 06：Tool / Prompt 主挂点接入

目标：

- 把第一版主链需要的 prompt、tool、model 挂点接入骨架
- 先建立可扩展接口，不追求一步实现全部细节

子任务：

- 任务 01：实现 prompt assembly 最小入口
- 任务 02：实现 phase prompt / dynamic injection 基本挂点
- 任务 03：实现 tool registry 骨架接线
- 任务 04：实现最小 tool request / result 适配
- 任务 05：实现 model gateway 最小接线
- 任务 06：补 prompt/tool/model 主挂点测试

当前状态：

- 设计已完成
- 开发未开始

### Step 07：Finalize / Verification 主干

目标：

- 把收尾、结果判定和 closeout 主干落成
- 形成第一版 `RunOutcome` 收口路径

子任务：

- 任务 01：实现 `RunOutcome` 最小结构
- 任务 02：实现 handoff 最小结构
- 任务 03：实现 finalize pipeline 主入口
- 任务 04：实现 verification 最小骨架
- 任务 05：实现 `pass / partial / fail` 最小闭环
- 任务 06：补 finalize / verification 最小测试

当前状态：

- 设计已完成
- 开发未开始

### Step 08：Memory Hook 主挂点接入

目标：

- 把 memory 以 hook 方式接入主链
- 保持 memory 不重新污染主控制结构

子任务：

- 任务 01：实现 run-start long-term memory recall hook
- 任务 02：实现 run-start user preference recall hook
- 任务 03：实现 step-prep runtime context processor hook
- 任务 04：实现 finalize-closeout memory write hook
- 任务 05：补 memory hook 最小集成测试

当前状态：

- 设计已完成
- 开发未开始

### Step 09：SubAgent Skeleton 落地

目标：

- 按 `S10` 已定稿结构，把 subagent 正式骨架接入主 graph

子任务：

- 任务 01：实现 `role registry`
- 任务 02：实现 `subagent runtime facade`
- 任务 03：实现 `subagent lifecycle controller`
- 任务 04：实现 `result collector`
- 任务 05：实现 `graph binding adapter`
- 任务 06：补 subagent 生命周期与回流最小测试

当前状态：

- 设计已完成
- 开发未开始

### Step 10：事件、测试与实现复核

目标：

- 在主干初步落地后补事件、测试和实现复核
- 形成可持续迭代的工程底座

子任务：

- 任务 01：补 runtime 关键事件挂点
- 任务 02：补 task graph 事件挂点
- 任务 03：补 subagent 事件挂点
- 任务 04：补 host / orchestrator / graph / subagent 测试分层
- 任务 05：做一轮设计与实现一致性复核

当前状态：

- 设计已完成
- 开发未开始

---

## 当前建议开发顺序

建议按下面顺序推进第一批开发：

1. Step 01：实现前对齐与目录骨架
2. Step 02：状态层与标识层落地
3. Step 03：Task Graph Skeleton 落地
4. Step 04：RuntimeHost 与 Start-Run 主链路
5. Step 05：RuntimeOrchestrator Skeleton

原因：

- 这 5 步先把主干控制面立住
- 后续 prompt/tool/finalize/memory/subagent 都要挂在这条主干上
- 如果先做增强能力，后面主干一改会反复返工

---

## 开发记录

### 2026-04-26

#### 记录 001：初始化 runtime-v2 开发进度文档

- 状态：已完成
- 范围：建立 `runtime-v2` 的开发进度记录文档
- 结果：
  - 明确区分设计完成与开发完成
  - 建立开发步骤总览
  - 建立逐步开发与子任务拆解结构
  - 明确当前仍处于“准备进入开发”的状态
- 遗留问题：
  - 具体第一批代码落点尚未最终登记到代码目录
  - Step 01 之后的实际实现记录尚未开始
- 下一步：
  - 开始 Step 01：实现前对齐与目录骨架

### 2026-04-26

#### 记录 002：确认 runtime-v2 独立源码工作区与最小目录骨架

- 状态：已完成
- 范围：完成 Step 01 的代码落点确认与最小目录骨架初始化
- 结果：
  - 确认 `runtime-v2/` 作为独立开发工作区，不把第一批新代码直接写回 `app/core/*`
  - 确认源码统一落在 `runtime-v2/src/`
  - 建立 `host`、`state`、`task_graph`、`orchestrator`、`tools`、`prompting`、`finalize`、`memory`、`subagent` 和 `tests` 目录骨架
  - 预留最小模块入口，供 Step 02 ~ Step 05 继续落地
- 遗留问题：
  - 还未进入正式类型实现
  - 还未建立最小测试基线
  - 还未决定后续这套实现接回主工程的导入方式
- 下一步：
  - 开始 Step 02：状态层与标识层落地
