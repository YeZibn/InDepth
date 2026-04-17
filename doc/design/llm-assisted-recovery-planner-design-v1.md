# InDepth LLM 辅助 Recovery Planner 设计稿 V1

更新时间：2026-04-17  
状态：Draft

## 1. 背景

当前 InDepth 的失败恢复链路已经具备较完整的规则基础：
1. Runtime 能在失败出口自动写入 `fallback_record`
2. Runtime 能单独推导 subtask `status`
3. `plan_task_recovery` 已能输出 `can_resume_in_place / needs_derived_recovery_subtask / primary_action`
4. Runtime 已能在必要时自动派生 recovery subtasks

但当前 Recovery Planner 仍然主要依赖规则分支，存在三个现实问题：
1. 对失败上下文的语义理解仍然偏粗
2. 同类失败在不同任务上下文里很难做出更精细的策略判断
3. 生成的恢复动作文案、恢复 subtasks 和理由说明仍然偏模板化

尤其在下面几类场景里，纯规则往往不够：
1. 工具失败背后其实暴露的是 subtask 拆分不合理
2. 同样是验证失败，有时应原地修复，有时应拆出独立诊断链
3. 同样是 budget exhausted，有时应拆分，有时应降级交付，有时应停止自动恢复

因此，本稿提出在当前规则恢复链路之上，引入一个强参与的 LLM Recovery Planner。

## 2. 目标

1. 让 Recovery Planner 能理解失败上下文的任务语义，而不只依赖固定映射
2. 提升 `can_resume_in_place / needs_derived_recovery_subtask` 的判断质量
3. 提升 `primary_action / rationale / next_subtasks` 的质量与可读性
4. 保持 Runtime 的安全边界、可测试性和可预测性

## 3. 非目标

1. 本稿不让 LLM 直接替代 todo 状态机
2. 本稿不让 LLM 直接决定 task 绑定、周期切换或自动执行边界
3. 本稿不要求本轮移除全部规则分支

## 4. 核心判断

本稿的核心判断是：
1. Recovery Planner 必须引入 LLM，而且 LLM 不是只负责润色
2. 但 LLM 不应成为唯一裁判，必须工作在规则边界之内
3. 这个 LLM Recovery Planner 必须是一次额外的独立 planner 调用，而不是主链路当前 step 顺手做出的判断

换句话说：
1. 规则负责“边界与安全”
2. LLM 负责“语义与策略”

## 5. 总体设计

### 5.1 双层 Planner

建议把 Recovery Planner 拆成两层：

1. Rule Guard Layer
   负责硬约束、候选动作约束和最终裁剪。

2. LLM Strategy Layer
   负责理解失败上下文、判断恢复层级、生成恢复策略与恢复 subtasks 草案。

整体链路：

```text
失败信号
-> Runtime 产出 fallback_record
-> Rule Guard 产出硬约束与允许动作集合
-> 独立 LLM Recovery Planner 调用读取失败上下文与硬约束
-> 输出恢复策略建议
-> Rule Guard 再做结构校验与安全裁剪
-> Runtime 决定是否自动执行
```

### 5.3 为什么必须是“独立调用”

这里明确约束实现方式：
1. LLM Recovery Planner 不挂在主执行 step 的推理里
2. 它发生在失败事实已经落盘、rule decision 已经产出之后
3. 它的职责是“恢复规划”，不是“继续执行当前任务”

原因有三点：
1. 主 step 的目标是完成任务执行，容易把“恢复规划”混进执行意图里
2. 独立 planner 调用才能稳定拿到完整失败事实、rule guardrails 和 fallback decision
3. 独立调用更容易做开关控制、观测、测试和失败回退

因此运行时实际顺序应是：
1. `record_task_fallback`
2. `derive_subtask_status_from_failure`
3. `plan_task_recovery` 生成 rule decision
4. 额外一次 `LLM recovery planner` 调用生成策略建议
5. 规则层对 LLM 输出做裁剪归一化
6. Runtime 决定是否 append recovery subtasks / 停止自动恢复 / 交回主链路

### 5.2 为什么必须双层

纯规则的问题：
1. 规则能看见显式失败类型，但不擅长理解失败语义
2. 容易把不同上下文中的失败压成同一恢复动作

纯 LLM 的问题：
1. 容易越过 task / todo 边界
2. 行为不稳定，不利于测试
3. 可能无视预算、关键路径和用户确认边界

双层的意义：
1. 让 LLM 有真正策略空间
2. 同时用规则守住系统边界

## 6. 哪些交给规则，哪些交给 LLM

### 6.1 规则负责的部分

以下信息和控制位必须由规则主导：

1. `active_todo_id` 是否已绑定
2. `active_subtask_id / active_subtask_number` 是否存在
3. 当前 task 是否允许再次 `create_task`
4. retry budget / time budget / critical path 等硬边界
5. 当前是否允许自动派生 recovery subtasks
6. `failure_state`
7. `reason_code` 的主分类
8. 最终输出是否合法、是否越权

### 6.2 LLM 负责的部分

LLM 应强参与以下决策：

1. 这次失败是否仍属于原 subtask 的正常恢复范围
2. 恢复动作是否已经独立成新工作单元
3. 在允许动作集合中，最合适的 `primary_action` 是什么
4. `recommended_actions` 的优先级排序
5. `rationale`
6. 若需派生，`next_subtasks` 的高质量草案

### 6.3 分工总结

一句话总结：
1. 规则负责定性与边界
2. LLM 负责策略与解释

## 7. Recovery Planner 的关键节点

### 7.1 节点 1：Runtime 产出失败事实

在进入 Recovery Planner 之前，Runtime 已经完成：
1. 绑定 `todo_id`
2. 尝试绑定 `active_subtask`
3. 生成 `fallback_record`
4. 单独推导 subtask `status`

此时 Planner 不负责重新定义这些事实，而是消费它们。

### 7.2 节点 2：Rule Guard 先收紧动作空间

在进入 LLM 之前，规则层应先给出：
1. 当前是否允许自动恢复
2. 当前是否允许派生 recovery subtasks
3. 当前是否允许 degraded delivery
4. 当前是否允许 handoff
5. 候选动作集合

例如：
1. 若 `waiting_user_input`，则不应允许 LLM 直接给出自动重试
2. 若 retry budget 已耗尽，则不应允许继续无限 `retry_with_fix`
3. 若是 critical path，则不应允许 LLM 擅自 `degrade`

### 7.3 节点 3：LLM 判断恢复层级

这是 LLM 最重要的职责。

LLM 需要重点回答两个问题：
1. `can_resume_in_place`
2. `needs_derived_recovery_subtask`

这两个判断比写文案更重要，因为它们直接决定：
1. todo 主线是否继续稳定围绕原 subtask
2. 恢复动作是否会扩张 todo 结构

### 7.4 节点 4：LLM 选择主恢复动作

在动作集合已经被规则层收紧之后，LLM 再选择最合适的：
1. `primary_action`
2. `recommended_actions`

LLM 的判断应综合：
1. subtask 原始目标
2. 当前失败原因
3. 已有产出
4. 当前上下文边界
5. 用户真正关心的完成目标

### 7.5 节点 5：LLM 生成恢复 subtasks 草案

若 `needs_derived_recovery_subtask=true`，LLM 应生成：
1. `next_subtasks`
2. 每个 subtask 的 `name`
3. `goal`
4. `description`
5. `acceptance_criteria`
6. 尽量显式回挂 `origin_subtask_id / origin_subtask_number`

这里 LLM 的价值最大，因为高质量恢复 subtasks 很难由静态模板覆盖所有场景。

### 7.6 节点 6：Rule Guard 最终裁剪

LLM 输出后，规则层必须再做一次校验：
1. 是否包含非法动作
2. 是否越过预算边界
3. 是否擅自切换 todo 周期
4. 是否在禁止自动恢复时仍建议自动执行
5. 是否派生了没有来源锚点的 recovery subtasks

只有通过校验的输出，才进入 Runtime 的自动恢复链路。

## 8. LLM Recovery Planner 输入

建议给 LLM 的输入不是原始 runtime 杂项，而是一份整理后的结构化恢复上下文。

建议输入字段：

### 8.1 Task / Todo 级输入

1. `todo_id`
2. `task_scope_status`
3. `binding_state`
4. `execution_phase`

### 8.2 当前 Subtask 级输入

1. `subtask_id`
2. `subtask_number`
3. `name`
4. `description`
5. `status`
6. `dependencies`
7. `owner`
8. `acceptance_criteria`
9. `origin_subtask_id / origin_subtask_number`（若本身已是 recovery subtask）

### 8.3 失败事实输入

1. `failure_state`
2. `reason_code`
3. `reason_detail`
4. `retryable`
5. `required_input`
6. `evidence`
7. `retry_count`
8. `retry_budget_remaining`
9. `has_partial_value`

### 8.4 规则边界输入

1. `allowed_actions`
2. `auto_recovery_allowed`
3. `allow_degraded_delivery`
4. `is_on_critical_path`
5. `must_preserve_main_subtask`
6. `must_anchor_followups_to_origin`

### 8.5 为什么输入里必须显式带硬边界

这是为了避免让 LLM 自己猜：
1. 什么动作可以做
2. 什么动作不能做
3. 是否允许自动派生

边界若不显式传入，LLM 很容易越权。

## 9. LLM Recovery Planner 输出

建议输出 schema 至少包括：

1. `can_resume_in_place: boolean`
2. `needs_derived_recovery_subtask: boolean`
3. `primary_action: string`
4. `recommended_actions: string[]`
5. `rationale: string`
6. `resume_condition: string`
7. `suggested_owner: string`
8. `next_subtasks: object[]`

其中 `next_subtasks` 的单项建议结构：
1. `name`
2. `goal`
3. `description`
4. `kind`
5. `owner`
6. `dependencies`
7. `acceptance_criteria`
8. `origin_subtask_id`
9. `origin_subtask_number`

## 10. 与当前实现的映射

### 10.1 当前已有基础

当前已经实现：
1. `fallback_record`
2. `failure_state / reason_code`
3. `can_resume_in_place / needs_derived_recovery_subtask`
4. `primary_action / recommended_actions / rationale`
5. `next_subtasks`
6. Runtime 自动派生 recovery subtasks

### 10.2 当前缺口

当前缺口不是数据结构，而是决策生成方式：
1. `_build_recovery_decision()` 仍然是纯规则函数
2. 对复杂失败语义的理解仍然偏粗
3. `next_subtasks` 仍然偏模板化

### 10.3 建议改造路径

建议把当前 `_build_recovery_decision()` 改成两段：

1. `_build_recovery_guardrails()`
   输出规则约束与允许动作集合

2. `_generate_recovery_strategy_llm()`
   在 guardrails 内生成恢复策略草案

3. `_validate_recovery_strategy()`
   对 LLM 输出再做裁剪与回退

最终：
1. LLM 成为真正的 strategy planner
2. 规则仍然守住边界

## 11. 回退与安全策略

即使引入 LLM，也必须有稳定回退路径。

建议如下：

### 11.1 LLM 不可用时

直接回退到当前规则版 planner。

### 11.2 LLM 输出非法时

例如：
1. 给出未允许动作
2. 未返回必要字段
3. 派生 subtasks 缺少来源锚点

处理方式：
1. 记录观测
2. 回退到规则版 planner

### 11.3 LLM 输出模糊时

例如：
1. 同时说“可原地恢复”和“必须派生”
2. `primary_action` 与 `recommended_actions` 不一致

处理方式：
1. 以规则校验结果为准
2. 无法裁剪时回退规则版 planner

## 12. 观测与评估建议

引入 LLM Recovery Planner 后，建议额外记录：
1. planner 来源：`rule_only | llm_assisted | rule_fallback`
2. LLM 输出与最终裁剪结果是否一致
3. 是否发生非法输出回退
4. 原地恢复成功率
5. 派生 recovery subtask 后的成功率

这样后续才能评估：
1. LLM 是否真的提高恢复质量
2. 它是改善了策略判断，还是只是改善了文案

## 13. 结论

本稿建议把 Recovery Planner 升级为“规则守边界、LLM 做策略”的双层结构。

其核心不在于让 LLM 把话说得更好，而在于让它真正参与这两个高价值判断：
1. 当前失败是否还能围绕原 subtask 原地恢复
2. 当前恢复动作是否已经独立到需要派生 recovery subtask

在此基础上，再由规则层做最终裁剪与安全回退。

这套设计既能显著提升失败恢复的语义质量，又不会牺牲当前 todo 编排系统最重要的稳定性与可控性。
