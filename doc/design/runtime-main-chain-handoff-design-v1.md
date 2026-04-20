# Runtime Main-Chain Handoff Design v1

## 1. 背景

当前 Runtime 的 `verification_handoff` 不是由主链路最终输出直接产出，而是在收尾阶段通过独立链路额外构建：

1. 主链路 Agent 先生成 `final_answer`
2. Runtime 在 `finalizing(handoff)` 步骤中调用 `build_verification_handoff`
3. `build_verification_handoff` 先生成一份 rule-based fallback handoff
4. 若启用开关，则再额外调用一次 handoff LLM 生成候选结构
5. 最终 verifier / postmortem / memory 消费的是这一份额外构建的 handoff

这带来几个问题：

1. 用户看到的最终答案与 verifier 消费的 handoff 可能不一致
2. handoff 并不是主链路 Agent 自己的正式交付物，而是后处理产物
3. handoff 的格式要求主要藏在旧的旁路 handoff service 中，而不在主链路 prompt 中
4. handoff 额外走了一条独立 LLM / fallback 构建链，增加了复杂度与漂移风险

## 2. 设计目标

本设计希望把 handoff 从“收尾后的额外旁路产物”改回“主链路 finalizing 阶段直接产出的标准化交付”。

目标如下：

1. `handoff` 由主链路 Agent 在 finalizing 阶段直接产出
2. 产出 handoff 时，使用主链路原本的 LLM，而不是额外 handoff 专用 LLM
3. handoff 生成应可读取主链路已有上下文，而不是再做一轮单独上下文挑选
4. handoff 的格式要求应写进 finalizing prompt，而不是仅存在于旁路 service
5. verifier / postmortem / memory 统一消费主链路 handoff
6. 删除旧旁路 handoff service 中“额外生成 handoff”的职责

## 3. 非目标

本次设计不处理以下事项：

1. 不重写 evaluator / verifier 的评分逻辑
2. 不在第一步改变 `RunOutcome` 的基础数据结构
3. 不要求一次性移除所有 normalize 逻辑
4. 不修改 todo recovery 本身的业务语义

## 4. 目标链路

改造后的目标链路如下：

1. 主链路 Agent 正常执行
2. 进入 `finalizing` 阶段
3. 同一个主链路 LLM 基于原始上下文直接输出最终收尾结果
4. 该结果中同时包含：
   - 面向用户的自然语言总结
   - 面向系统的结构化 handoff
5. Runtime 从主链路最终输出中提取 handoff
6. verifier / postmortem / memory 消费该 handoff

关键变化是：

- `final_answer` 与 `handoff` 不再来自两条不同生成链
- `handoff` 不再由 finalize 后的附加工序构造
- `handoff` 成为主链路 Agent 自身交付的一部分

## 5. 输出形式

为了兼顾用户可读性与系统可解析性，建议 finalizing 阶段采用“两段式输出”：

1. 面向用户的自然语言总结
2. 面向系统的结构化 handoff JSON

推荐格式：

```text
[Final Answer]
这里是给用户看的自然语言总结。

[Structured Handoff]
```json
{
  "goal": "string",
  "task_summary": "string",
  "final_status": "pass|partial|fail",
  "constraints": ["string"],
  "expected_artifacts": [
    {
      "path": "string",
      "must_exist": true,
      "non_empty": true,
      "contains": "string"
    }
  ],
  "key_evidence": [
    {
      "type": "file|command|test|reasoning",
      "name": "string",
      "summary": "string"
    }
  ],
  "claimed_done_items": ["string"],
  "key_tool_results": [
    {
      "tool": "string",
      "status": "ok|error",
      "summary": "string"
    }
  ],
  "known_gaps": ["string"],
  "risks": ["string"],
  "recovery": {
    "todo_id": "string",
    "subtask_id": "string",
    "subtask_number": 0,
    "fallback_record": {},
    "recovery_decision": {}
  },
  "memory_seed": {
    "title": "string",
    "recall_hint": "string",
    "content": "string"
  },
  "self_confidence": 0.0,
  "soft_score_threshold": 0.7,
  "rubric": "string"
}
```
```

说明：

1. 前半段自然语言仍用于直接展示给用户
2. 后半段 JSON 用于 handoff 提取
3. schema 应尽量沿用现有 verifier 已消费的字段，减少下游改动

## 5.1 Structured Handoff 字段语义规范

为了避免 handoff 变成“只有 schema、没有语义”的半成品，下面明确每个字段的定义、填写要求、允许空值与主要消费方。

### 顶层字段

#### `goal`

- 含义：本次 run 试图完成的原始任务目标。
- 来源：优先来自用户原始输入或 prepare 后确认的目标，不是收尾总结语。
- 要求：必填。
- 允许空值：不允许。
- 消费方：verifier、memory、恢复链路。

#### `task_summary`

- 含义：对本次 run 当前结果的简短总结，应能一句话说明做到什么程度。
- 要求：必填。
- 允许空值：不允许。
- 消费方：verifier、postmortem、memory。

#### `final_status`

- 含义：本次任务最终状态，只能是 `pass | partial | fail`。
- 规则：
  - `pass`：任务已完成，且当前证据足以支持主要完成结论。
  - `partial`：形成了部分有效结果，但未完全闭环。
  - `fail`：未形成有效交付，或关键目标失败。
- 要求：必填。
- 允许空值：不允许。
- 消费方：verifier、恢复链路、postmortem。

### 约束与目标产物

#### `constraints`

- 含义：本次执行必须遵守的明确约束。
- 例子：不能联网、不得修改既有 API 行为、只允许改 `work/` 目录。
- 要求：建议填写；若上下文中没有明确约束，可为空数组。
- 允许空值：允许空数组。
- 消费方：verifier。

#### `expected_artifacts`

- 含义：本轮结束后，理论上应该存在且可检查的关键产物。
- 注意：这是“应该被校验的交付目标”，不是“自动等同于已经存在”的声明。
- 每项字段含义：
  - `path`：产物路径。
  - `must_exist`：verifier 是否必须检查存在性。
  - `non_empty`：verifier 是否必须检查非空。
  - `contains`：若提供，表示建议检查是否包含某关键内容。
- 要求：
  - 只在确实产生或明确承诺交付文件/目录/可执行物时填写。
  - 不要把不确定存在的文件写进去。
- 允许空值：允许空数组。
- 消费方：verifier。

### 证据与执行痕迹

#### `key_evidence`

- 含义：支持结论成立的关键证据，偏“证明任务确实做到”的信息。
- 推荐类型：
  - `file`：文件存在、文件内容变更、文档生成。
  - `command`：命令输出。
  - `test`：测试通过或失败。
  - `reasoning`：没有直接产物时的高价值解释性证据。
- 要求：
  - 至少在“有明确验证动作或文件产物”时填写。
  - 若证据不足，应在 `known_gaps` 中明确承认。
- 允许空值：允许空数组，但不应与 `pass` 长期共存。
- 消费方：verifier、postmortem。

#### `claimed_done_items`

- 含义：主链路明确声称“已经完成”的事项列表。
- 原则：
  - 只能写主链路愿意对 verifier 负责的完成事项。
  - 不能把“准备做”“建议下一步做”写成已完成。
- 要求：
  - 建议必填。
  - 若模型未显式给出，runtime 可从 `Final Answer` 提炼出最小保底项。
- 允许空值：原则上不应为空；如为空，应视为 handoff 质量偏低。
- 消费方：verifier。

#### `key_tool_results`

- 含义：关键工具调用结果摘要，偏执行流水中的高价值节点。
- 与 `key_evidence` 的区别：
  - `key_tool_results` 更偏“做了哪些关键动作”。
  - `key_evidence` 更偏“哪些证据支持结论成立”。
- 要求：
  - 只保留关键动作，避免把所有工具调用都塞进来。
  - 每项至少包含 `tool`、`status`、`summary`。
- 允许空值：允许空数组。
- 消费方：postmortem、verifier。

### 缺口、风险与恢复

#### `known_gaps`

- 含义：当前明确知道但尚未解决、尚未验证或尚未覆盖的缺口。
- 原则：
  - 这是防止过度宣称的核心字段。
  - 只要有证据不足、测试未跑、结果未确认，就应该写入。
- 要求：
  - 当 `final_status != pass` 时通常应非空。
  - 当 `pass` 但仍有未验证部分时，也应非空。
- 允许空值：允许空数组。
- 消费方：verifier、恢复链路。

#### `risks`

- 含义：虽然当前已结束，但后续仍可能暴露的问题或不确定性。
- 与 `known_gaps` 的区别：
  - `known_gaps` 是明确没做完或没验证。
  - `risks` 是已结束后仍存在的潜在问题。
- 要求：建议填写；无明显风险时可为空数组。
- 允许空值：允许空数组。
- 消费方：verifier、postmortem。

#### `recovery`

- 含义：todo/subtask 恢复相关的结构化状态，用于后续恢复任务，而不是给用户展示。
- 典型字段：
  - `todo_id`
  - `subtask_id`
  - `subtask_number`
  - `fallback_record`
  - `recovery_decision`
- 要求：
  - 若本轮与 todo 恢复相关，应尽量完整保留。
  - 若无恢复上下文，可为空对象。
- 允许空值：允许空对象。
- 消费方：恢复链路。

### 记忆与评估

#### `memory_seed`

- 含义：要沉淀到 system memory 的最小经验摘要。
- 字段含义：
  - `title`：记忆标题。
  - `recall_hint`：未来什么场景应召回这条经验。
  - `content`：可复用的结果摘要或经验要点。
- 要求：必填。
- 允许空值：不允许。
- 消费方：system memory。

#### `self_confidence`

- 含义：主链路对 handoff 完整度与真实性的自评分，不等于“任务成功率”。
- 要求：建议填写，范围 `0.0 ~ 1.0`。
- 允许空值：允许 runtime 回退默认值。
- 消费方：verifier。

#### `soft_score_threshold`

- 含义：供 verifier 软评分参考的通过阈值。
- 要求：建议填写，范围 `0.0 ~ 1.0`。
- 允许空值：允许 runtime 回退默认值。
- 消费方：verifier。

#### `rubric`

- 含义：告诉 verifier 这次任务应优先按什么标准判断。
- 例子：优先评估需求覆盖、证据充分性、约束满足度。
- 要求：建议填写。
- 允许空值：允许 runtime 回退默认 rubric。
- 消费方：verifier。

## 5.2 必填、建议填写与可空策略

### 必填字段

1. `goal`
2. `task_summary`
3. `final_status`
4. `memory_seed`

### 建议强填写字段

1. `claimed_done_items`
2. `known_gaps`
3. `rubric`
4. `self_confidence`
5. `soft_score_threshold`

### 允许空数组或空对象的字段

1. `constraints`
2. `expected_artifacts`
3. `key_evidence`
4. `key_tool_results`
5. `known_gaps`
6. `risks`
7. `recovery`

### 空值保底策略

1. 若模型未提供完整 handoff，runtime 应构建最小 fallback handoff。
2. 若模型提供了 handoff，但漏掉 `claimed_done_items`，runtime 应保留 fallback 中基于 `Final Answer` 提炼出的保底完成项。
3. 若模型未提供 `memory_seed`，runtime 应回退到最小 memory seed。
4. 若模型把数组字段输出为空，不应无条件抹掉 fallback 中对真实性有帮助的关键保底信息。

## 5.3 当前消费关系

目前 `Structured Handoff` 的主要消费方如下：

1. verifier：消费 `goal`、`final_status`、`constraints`、`expected_artifacts`、`key_evidence`、`claimed_done_items`、`known_gaps`、`risks`、`rubric`
2. system memory：消费 `memory_seed`
3. todo 恢复链路：消费 `recovery`
4. postmortem：可消费 `task_summary`、`key_tool_results`、`known_gaps`、`risks`

## 6. Prompt 设计

`FINALIZING_PHASE_PROMPT` 需要从“只要求诚实总结”升级为“要求总结 + 结构化 handoff”。

应明确要求：

1. 输出必须包含两部分：
   - 面向用户的最终总结
   - 面向系统的结构化 handoff
2. handoff 必须使用严格 JSON
3. handoff 必须忠实于当前上下文，不得臆造文件、测试、命令结果或完成状态
4. 若证据不足，必须写入 `known_gaps`
5. 若任务未完全完成，`final_status` 必须为 `partial` 或 `fail`
6. 必须包含 `memory_seed`

建议在 prompt 中直接内嵌 schema，避免模型自由发挥字段名。

## 6.1 Finalize Prompt 应补充的字段级要求

除了 schema 本身，prompt 还应明确：

1. `goal` 写“任务目标”，不是“最终总结”。
2. `task_summary` 写“本次做到什么程度”。
3. `claimed_done_items` 只写真正完成的事项。
4. `expected_artifacts` 只写有把握存在或明确交付的产物。
5. `key_evidence` 应优先记录文件、命令、测试等可验证证据。
6. 若没有执行验证动作，必须把缺口写进 `known_gaps`。
7. `memory_seed` 不能缺失。
8. `pass` 不能和明显的未验证缺口同时被包装成“完全完成”。

## 7. Runtime 改造点

### 7.1 新增主链路 handoff 提取

在 Runtime 中新增提取函数，例如：

- `extract_handoff_from_final_answer(final_answer: str) -> tuple[user_facing_answer, handoff_dict, extract_status]`

提取逻辑建议：

1. 查找 `[Structured Handoff]`
2. 提取其后的 JSON fenced block
3. 解析为字典
4. 进行轻量 normalize
5. 若关键字段缺失，则返回 invalid 状态

### 7.2 finalize 链路改造

`runtime_finalization.py` 的 `finalize_completed_run` 改为：

1. 优先使用从主链路最终输出中提取到的 handoff
2. 将 handoff_source 记录为 `main_final_answer`
3. verifier / postmortem / memory 使用该 handoff

### 7.3 旧服务退场

旧旁路 handoff service 的以下职责应退场：

1. `build_rule_verification_handoff`
2. `generate_verification_handoff_llm`
3. `build_verification_handoff`

第一阶段可以保留 normalize 相关逻辑，但角色调整为：

- 只做“主链路 handoff 的轻量修整”
- 不再负责“再生成一份 handoff”

## 8. 推荐迁移步骤

### 阶段一：双轨观察

目标：先让主链路开始产出 handoff，但暂不删除旧逻辑。

步骤：

1. 修改 `FINALIZING_PHASE_PROMPT`
2. 新增 `extract_handoff_from_final_answer`
3. 主链路 final answer 中开始包含 handoff
4. 记录主链路 handoff 提取成功率
5. 迁移初期暂时保留旧旁路 handoff 逻辑作为回退

验收：

1. 主链路可稳定产出结构化 handoff
2. 提取成功率足够高
3. 用户输出可读性不明显下降

### 阶段二：主链路优先

目标：正式让 verifier / postmortem / memory 优先消费主链路 handoff。

步骤：

1. `finalize_completed_run` 优先采用主链路 handoff
2. 只有提取失败时才短暂 fallback 到旧逻辑
3. 增加观测：handoff_source = `main_final_answer|fallback_rule`

验收：

1. verifier 结果与用户最终输出的一致性提升
2. fallback 比例持续下降

### 阶段三：删除旧链路

目标：彻底移除旁路 handoff 生成机制。

步骤：

1. 移除 handoff LLM 额外生成逻辑
2. 移除 rule-based 完整 handoff 构建逻辑
3. 保留最小 normalize / validate
4. 清理 handoff_source 枚举值

验收：

1. handoff 唯一来源为主链路 finalizing
2. verifier / postmortem / memory 全部消费同一份 handoff

## 9. 风险与对策

### 风险 1：最终输出变长

原因：

- 最终答案同时承载用户总结与结构化 handoff

对策：

1. 用户总结部分保持简洁
2. handoff 放在明确分段中
3. 后续如有需要，可在展示层隐藏 handoff JSON

### 风险 2：主链路 handoff 稳定性不足

原因：

- 模型可能漏字段、字段名漂移、输出不合法 JSON

对策：

1. 在 finalize prompt 中明确 JSON-only handoff 要求
2. 直接内嵌 schema
3. 保留最小 normalize / validate 层

## 10. 当前已落地与未落地

### 已落地

1. 主链路 finalizing 已要求产出 `[Final Answer]` 与 `[Structured Handoff]`
2. handoff 已由主链路 finalize 输出提取，不再走原先的额外 handoff 生成链
3. verifier 已消费主链路 handoff
4. memory 已可从 `memory_seed` 取摘要
5. runtime 已保留最小 fallback handoff，并在主链路 handoff 不完整时做保底

### 部分落地

1. schema 已进入 prompt，但字段语义文档此前不完整，本设计稿现已补齐
2. normalize 已能处理部分字段回退，但字段级 contract 还未完全制度化
3. `recovery` 已可透传，但恢复侧与 handoff 的稳定 contract 还需要再固化

### 尚未完全落地

1. verifier 还没有逐字段充分利用 `expected_artifacts`、`key_evidence`、`rubric` 做更强判断
2. prompt 虽有 schema，但字段级“何时必须写、何时必须承认缺口”的约束还需要持续打磨
3. `Structured Handoff` 还缺少独立测试覆盖矩阵，例如：
   - `pass` + 空证据
   - `partial` + recovery
   - 有 artifact 但无 evidence
   - 有 done items 但 known_gaps 未写
4. 迁移初期可短暂保留旧旁路逻辑兜底，但当前实现已完成该历史清理

### 风险 3：用户可见输出体验受影响

原因：

- 如果 JSON 直接暴露给用户，输出会显得过重

对策：

1. 保持“两段式输出”
2. 后续在 CLI / UI 层增加 handoff 隐藏或折叠显示

## 10. 设计结论

本设计建议：

1. 将 handoff 定义为 finalizing 阶段的主交付，而不是收尾后的附加工序
2. 使用主链路原本的 LLM 和上下文直接产出 handoff
3. 将 handoff 结构要求写入 finalize prompt
4. 删除现有独立 handoff 生成链
5. 让 verifier / postmortem / memory 统一消费主链路 handoff

这将把 handoff 从“后处理产物”收敛为“主链路标准交付”，减少漂移、降低复杂度，并提高系统可解释性。
