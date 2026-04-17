# InDepth Todo 编排参考

更新时间：2026-04-17

## 1. 目标

Todo 编排层负责把复杂任务拆成可执行、可验证、可审计的最小动作单元，并为主 Agent / SubAgent 协作、失败恢复、以及最终交付提供统一状态面。

在当前实现里，Todo 的整体运行逻辑可以概括为：
1. 当前 task 先绑定一个 `todo_id`
2. 执行过程围绕某个 active subtask 展开
3. 若执行失败，先把失败事实写入 `Fallback Record`
4. 再单独推导 subtask 当前应进入的状态
5. 然后由 `plan_task_recovery` 判断能否原地恢复
6. 在 rule decision 之后，可选再触发一次独立的 LLM recovery planner 调用
7. 只有原地恢复不合适时，才派生 recovery subtask
8. 恢复完成后，可通过 `reopen_subtask` 显式回到原 subtask 主线
9. task 完成后，当前 todo 绑定被关闭

这条链路里的关键节点包括：
- `active_todo_id` 绑定：决定本次 task 围绕哪个 todo 运行
- `active_subtask` 绑定：决定当前失败归属到哪个 subtask
- `record_task_fallback`：记录失败事实，而不是直接重写整个 subtask
- `update_task_status`：单独维护 subtask 生命周期状态
- `plan_task_recovery`：决定原地恢复还是派生恢复
- 独立 `LLM recovery planner`：在规则边界内补充语义化恢复策略
- `reopen_subtask`：显式把恢复重新挂回原主线

这意味着当前 todo 系统已经不只是“列清单”，而是形成了一套围绕 subtask 主线推进、失败恢复和任务边界管理的运行机制。

这份文档重点回答五个问题：
- 什么情况下必须创建 todo？
- subtask 应该如何设计，粒度多大才合适？
- 当前 todo 工具真实支持哪些状态和数据结构？
- 任务未完成时，fallback 与 recovery 现在是如何实现的？
- Runtime 如何自动接入这条恢复链路？

相关代码：
- `InDepth.md`
- `app/tool/todo_tool/todo_tool.py`
- `app/core/runtime/agent_runtime.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/core/runtime/tool_execution.py`
- `app/eval/verification_handoff_service.py`
- `doc/refer/tools-reference.md`

## 2. 设计定位

Todo 不是简单的待办清单，而是运行时编排层的事实源。

它承担四类职责：
- 规划职责：把复杂目标拆成有依赖关系的 subtask。
- 执行职责：给主 Agent 一个明确的“当前正在做什么”。
- 恢复职责：在任务未完成时记录失败现场并生成下一步动作。
- 审计职责：把状态变化、依赖阻塞、恢复决策和进度沉淀为可回放记录。

在 InDepth 协议里，主 Agent 不能绕开 todo 直接做清单外动作；执行必须围绕 subtask 展开。

## 2.1 失败恢复主线：一个 Subtask 失败后，系统内部如何流转

如果按“一个 subtask 执行失败后，系统内部到底怎么流转”来理解，当前实现的主线是：

1. 先有一个当前 task 绑定的 todo
2. 执行围绕某个 active subtask 展开
3. 失败发生后，先记录失败事实
4. 再单独决定 subtask 该进入什么状态
5. 然后规划恢复
6. 优先原地恢复
7. 只有必要时才派生 recovery subtask

也就是说，失败处理不再是“报错了就新建几个 follow-up”，而是先尽量保住原 subtask 主线。

### 2.1.1 关键节点 1：Task 绑定 Todo

运行开始后，当前 task 会绑定一个 `active_todo_id`。

这里维护的是 task 级上下文，当前实现里主要包括：
- `todo_id`
- `active_subtask_id`
- `active_subtask_number`
- `execution_phase`
- `binding_required`
- `binding_state`
- `todo_bound_at`

这个节点的作用是：
- 确保本次 task 只围绕一个 todo 主线推进
- 确保失败发生时，系统知道该挂回哪个 todo
- 防止在同一 task 周期里重复 `create_task`

如果这一步没绑定好，后面就容易掉进 `orphan failure`。

### 2.1.2 关键节点 2：激活当前 Subtask

todo 里真正被执行的是某个 active subtask。

通常来源于几种动作：
- `update_task_status(..., status="in-progress")`
- `get_next_task`
- `reopen_subtask`
- 某些 `update_subtask` 后的上下文同步

这个节点的作用是：
- 告诉 Runtime：当前真正推进的是哪个 subtask
- 让失败能够归属到具体 subtask
- 让恢复动作能够围绕原主线继续展开

如果没有 active subtask，Runtime 仍然知道当前有 todo，但不知道失败到底属于哪一个 subtask，于是只能进入 `orphan failure` 这种兜底路径。

### 2.1.3 关键节点 3：执行过程中收到失败信号

失败信号可能来自：
- 工具失败
- 模型失败
- 超出步数预算
- 等待用户输入
- 缺上下文或缺依赖
- 已有部分产出但尚未完成

这一层拿到的是“原始失败事实”，还不是最终恢复决策。

它回答的是：
- 刚刚发生了什么异常
- 这个异常更接近执行问题、输入问题、预算问题，还是验证问题

### 2.1.4 关键节点 4：写入 Fallback Record

失败发生后，系统首先会调用 `record_task_fallback(...)`。

这一层写入的是结构化失败事实，核心字段包括：
- `failure_state`
- `reason_code`
- `reason_detail`
- `retryable`
- `required_input`
- `suggested_next_action`
- `retry_count`
- `retry_budget_remaining`

这一步当前实现的核心语义是：
- 记录“最近一次失败或未完成尝试发生了什么”
- 不直接替代 subtask 本身
- 不再直接等于 subtask 生命周期状态

换句话说，`Fallback Record` 更像一次执行事实，而不是 subtask 本体。

### 2.1.5 关键节点 5：单独推导 Subtask 状态

写完 `Fallback Record` 后，系统不会再像旧语义那样直接用 fallback 覆盖 subtask 状态。

当前实现会单独根据 `failure_state / reason_code` 推导 subtask 应进入什么状态，并调用 `update_task_status(...)`。

典型映射是：
- 等待用户输入 -> `awaiting_input`
- 依赖未满足 -> `blocked`
- 有部分产出 -> `partial`
- 预算耗尽 -> `timed_out`
- 一般执行失败 -> `failed`

这一层的作用是：
- 把“失败事实”与“生命周期状态”拆开
- 让 subtask 状态机仍然保持清晰
- 避免 `fallback_record` 直接承担所有语义

### 2.1.6 关键节点 6：Rule Recovery Planner 决策

接下来系统会调用 `plan_task_recovery(...)`。

这一层先产出一版规则侧的 `recovery_decision`，其中最关键的是两个控制位：
- `can_resume_in_place`
- `needs_derived_recovery_subtask`

它们分别回答：

1. 原 subtask 能不能继续围绕自己恢复
2. 恢复动作是否已经独立到需要新建 recovery subtask

除此之外，rule planner 还会给出：
- `primary_action`
- `recommended_actions`
- `decision_level`
- `rationale`
- `resume_condition`
- 必要时的 `next_subtasks`

这是当前恢复链路最关键的第一层分叉点。

### 2.1.7 关键节点 7：原地恢复 or 派生恢复

如果：
- `can_resume_in_place = true`
- `needs_derived_recovery_subtask = false`

那么系统会认为：
- 原 subtask 仍然是主对象
- 下一步应继续围绕它推进
- 不需要默认 append 新 subtask

典型动作包括：
- `retry`
- `retry_with_fix`
- `repair`
- `wait_user`
- `resolve_dependency`

这就是“默认原地恢复”。

如果：
- `needs_derived_recovery_subtask = true`

那说明恢复动作已经独立成一个新的工作单元了，例如：
- 需要 diagnose
- 需要先补前置依赖
- 需要切换执行 owner
- 需要拆成更小 recovery step

这时才会调用 `append_followup_subtasks(...)`。

### 2.1.8 关键节点 8：派生 Recovery Subtask 时如何保住主线

当前派生出的 recovery subtask 会尽量带上：
- `origin_subtask_id`
- `origin_subtask_number`

这样做的目的不是增加字段，而是保证之后还能看得出：
- 哪个 subtask 是原主线
- 哪些 subtask 是为了恢复它而派生出来的

这一步非常重要，因为如果 recovery subtask 和原 subtask 之间没有显式关联，todo 很容易退化成一串无主线的补救任务。

### 2.1.9 关键节点 9：显式重开原 Subtask

当恢复准备就绪后，系统可以通过 `reopen_subtask(...)` 把原 subtask 明确拉回 `in-progress`。

这一步的作用是：
- 告诉系统：不是新任务开始了
- 而是原 subtask 恢复执行
- 让恢复结果重新挂回原主线

它让 recovery 闭环更完整，也让“失败 -> 恢复 -> 继续执行”这条链真正形成可追踪状态流。

### 2.1.10 关键节点 10：Orphan Failure

还有一个特殊节点是 `orphan failure`。

发生条件是：
- todo 已经存在
- 但失败发生时没有 active subtask

这时系统不能正常把失败挂回某个 subtask，只能：
- 记录 `orphan_subtask_unbound`
- 输出最小恢复摘要
- 提示应先绑定或选择正确的 subtask

这个节点的作用是：
- 不再静默丢失失败
- 同时显式暴露“编排没绑好”的问题

### 2.1.11 关键节点 11：Task 完成后关闭绑定

当 run 完成后，Runtime 会把当前 todo context 标成关闭状态：
- `binding_state = closed`
- 清掉 `active_subtask_id`
- 清掉 `active_subtask_number`
- `binding_required = false`

这一层的作用是：
- 防止下一个 task 误继承上一个 todo
- 真正实现“一个 todo 对应一个 task 周期”

### 2.1.12 把整条链串起来

如果把当前实现压成一条最短主线，就是：

```text
task 绑定 active_todo_id
-> 激活 active subtask
-> 收到失败信号
-> record_task_fallback 记录失败事实
-> update_task_status 单独更新 subtask 状态
-> plan_task_recovery 判断是否可原地恢复
-> 能原地恢复：继续围绕原 subtask 推进
-> 不能原地恢复：append recovery subtasks，并挂回 origin subtask
-> 条件成熟时 reopen_subtask
-> run 完成后关闭 todo 绑定
```

当前实现里，这 11 个节点一起构成了失败恢复主线。理解了这条主线，再看后面的状态机、fallback 字段和 recovery 输出，就不会只停留在“字段很多”的层面，而能看出系统到底在怎样保护 subtask 主线。

## 2.2 独立 LLM Recovery Planner 详解

前面的 2.1 讲的是失败恢复主线。这里单独讲当前设计里新增的 `LLM recovery planner`，避免把它混在总流程节点里看不清。

这部分最重要的结论只有一句：
- 它是一 个独立的、额外发生的 planner 调用
- 它不属于主链路当前 step 的执行推理
- 它也不直接替代 `plan_task_recovery`

### 2.2.1 它在链路中的位置

当前顺序是：
1. Runtime 识别 run 未完成或失败退出
2. `record_task_fallback(...)` 写入失败事实
3. `update_task_status(...)` 推导并写入 subtask 生命周期状态
4. `plan_task_recovery(...)` 先生成 rule decision
5. 若开启 `enable_llm_recovery_planner`，再额外调用一次独立的 `LLM recovery planner`
6. 系统把 LLM 输出按规则边界做归一化与裁剪
7. 再决定是否 `append_followup_subtasks(...)`

也就是说，LLM planner 并不负责“发现失败”，它消费的是已经整理好的失败上下文。

### 2.2.2 为什么要单独拆成一次调用

如果把 recovery 判断直接塞进主链路当前 step，会有三个问题：
- 当前 step 的目标是继续执行任务，容易把“恢复规划”和“继续干活”混在一起
- 主 step 未必能稳定拿到完整的 fallback facts、rule decision 和边界约束
- 很难单独开关、观测、测试和回退

因此当前设计坚持：
- 主链路 step 负责执行
- 独立 planner 调用负责恢复规划
- 规则层负责最后裁剪

### 2.2.3 它接收什么信息

当前实现里，独立 LLM planner 接收的核心输入可以分成四组：

第一组，当前恢复上下文：
- `todo_id`
- `subtask_id`
- `subtask_number`
- `runtime_state`
- `stop_reason`
- `final_answer_preview`

第二组，失败事实：
- `fallback_record`
- `last_tool_failures`

第三组，运行时绑定信息：
- `binding_state`
- `execution_phase`

第四组，规则侧先给出的基线：
- rule planner 产出的 `fallback_decision`
- 规则整理出的 `guardrails`

这意味着它不是直接读原始日志乱做判断，而是读一份已经结构化过的 recovery context。

### 2.2.4 规则层先交给它什么边界

在 LLM planner 执行前，系统会先从 rule decision 里整理出一份 guardrails。当前重点包括：
- `allowed_primary_actions`
- `fallback_primary_action`
- `must_stop_auto_recovery`
- `can_only_escalate_decision_level`
- `must_preserve_main_subtask`
- `must_derive_recovery_subtask`
- `must_anchor_followups_to_origin`
- `retry_budget_remaining`
- `retryable`

这些 guardrails 的作用是：
- 限制它只能在允许动作集合里选动作
- 不允许它降低既有安全级别
- 不允许它派生没有来源锚点的 recovery subtasks
- 不允许它绕过 retry budget 和 stop_auto_recovery 之类的硬边界

### 2.2.5 它主要负责判断什么

当前设计里，LLM planner 不是来“改字段文案”的，而是重点补充语义策略判断。它最重要的职责有四个：

1. 判断这次失败是否仍然适合原地恢复
这里主要影响 `can_resume_in_place`。

2. 判断恢复动作是否已经独立成新的工作单元
这里主要影响 `needs_derived_recovery_subtask`。

3. 在允许动作集合中选择更合适的动作
这里主要影响 `primary_action` 和 `recommended_actions`。

4. 如果需要派生，给出更像样的 recovery subtask 草案
这里主要影响 `next_subtasks` 的质量。

换句话说，规则层负责“不能乱来”，LLM 负责“在允许范围里更聪明地选”。

### 2.2.6 它输出什么

当前实现里，LLM planner 的目标输出包括：
- `can_resume_in_place`
- `needs_derived_recovery_subtask`
- `primary_action`
- `recommended_actions`
- `decision_level`
- `rationale`
- `resume_condition`
- `stop_auto_recovery`
- `suggested_owner`
- `next_subtasks`

但这里要注意：
- 这不是最终直接落地结果
- 这是“候选恢复策略”

它必须再经过规则归一化之后，才会变成最终 `recovery_decision`。

### 2.2.7 规则最终如何裁剪 LLM 输出

当前实现里，LLM 输出回来后不会直接信任，而是会经过一次 normalize。

重点裁剪规则包括：
- `primary_action` 必须在 `allowed_primary_actions` 里
- `decision_level` 只能维持或升级，不能降级
- `stop_auto_recovery` 只会被维持或收紧，不会被放宽
- 如果规则已经要求必须派生 recovery subtask，LLM 不能取消
- 如果最终需要派生，`next_subtasks` 会被补齐 `origin_subtask_id / origin_subtask_number`

这一步非常关键，因为它决定了：
- LLM 能参与策略
- 但不能突破系统状态机和安全边界

### 2.2.8 什么时候会真的 append recovery subtasks

不是 LLM 说“需要派生”就一定 append。

当前 runtime 仍然保留原来的自动执行门槛。通常要同时满足：
- `needs_derived_recovery_subtask = true`
- `decision_level = auto`
- `stop_auto_recovery = false`
- `next_subtasks` 非空
- `append_followup_subtasks` 工具可用

只有这些条件都成立，系统才会真的自动追加 follow-up subtasks。

所以这里分成两层：
- planner 决定“建议怎么恢复”
- runtime 决定“是否现在自动执行这个恢复”

### 2.2.9 失败或异常时如何回退

当前实现里，独立 LLM planner 是可选增强，不是硬依赖。

如果出现下面任一情况：
- `enable_llm_recovery_planner = false`
- model provider 不可用
- LLM 调用异常
- LLM 输出不是合法 JSON
- 输出不满足规则约束

系统都会回退到 rule planner 的结果。

这也是为什么当前实现会在最终 `recovery_decision` 里保留：
- `planner_source = "llm"` 或
- `planner_source = "rule"`

这样后面做观测、调试和评估时，可以直接看出本次恢复决策最终是谁主导的。

### 2.2.10 现在项目里它的定位

如果用一句话总结当前项目里的定位：

`plan_task_recovery` 是恢复决策的稳定基线，独立 `LLM recovery planner` 是建立在这个基线之上的语义增强层。

所以当前不是“规则还是 LLM 二选一”，而是：
- 规则先给安全底盘
- LLM 在底盘内做更细的恢复策略判断
- runtime 再决定是否自动落地

## 3. 何时必须创建 Todo

满足以下任一条件即必须创建 todo：
- 至少 3 个可识别步骤。
- 涉及跨文件或跨组件修改。
- 预计执行超过 5 分钟。
- 存在依赖关系或并行机会。

调用 `create_task` 时必须提供：
- `task_name`：主任务标题，必须体现“动作 + 对象”。
- `context`：范围、边界、交付物、验收口径、时间基准。
- `split_reason`：为什么需要拆分。
- `subtasks`：结构化子任务数组。

返回值中的 `todo_id` 是 todo 域唯一标识，后续状态更新、失败记录、恢复规划和报告生成都必须复用它。

## 4. 当前 Todo 数据模型

### 4.1 顶层结构

`create_task` 会生成 `todo/<timestamp>_<sanitized_name>.md` 文件，主体结构包含：
- `Metadata`
- `Context`
- `Subtasks`
- `Dependencies`
- `Notes`

顶层元数据包括：
- `Todo ID`
- `Status`
- `Priority`
- `Created`
- `Updated`
- `Progress`

### 4.2 Subtask 结构

当前实现中，每个 subtask 会落为：
- `Task <n>: <name>`
- `Status`
- `Priority`
- `Dependencies`
- `Kind`（可选）
- `Owner`（可选）
- `Split Rationale`
- `Acceptance Criteria`（可选）
- `Fallback Record`（可选）
- 复选描述项

`create_task` / `append_followup_subtasks` 支持的核心字段包括：
- `subtask_id`
- `name` / `title`
- `description`
- `priority`
- `dependencies`
- `split_rationale`
- `kind`
- `owner`
- `origin_subtask_id`
- `origin_subtask_number`
- `acceptance_criteria`
- `fallback_record`

### 4.3 依赖派生信息

`todo_tool` 会根据依赖关系额外生成一段依赖摘要：
- `Blocked subtasks`
- `Ready subtasks`
- `Blocking subtasks`

这段内容不是独立输入，而是由 subtask 的状态和依赖列表推导出来的。

## 5. Subtask 设计准则

### 5.1 粒度要求

一个好的 subtask 应满足：
- 单一动作：只做一件可描述、可验收的事。
- 单一责任：不要把“实现 + 测试 + 汇总”混成一步。
- 可验证：完成后能用产物、命令结果或结构化结论证明。
- 可流转：能够自然进入状态流转，而不是长期停留在模糊的“处理中”。

推荐粒度是 5 到 30 分钟可完成。

### 5.2 推荐写法

推荐使用“动词 + 对象 + 产出”：
- 读取错误日志并定位构建失败根因
- 基于诊断结果修复验证失败的实现
- 重新分派 researcher 并产出缩小范围后的证据摘要

### 5.3 完成判据

每个 subtask 至少应绑定一种完成判据：
- 产物路径
- 命令结果
- 结构化结论

如果完成后无法明确回答“什么算做完”，这个 subtask 往往拆得还不够好。

## 6. 当前代码实现状态机

### 6.1 Subtask 状态

当前 `todo_tool` 已真实支持以下状态：
- `pending`
- `in-progress`
- `completed`
- `blocked`
- `failed`
- `partial`
- `awaiting_input`
- `timed_out`
- `abandoned`

与旧版本不同，当前实现已经不再是三态。

### 6.2 状态含义

1. `pending`
   尚未开始，且没有被显式标记为未完成态。

2. `in-progress`
   当前正在执行。

3. `completed`
   满足完成判据。

4. `blocked`
   当前不能继续执行，通常是依赖未满足或外部条件不满足。

5. `failed`
   已执行，但结果失败、工具失败或输出不符合要求。

6. `partial`
   已有部分有效产出，但尚未完整闭环。

7. `awaiting_input`
   等待用户或外部系统补充输入。

8. `timed_out`
   达到预算上限、重试上限或步数上限。

9. `abandoned`
   明确止损，不再继续投入。

### 6.3 依赖推进规则

当前工具仍然会对 `in-progress`、`completed`、`partial` 做依赖检查：
- 若依赖未满足，不允许直接推进。

`get_next_task()` 只会返回依赖满足的 `pending` 任务作为下一个 ready subtask。

## 7. Fallback 记录

### 7.1 作用

任务未完成时，当前实现不会只停留在自然语言说明，而是支持将失败事实结构化写入 `Fallback Record`。

对应工具：
- `record_task_fallback(todo_id, subtask_number, ...)`

这里要特别注意一个当前实现语义：
- `Fallback Record` 记录的是“最近一次失败或未完成尝试发生了什么”
- 它不再等同于 subtask 本身，也不直接替代 subtask 生命周期状态

换句话说，subtask 仍然是“长期工作单元”，而 `Fallback Record` 是挂在这个工作单元上的一次执行事实。

这样设计的原因是：
- 同一个 subtask 可能经历多次尝试
- 一次失败不应该天然意味着“原 subtask 作废”
- 后续恢复动作需要围绕原 subtask 展开，而不是每次失败都重新发明一个新任务

### 7.2 最小字段

当前实现支持的核心字段包括：
- `state`
- `failure_state`
- `reason_code`
- `reason_detail`
- `impact_scope`
- `retryable`
- `required_input`
- `suggested_next_action`
- `evidence`
- `owner`
- `retry_count`
- `retry_budget_remaining`

### 7.3 典型 `reason_code`

当前设计与实现对齐的原因码包括：
- `dependency_unmet`
- `tool_invocation_error`
- `execution_environment_error`
- `validation_failed`
- `missing_context`
- `waiting_user_input`
- `budget_exhausted`
- `partial_progress`
- `orphan_subtask_unbound`
- `subagent_empty_result`
- `subagent_execution_error`

### 7.4 当前失败重试模型

当前实现采用的是“默认原地恢复，必要时才派生”的重试模型。

它背后的判断是：
- subtask 是主线
- 失败只是主线推进中的一次受挫
- 恢复动作应优先服务于“让原 subtask 继续完成”

因此，失败后默认不会立刻新增一串 follow-up subtasks，而是先做三件事：
1. 把失败事实结构化写入 `Fallback Record`
2. 单独判断当前 subtask 应进入什么状态
3. 由 `plan_task_recovery` 判断能否原地恢复

这套模型有两个直接好处：
- todo 主线更稳定，不会因为每次失败都膨胀
- 用户和 agent 更容易回答“原 subtask 现在到底处于什么情况”

### 7.5 当前实现如何理解“重试”

在当前实现里，“重试”不是一个单一动作，而是一个总称，通常分成下面几种情况：

1. 直接重试
   适用于明显的瞬时失败，且恢复动作仍然围绕原 subtask。

2. 修复后重试
   适用于工具调用问题、环境问题、轻量逻辑问题。对应动作常见为 `retry_with_fix` 或 `repair`。

3. 等待输入后继续
   当失败本质上是缺信息，而不是执行能力不足时，重试不应该立即发生，而应先进入 `awaiting_input`。

4. 缩小范围后继续
   当预算耗尽或任务粒度过大时，“继续做原 subtask”仍然成立，但恢复动作需要先缩小执行范围。

因此，当前的“重试”更准确地说是：
- 不是机械地再跑一遍
- 而是围绕原 subtask 选择最小、最安全的下一步

### 7.6 什么情况下不应直接重试

虽然当前模型默认原地恢复，但并不是所有失败都适合直接重试。

以下情况一般不应直接进入“再试一次”：
- 依赖未满足：应先解决依赖，通常对应 `dependency_unmet`
- 明显缺上下文：应先补材料或补约束，通常对应 `missing_context`
- 等待用户输入：应先暂停，通常对应 `waiting_user_input`
- 已耗尽自动重试预算：应避免继续盲目重试
- 恢复动作已经独立成一段新工作：例如 diagnose / verify / handoff 已经形成独立链路

当前实现里，这些情况通常会把恢复决策导向：
- `wait_user`
- `resolve_dependency`
- `split`
- `execution_handoff`
- `decision_handoff`

### 7.7 失败判断里哪些交给规则，哪些交给 LLM

当前实现对失败处理采用的是“规则主导，LLM 辅助”的分工。

这样划分的原因是：
- 失败分类会直接影响 subtask 状态、恢复分叉和 todo 主线稳定性
- 这些控制位必须可测试、可复现、可预测
- LLM 更适合补充解释，而不适合成为唯一裁判

#### 7.7.1 规则负责的部分

失败处理里的核心控制位由规则决定，主要包括：

1. 是否进入失败/未完成处理
   例如：
   - 工具调用失败
   - 达到步数上限
   - 等待用户输入
   - run 进入 failed
   - todo 已存在但没有 active subtask

2. `failure_state`
   当前实现中的结果形态包括：
   - `failed`
   - `blocked`
   - `partial`
   - `awaiting_input`
   - `timed_out`

3. `reason_code`
   当前实现中的主要失败原因包括：
   - `dependency_unmet`
   - `tool_invocation_error`
   - `execution_environment_error`
   - `validation_failed`
   - `missing_context`
   - `waiting_user_input`
   - `budget_exhausted`
   - `partial_progress`
   - `orphan_subtask_unbound`

4. 失败后 subtask 应进入什么状态
   当前实现会先写入 `Fallback Record`，再由 Runtime 基于 `failure_state/reason_code` 单独推导 subtask 的 `status`。

5. 是否原地恢复
   也就是：
   - `can_resume_in_place`
   - `needs_derived_recovery_subtask`

6. 是否允许自动派生 recovery subtask
   只有在恢复决策明确需要派生，且自动推进条件满足时，Runtime 才会调用 `append_followup_subtasks`。

#### 7.7.2 LLM 辅助的部分

LLM 在失败处理里更适合承担“解释”和“表达”工作，而不是核心控制逻辑。

当前更适合交给 LLM 辅助的部分包括：

1. `reason_detail` 的自然语言补充
   把失败事实解释得更可读，例如：
   - 哪个命令失败了
   - 缺少了什么信息
   - 哪个验证点没过

2. 恢复建议的描述性文案
   例如为什么建议 `retry_with_fix`，为什么建议 `split`。

3. 用户可见的恢复摘要
   当前最终回答中的“恢复摘要”属于面向用户的解释层，适合由 LLM 或模板化逻辑辅助生成。

4. 模糊场景下的辅助判断
   当失败证据不够完整时，LLM 可以帮助生成候选解释或补充说明；但最终落库的 `reason_code`、`failure_state` 和恢复分叉，仍应由规则收敛。

#### 7.7.3 一句话总结

在当前实现里：
- 规则负责定性：失败属于什么、状态怎么变、能否原地恢复
- LLM 负责定描述：为什么失败、如何把恢复建议讲清楚

这种分工能够让失败恢复既保持编排稳定性，又保留足够好的可读性。

## 8. Recovery 决策

## 8. Recovery 决策

### 8.1 恢复决策器

当前已落地一个规则版恢复决策器：
- `plan_task_recovery(todo_id, subtask_number, ...)`

它会基于当前 subtask 的 `fallback_record` 生成 `recovery_decision`。

### 8.2 输出结构

当前恢复决策输出包含：
- `subtask_id`
- `can_resume_in_place`
- `needs_derived_recovery_subtask`
- `primary_action`
- `recommended_actions`
- `decision_level`
- `rationale`
- `preserve_artifacts`
- `next_subtasks`
- `resume_condition`
- `escalation_reason`
- `stop_auto_recovery`
- `suggested_owner`

### 8.3 当前动作集

规则版恢复决策器当前使用的动作包括：
- `retry`
- `retry_with_fix`
- `repair`
- `split`
- `fallback_path`
- `execution_handoff`
- `decision_handoff`
- `wait_user`
- `resolve_dependency`
- `pause`
- `degrade`
- `abandon`

### 8.4 当前分级

恢复动作会被标记为：
- `auto`
- `agent_decide`
- `user_confirm`

当前 runtime 只会自动推进：
- `decision_level=auto`
- 且 `stop_auto_recovery=false`
的恢复决策。

### 8.5 原地恢复优先的实际含义

当前实现里的“原地恢复优先”，不是一句抽象原则，而是具体落在两个控制位上：
- `can_resume_in_place`
- `needs_derived_recovery_subtask`

它们分别回答两个问题：

1. `can_resume_in_place`
   下一步是否仍应围绕原 subtask 推进。

2. `needs_derived_recovery_subtask`
   恢复动作是否已经独立到需要派生新 subtask。

这两个字段同时存在的意义是：
- 不再把“恢复”简单理解成“再建几个 follow-up subtasks”
- 先判断原 subtask 能不能继续
- 只有继续不合适时，才允许恢复链路外溢成新的 recovery subtask

### 8.6 当前 planner 是如何看待失败重试的

当前规则版 `plan_task_recovery` 不会把所有失败都压成统一的“retry”。

它更关心的是：
- 失败原因是什么
- 是否还值得继续围绕原 subtask 投入
- 下一步是轻量修复，还是已经需要升级成新的恢复工作单元

一个典型的判断顺序是：
1. 先看失败类型，例如工具调用失败、环境失败、缺依赖、缺用户输入、预算耗尽
2. 再看是否还有自动恢复预算
3. 再看是否允许保持在原 subtask 内修复
4. 最后才决定是否派生 recovery subtask

因此，当前 planner 的目标不是“尽量多做动作”，而是“尽量用最小动作恢复主线”。

### 8.7 派生 Recovery Subtask 的现实意义

当前实现仍然支持 `append_followup_subtasks`，但它的角色已经和早期不同。

现在它更像一种“恢复升级机制”，而不是默认恢复流程。

只有当满足下面这类情况时，才更适合派生 recovery subtask：
- 恢复动作本身就是独立工作，例如根因分析或责任切换
- 原 subtask 如果继续承载恢复细节，会让语义变形
- 恢复链路已经天然分成 diagnose / repair / verify 多步
- 自动重试预算已经耗尽，需要显式拆小或切换执行路径

为了避免主线丢失，当前派生出的 recovery subtasks 会尽量带上：
- `origin_subtask_id`
- `origin_subtask_number`

这样做的目的是让读者始终看得出：
- 哪个 subtask 是原主线
- 哪些 subtask 是为恢复它而派生出来的

## 9. Follow-up Subtasks

### 9.1 作用

当前实现支持把恢复动作进一步落成新的 subtask，而不是只停留在建议层；但与早期版本不同，派生 follow-up 已不再是默认恢复路径。

对应工具：
- `append_followup_subtasks(todo_id, follow_up_subtasks)`

### 9.2 当前支持的 kind

follow-up subtask 的 `kind` 当前支持：
- `diagnose`
- `repair`
- `retry`
- `verify`
- `handoff`
- `resume`
- `report`

### 9.3 推荐模板

当前规则版恢复链路最常见的 follow-up 模式是：

1. `diagnose`
   先定位根因。

2. `repair` / `retry`
   再执行修复或重试。

3. `verify`
   最后做聚焦验证。

## 10. Runtime 自动接入

这是当前实现与早期设计最大的变化之一。

### 10.1 当前 runtime 做了什么

`AgentRuntime` 现在会跟踪活跃的 todo 上下文：
- `todo_id`
- `active_subtask_id`
- `active_subtask_number`
- `execution_phase`
- `binding_required`
- `binding_state`
- `todo_bound_at`

上下文来源于工具执行结果，例如：
- `create_task`
- `update_task_status`
- `update_subtask`
- `record_task_fallback`
- `reopen_subtask`
- `get_next_task`

当前语义：
- `create_task` 成功后，runtime 会记录 `todo_id`，并进入 `planning` 阶段
- `create_task` 默认会绑定当前 task 周期；若当前已有 `active_todo_id` 且未显式 `force_new_cycle`，runtime 会拒绝再次创建 todo
- `update_task_status(..., status="in-progress")` 后，runtime 会把该 subtask 视为当前 active subtask，并进入 `executing`
- `update_subtask(...)` 后，runtime 会同步当前 active subtask 的 `subtask_id/subtask_number`
- `record_task_fallback(...)` 后，runtime 会把该 subtask 视为恢复中的 subtask，并进入 `recovering`
- `reopen_subtask(...)` 后，runtime 会把该 subtask 重新置回 `executing`
- `get_next_task` 返回 ready subtask 后，runtime 会记录候选 active subtask，但此时仍属于“待激活”状态，阶段仍偏向 `planning`
- run 完成后，runtime 会将当前 todo 绑定切到 `closed`

这意味着 runtime 已经不只是“记住最近的 todo_id”，而是开始区分：
- 当前是否已经进入 todo 执行流
- 当前是否已经绑定具体 subtask
- 当前是在规划、执行，还是恢复阶段

### 10.2 自动触发点

当 runtime 进入以下未完成出口时，会自动触发恢复链路：
- `failed`
- `awaiting_user_input`
- `max_steps_reached`
- `tool_failed_before_stop`
- 其他运行失败分支

### 10.3 自动恢复顺序

当前自动顺序为：

1. `record_task_fallback`
2. 基于 `failure_state/reason_code` 推导 subtask 状态，并单独调用 `update_task_status`
3. `plan_task_recovery`
4. 仅当 `needs_derived_recovery_subtask=true` 且恢复决策允许自动推进时，才 `append_followup_subtasks`

这意味着：
- 失败记录不再只靠 agent 自觉
- `fallback_record` 与 subtask `status` 已经解耦
- 恢复优先围绕原 subtask 展开，只有必要时才派生 recovery subtasks

### 10.4 当前新增的绑定告警与 orphan failure

当前 runtime 还没有把“每个 step 都必须绑定 subtask”升级为强拦截，但已经新增了一层 `warn` 级 guard：

- 当 todo 已创建
- 且 runtime 认为当前动作应属于某个 subtask
- 但模型仍直接调用普通业务工具

runtime 会记录 `todo_binding_missing_warning` 观测事件。

当前被视为“补救性/编排性”的工具包括：
- `create_task`
- `list_tasks`
- `get_next_task`
- `get_task_progress`
- `generate_task_report`
- `update_task_status`
- `update_subtask`
- `record_task_fallback`
- `reopen_subtask`
- `plan_task_recovery`
- `append_followup_subtasks`

除这些工具外，其他工具默认会被视为“需要 active subtask 绑定的普通执行工具”。

#### 10.4.1 orphan failure

当前 runtime 还新增了一个重要异常分支：`orphan failure`

含义：
- 已经创建了 todo
- 但失败发生时还没有 active subtask
- 导致失败无法归属到具体 subtask

当前处理方式：
- runtime 不再静默跳过恢复链路
- 会生成一份最小恢复摘要
- `reason_code = orphan_subtask_unbound`
- `primary_action = decision_handoff`
- `decision_level = agent_decide`

这种情况下：
- 当前 todo 文件里的 subtask 不会被自动改写成 `failed`
- 但最终交付与恢复摘要会明确说明：当前失败来自“todo 已存在，但执行未绑定到具体 subtask”

## 11. 恢复信息如何外溢

当前恢复信息会进一步进入以下位置：

1. `verification_handoff.recovery`
   包含：
   - `todo_id`
   - `subtask_id`（若存在 active subtask）
   - `subtask_number`（若存在 active subtask）
   - `fallback_record`
   - `recovery_decision`

2. `task_judged.payload.verification_handoff`

3. postmortem 的“交付内容”区块

4. 最终用户回复中的简短“恢复摘要”

这意味着恢复信息已经不是 todo 内部私有信息，而是贯穿了：
- 编排
- 评估
- 观测
- 用户可见输出

## 12. 当前实现与设计稿关系

### 12.1 已实现部分

当前已经实现：
- richer subtask states
- `subtask_id`
- `update_subtask`
- `reopen_subtask`
- `fallback_record`
- 规则版 `recovery_decision`
- follow-up subtask 追加
- runtime 自动接入恢复链路
- recovery 信息进入 handoff / postmortem / user-facing summary

### 12.2 仍未完全收口的部分

当前仍然是“最小规则版恢复系统”，还没有：
- 更高级的策略评分器
- 严格的关键路径推断
- 恢复效果 metrics（成功率、升级率、止损率）

## 13. 一句话结论

当前 Todo 的核心已经不只是“列任务”，而是把复杂执行过程压缩成一组可验证、可恢复、可继续推进的 subtask；而 runtime 已经开始在失败出口自动补齐 fallback 与 recovery 链路，保证恢复机制不再只靠 agent 自觉遵守。
