# InDepth LLM 主导失败分类与恢复规划设计稿 V1

更新时间：2026-04-17  
状态：Draft（阶段一至阶段四已落地）

## 0. 当前落地状态

截至 2026-04-17，本文对应方案已完成阶段一至阶段四的核心实现：
1. 已引入 `failure_facts`，把 Runtime 失败出口中的运行事实单独结构化
2. 已引入单次 `LLM recovery assessment` 调用，同时输出失败解释与恢复规划
3. 已把 `failure_interpretation` 写回 `fallback_record`
4. 已让后续 `plan_task_recovery` 读取解释后的 `reason_code`
5. 已让 `LLM Recovery Planner` 输出结构化 `retry_guidance`
6. 已把 `retry_guidance` 注入 active todo context，并在下一轮 system prompt 中显式带给模型
7. 已收缩旧的 `reason_code -> primary_action` 规则映射，把普通失败动作选择退回到 `suggested_next_action` + guardrails
8. 已补充 `HTTP 504 + 长文本生成` 的回归测试，验证可被解释为 `oversized_generation_request`

当前仍未完成的部分：
1. `reason_code` 仍然保留有限枚举白名单
2. 规则 planner 仍然存在，但已退化为 guardrails 与保守 fallback
3. `retry_guidance` 已进入下一轮 prompt，但尚未对具体工具调用参数做更细粒度自动改写

## 1. 背景

当前 InDepth 的失败恢复链路已经具备一定基础能力：
1. Runtime 能在失败出口自动写入 `fallback_record`
2. Runtime 能把失败写回到 todo/subtask
3. `plan_task_recovery` 能基于 `reason_code` 输出最小恢复决策
4. 在部分场景下，系统还能自动追加 recovery subtasks

但当前实现仍然偏“规则主导”：
1. 失败类别主要由规则映射得出
2. 恢复动作也主要由 `reason_code -> action` 的规则映射决定
3. LLM 即使参与 recovery planner，也仍然工作在较强的规则结论之后

这导致一个现实问题：
1. 规则能识别“失败发生了”
2. 但未必能理解“为什么在这个任务上下文里失败”
3. 也未必能给出最合适的恢复路径

例如：
1. `HTTP 504` 可能是偶发网络抖动
2. 也可能是一次性生成长文本、输出负载过大
3. 还可能是 prompt 结构过重、上下文过长、工具链过深

如果只把它统一归类为 `execution_environment_error -> retry_with_fix`，恢复质量会明显不足。

因此，本稿提出一套“弱规则 + 强 LLM”的失败分类与恢复规划方案：
1. 弱规则负责沉淀运行事实与硬边界
2. 强 LLM 负责主导失败解释、失败分类、恢复策略与恢复拆分

## 2. 目标

1. 降低“失败类别识别过粗”导致的恢复失真
2. 让失败分类更依赖任务语义与上下文，而不只依赖静态规则
3. 让恢复方案从模板式映射升级为 LLM 主导的上下文化决策
4. 保留最小运行事实边界，避免完全交给 LLM 后失控
5. 为后续逐步削弱 `reason_code -> action` 规则映射提供迁移路径

## 3. 非目标

1. 本稿不让 LLM 直接替代 Runtime 状态机
2. 本稿不让 LLM 决定 tool 是否执行成功
3. 本稿不让 LLM 自由改写 todo 绑定关系
4. 本稿不要求首版就删除所有旧规则字段
5. 本稿不处理 UI 交互层改造

## 4. 核心判断

本稿的核心判断是：
1. 失败分类与恢复方案应主要交给 LLM
2. 但“失败事实”不应完全交给 LLM 猜测
3. Runtime 仍应保留最小事实层和边界层

换句话说：
1. 规则不再主导“这属于什么失败、应该怎么恢复”
2. 规则只负责“本轮真实发生了什么”
3. LLM 基于这些事实做解释、定性和恢复规划

## 5. 现状问题

### 5.1 当前失败分类偏静态映射

当前实现会基于：
1. `runtime_state`
2. `stop_reason`
3. `last_tool_failures`

来构造 `fallback_record`。

现有问题：
1. 规则会直接产出 `reason_code`
2. 规则会直接产出 `suggested_next_action`
3. 这导致 LLM 后续更像在“补充说明”，而不是主导决策

### 5.2 当前恢复方案仍由规则主导

当前 `plan_task_recovery` 的主分支仍然是：
1. `execution_environment_error -> retry_with_fix`
2. `budget_exhausted -> split`
3. `waiting_user_input -> wait_user`

这种方式在简单场景有效，但在复杂场景下会出现问题：
1. 相同的错误文本在不同任务里需要不同恢复路径
2. 不同错误文本在同一任务语义下可能本质相同
3. 规则无法稳定识别“这次失败真正暴露的是任务过大、上下文失配还是执行者不合适”

### 5.3 当前 LLM 恢复参与层次仍然偏后

当前 LLM 恢复 planner 更多是在：
1. 规则已有 fallback decision 之后做增强
2. 规则已有允许动作集合之后做筛选

这对安全有帮助，但也意味着：
1. LLM 很难翻案
2. 一旦规则先验过强，LLM 很难给出本质不同的解释

## 6. 设计目标拆解

我们希望把当前“规则主导”改造成三层模型：

1. 事实层
   只描述运行中客观发生的事实

2. 解释层
   由 LLM 主导回答“这次失败本质上是什么”

3. 恢复层
   由 LLM 主导回答“下一步最合适怎么恢复”

对应关系：

```text
运行事实 -> LLM 恢复判定 -> 规则边界校验 -> Runtime 落地
```

## 7. 总体设计

### 7.1 三层模型

建议把现有恢复链路拆成下面三层：

1. Fact Envelope
   由 Runtime 构造，只包含运行事实与硬边界。

2. LLM Recovery Assessment
   由单次独立 LLM 调用完成，同时负责失败定性、失败解释、恢复方案与 follow-up subtasks。

3. Runtime Guard Layer
   负责校验输出、收紧边界并在 LLM 输出无效时回退到保守方案。

### 7.2 Fact Envelope 的职责

Fact Envelope 不再直接下结论，只保留事实：
1. `runtime_state`
2. `stop_reason`
3. `last_tool_failures`
4. `model_error_text`
5. `had_partial_output`
6. `retry_count`
7. `retry_budget_remaining`
8. `active_todo_id`
9. `active_subtask_id`
10. `execution_phase`
11. `is_on_critical_path`
12. `allowed_degraded_delivery`

关键点：
1. 事实层不直接给强解释
2. 事实层不再默认输出强结论式 `reason_code -> suggested_next_action`
3. 事实层只在极少数硬场景产出不可争议边界，例如“必须等待用户输入”

### 7.3 LLM Recovery Assessment 的职责

该节点同时负责失败解释与恢复规划，输出内容建议包括：
1. `failure_label`
2. `reason_code`
3. `reason_detail`
4. `confidence`
5. `evidence`
6. `retryable`
7. `suspected_root_causes`
8. `recovery_risks`
9. `primary_action`
10. `recommended_actions`
11. `retry_guidance`
12. `next_subtasks`

这里的关键变化是：
1. `reason_code` 不再由规则直接决定
2. `reason_detail` 不再只是截断的错误文本
3. 恢复动作不再由规则直接映射
4. LLM 需要结合任务语义一次性给出“是什么问题、下一步怎么办”

例如 `HTTP 504`：
1. 在“短问答”场景下可能偏向基础环境抖动
2. 在“3000 字论文一次性生成”场景下可能更应解释为“单次生成负载过大”

### 7.4 为什么采用单次 LLM 调用

相比“先失败解释、再恢复规划”的双调用方式，单次 LLM 调用更适合当前链路：
1. 避免两次调用之间的解释漂移
2. 降低失败路径上的模型调用成本与时延
3. 降低 prompt、normalize 与 fallback 的维护复杂度
4. 让 Runtime 只需要消费一次结构化恢复判定结果

### 7.5 规则仍然保留的边界

规则保留的内容应尽量收缩为边界，而不是主结论：
1. 是否绑定到了有效 todo/subtask
2. 是否已经耗尽 retry budget
3. 是否必须等待用户输入
4. 是否允许自动 append subtasks
5. 是否允许 degraded delivery
6. 是否允许越过 critical path 改变交付承诺

这些规则只做：
1. 拦截非法恢复
2. 收紧可执行边界
3. 校验 LLM 输出是否合法

不再做：
1. 主导失败分类
2. 主导恢复动作选择

## 8. 新的链路设计

建议的新链路如下：

```text
Runtime failure
-> build_fact_envelope
-> produce conservative rule fallback
-> single LLM recovery assessment
-> normalize interpreted failure + recovery plan
-> validate with runtime guardrails
-> decide whether auto-apply / append subtasks / reopen subtask
```

对应到工程层：
1. `build_runtime_fallback_record` 变为 `build_runtime_failure_fact_envelope`
2. `generate_recovery_assessment_llm` 单次输出失败解释与恢复决策
3. `normalize_failure_interpretation` 与 `normalize_llm_recovery_assessment` 负责拆分和归一化输出
4. 现有规则 planner 收缩为 guardrails 生产器和输出校验器

## 9. 输出模型建议

### 9.1 事实层输出

建议输出结构：

```json
{
  "runtime_state": "failed",
  "stop_reason": "model_failed",
  "model_error_text": "Model request failed after retries: HTTP 504 ...",
  "tool_failures": [],
  "final_answer_preview": "...",
  "retry_count": 1,
  "retry_budget_remaining": 1,
  "todo_id": "xxx",
  "subtask_id": "st_xxx",
  "subtask_number": 3,
  "execution_phase": "executing",
  "allowed_degraded_delivery": false,
  "is_on_critical_path": false
}
```

### 9.2 LLM 恢复判定输出中的失败解释部分

建议输出结构：

```json
{
  "failure_label": "generation_overload",
  "reason_code": "oversized_generation_request",
  "reason_detail": "本次失败更像是长文本一次性生成导致的请求超时，而不是普通环境抖动。",
  "confidence": 0.82,
  "retryable": true,
  "evidence": [
    "stop_reason=model_failed",
    "error contains HTTP 504",
    "task goal requires long-form generation"
  ],
  "suspected_root_causes": [
    "single-request payload too large",
    "long-form generation in one turn"
  ],
  "recovery_risks": [
    "retrying unchanged may reproduce the same 504"
  ]
}
```

### 9.3 LLM 恢复判定输出中的恢复规划部分

建议输出结构：

```json
{
  "can_resume_in_place": false,
  "needs_derived_recovery_subtask": true,
  "primary_action": "split",
  "recommended_actions": ["split", "retry_with_fix"],
  "rationale": "继续原样重试大概率复现同一失败，应先缩小单次生成粒度。",
  "resume_condition": "已将原任务拆成更小的分段生成步骤。",
  "retry_guidance": [
    "每次只生成一节或 300-600 字",
    "每段生成后立即写入 Markdown",
    "避免再次一次性生成全文"
  ],
  "stop_auto_recovery": false,
  "suggested_owner": "main",
  "next_subtasks": [
    {
      "name": "生成引言部分",
      "goal": "先完成论文引言并写入文档",
      "description": "基于大纲和参考材料只生成引言部分，不扩展到全文",
      "kind": "execute",
      "owner": "main",
      "depends_on": ["3"],
      "acceptance_criteria": ["引言生成完成", "已写入目标 Markdown"]
    }
  ]
}
```

## 10. 字段迁移策略

### 10.1 `reason_code` 的迁移

当前 `reason_code` 是规则主产物。

建议改成：
1. 规则不再直接给最终 `reason_code`
2. LLM 给出候选 `reason_code`
3. 规则只校验是否属于允许集合

允许集合可以先做成有限枚举，避免 observability 污染过快。

### 10.2 `suggested_next_action` 的迁移

当前 `suggested_next_action` 在 `fallback_record` 里由规则直接输出。

建议改成：
1. 事实层不再强行填写动作
2. 可先保留该字段作为兼容字段
3. 值改为来自 recovery planner 的 `primary_action`

### 10.3 `fallback_record` 的迁移

建议把当前 `fallback_record` 逐步拆成两部分：
1. `failure_facts`
2. `failure_interpretation`

为兼容历史数据，首版可以保留 `fallback_record`，但字段语义调整为：
1. `fallback_record.facts`
2. `fallback_record.interpretation`
3. `fallback_record.recovery_hint`

## 11. 分阶段落地计划

### 11.1 阶段一：保留现有接口，削弱规则结论

状态：已落地

目标：
1. 不大改工具接口
2. 先把规则从“主导结论”降级为“提供事实和 guardrails”

改动建议：
1. `build_runtime_fallback_record` 内部改为先构建 `failure_facts`
2. 对 `reason_code/suggested_next_action` 只保留兼容默认值
3. 新增 `failure_interpretation` 到 recovery context
4. LLM recovery planner 读取 `failure_facts + failure_interpretation + guardrails`

### 11.2 阶段二：引入单次 LLM 恢复判定

状态：已落地

目标：
1. 让 LLM 在单次调用中同时产出失败解释与恢复规划
2. 让解释后的 `reason_code` 回写到 `fallback_record`
3. 让 rule planner 读取解释后的失败结论

改动建议：
1. 新增或升级为 `generate_recovery_assessment_llm`
2. `normalize_failure_interpretation` 与 `normalize_llm_recovery_assessment` 负责拆分结构
3. recovery planner guardrails 只保留 fallback 与边界职责

### 11.3 阶段三：让 recovery plan 真正主导 runtime 恢复

状态：部分落地

目标：
1. 让 LLM 输出不只是记录到 handoff
2. 而是真正驱动 `reopen_subtask / append_followup_subtasks / retry guidance`

改动建议：
1. 在 recovery context 中持久化 `retry_guidance`
2. Runtime 在 reopen/retry 时把 guidance 注入下一轮上下文
3. 对自动 split 场景优先执行 LLM 产出的 `next_subtasks`

当前已完成：
1. `retry_guidance` 已写回 `fallback_record`
2. `update_active_todo_context` 已把 `retry_guidance` 保存在 active todo context 中
3. `AgentRuntime._build_system_prompt` 已在存在 guidance 时附加 `Retry Guidance` 段落

当前未完成：
1. 还未根据 `retry_guidance` 自动改写具体工具参数
2. 还未让所有恢复类型都生成更细粒度的执行补丁

### 11.4 阶段四：收缩旧规则映射

状态：已落地

目标：
1. 去掉大部分 `reason_code -> primary_action` 硬映射
2. 保留最少边界规则

本阶段已完成：
1. `plan_task_recovery` 不再对普通失败执行大规模 `reason_code -> primary_action` 硬映射
2. 普通失败默认优先读取 `fallback_record.suggested_next_action`
3. 当 `suggested_next_action` 缺失时，仅按 `retryable` 做保守兜底
4. `recommended_actions` 从窄规则表改为更宽的 guardrail 集合
5. `build_runtime_fallback_record` 不再为大多数普通失败预设 `suggested_next_action`
6. `suggested_next_action` 目前只在少数硬边界场景保留，例如 `wait_user`、`split(length/max_steps)`

保留项：
1. `awaiting_user_input` 必须暂停
2. retry budget 耗尽必须停止自动原地重试
3. `budget_exhausted/timed_out` 仍必须转入收缩范围或显式接受降级交付
4. `dependency_unmet` 仍优先要求先解依赖
5. `orphan_subtask_unbound` 仍必须进入 handoff/人工决策
6. critical path 改变交付承诺必须升级到 `user_confirm`

效果：
1. 失败解释与恢复动作的主导权进一步转移到单次 LLM recovery assessment
2. 规则层从“给结论”进一步收缩为“限制越界、提供保守 fallback”

## 12. 风险与对策

### 12.1 风险：LLM 输出漂移

问题：
1. 同类失败可能产生不同分类文案
2. 导致 observability 难以聚合

对策：
1. 对 `reason_code` 建立白名单枚举
2. 保留 `failure_label` 供更灵活表达
3. normalize 阶段把自由输出收敛到稳定字段

### 12.2 风险：LLM 过度自信

问题：
1. LLM 可能把环境错误解释得过于语义化
2. 导致恢复方案过拟合

对策：
1. 输出 `confidence`
2. 要求给出 `evidence`
3. 低置信度时回落到保守恢复动作

### 12.3 风险：LLM 越过边界

问题：
1. 擅自更改 todo 绑定
2. 擅自宣告成功
3. 擅自降级交付

对策：
1. guardrails 显式约束允许动作
2. normalize 层做强校验
3. 非法输出直接回退到保守方案

### 12.4 风险：链路变长，失败点变多

问题：
1. 失败路径上的单次恢复判定调用仍会增加额外模型成本
2. 若恢复判定输出无效，仍需回退到保守规则方案

对策：
1. 保持单次调用，不再拆成两个解释器
2. LLM 输出无效时，退回保守规则恢复
3. 对 mini model 做优先配置，控制成本和时延

## 13. 对现有模块的影响

预计会影响这些模块：
1. `app/core/runtime/todo_runtime_lifecycle.py`
2. `app/core/runtime/recovery_planner_service.py`
3. `app/tool/todo_tool/todo_tool.py`
4. `app/core/runtime/agent_runtime.py`
5. `tests/test_todo_recovery_flow.py`
6. `tests/test_runtime_todo_recovery_integration.py`

重点改造点：
1. `build_runtime_fallback_record`
2. `generate_recovery_decision_llm`
3. `normalize_llm_recovery_decision`
4. recovery context 持久化结构

## 14. 测试建议

建议新增或调整以下测试：

1. 当 `HTTP 504` 发生在长文本生成任务时，LLM 可将其解释为“过载型生成失败”
2. 当 `HTTP 504` 发生在短问答任务时，LLM 可保守解释为“瞬时环境失败”
3. LLM 输出非法 `primary_action` 时，系统会被 guardrails 收敛
4. retry budget 耗尽时，即使 LLM 想继续原地重试，也会被拦截
5. `retry_guidance` 能进入 recovery context，并在下一轮恢复时可见

## 15. 结论

本稿建议的不是“完全取消规则”，而是把规则从“主导失败分类与恢复策略”降级为“提供事实与边界”。

新的分工应是：
1. Runtime/规则负责记录真实发生的运行事实
2. LLM 负责主导失败解释与恢复规划
3. Guardrails 负责兜底、校验和边界收缩

这样既能避免纯规则恢复过于僵硬，也能避免纯 LLM 恢复失去稳定性和可控性。
