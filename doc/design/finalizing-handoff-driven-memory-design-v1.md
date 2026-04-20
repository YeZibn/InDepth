# Finalizing Handoff 驱动验证与记忆沉淀设计方案（V1）

更新时间：2026-04-20  
状态：Implemented（已按 V1 落地）

## 1. 背景

当前 Runtime 在任务收尾阶段存在两条相互独立、但输入事实高度重叠的链路：
1. `verification_handoff`：供 verifier 判断任务是否真正完成。
2. `system memory finalize / candidate capture`：供系统经验沉淀与后续 recall 使用。

这带来了几个问题：
1. 重复总结：verification 与 memory 都在各自做一次“运行事实整理”。
2. 事实源不一致：verifier 与 memory card 可能基于不同总结结果。
3. 运行中候补记忆质量不稳定：任务尚未结束时，事实未收敛，容易把中间态误沉淀为长期经验。
4. memory card 结构过重：历史 schema 同时承担“治理档案”和“召回单元”职责，不利于后续向量检索。

## 2. 核心目标

本方案目标：
1. 将 `handoff` 升级为 final 阶段主链路产出的核心结构化结果。
2. 让 `handoff` 成为 verification 与 memory 沉淀的共同事实源。
3. 删除运行中候补记忆卡片；正式 memory card 只能在任务结束后基于 handoff 沉淀。
4. 简化 memory card schema，使其更适合作为 recall 与向量检索的索引对象。
5. 保持 Runtime 主链路完整，不额外派生独立 handoff agent。

## 3. 非目标

本次不做：
1. 不改 Runtime 会话记忆（`runtime_memory.db` / `messages` / `summaries`）压缩策略。
2. 不直接在本方案中落地向量数据库选型与工程接入细节。
3. 不扩展新的中间态 memory candidate 概念。
4. 不要求用户回答与系统 handoff 在同一次模型输出中同时完成。

## 4. 设计原则

1. 单源事实：verification 与 memory 只能基于同一份 final handoff。
2. 结束后沉淀：长期系统记忆只能由任务结束后的 handoff 生成。
3. 运行中只记事实，不沉淀记忆：执行中的观察可进入 event / trace，但不能直接写 memory card。
4. 轻量 recall：run-start recall 仍然只注入轻量信息，而不是整卡全文。
5. 结构化优先：handoff 必须是稳定 JSON，便于 verifier、memory builder、postmortem 共用。
6. 失败可回退：若 handoff step 失败，系统仍可退回规则 fallback handoff，不能阻塞主流程。

## 5. 最终方案概览

新的任务收尾链路统一为：

`executing -> finalizing(answer) -> finalizing(handoff) -> verification -> memory persist -> vector index`

含义：
1. `executing`
   - 完成实际工作、工具调用与产物生成。
2. `finalizing(answer)`
   - 基于已有事实生成面向用户的 `final_answer`。
3. `finalizing(handoff)`
   - 在同一主链路中追加一个独立 handoff step，读取完整上下文并输出严格 JSON。
4. `verification`
   - verifier 优先消费这份 handoff。
5. `memory persist`
   - 从 handoff 派生正式 memory card。
6. `vector index`
   - 后续向量检索索引基于 memory card 建立。

## 6. handoff 的职责定位

`handoff` 不是：
1. 不是用户最终答案。
2. 不是完整原始日志。
3. 不是长期 recall 单元本身。

`handoff` 是：
1. 任务结束后的结构化交接单。
2. verifier 的直接输入。
3. memory card 的唯一事实来源。
4. postmortem 与后续审计的稳定中间结果。

handoff 需要回答这些问题：
1. 用户原始目标是什么。
2. 本次运行实际完成了什么。
3. 产出了什么文件或结果。
4. 哪些环节存在缺口、风险或恢复建议。
5. 本次最值得沉淀的经验摘要是什么。

## 7. handoff 的生成方式

### 7.1 生成策略

不再额外派生独立 handoff LLM 链路，而是在原 Runtime 主链路进入 `finalizing` 阶段后，新增一个 `handoff_step`。

即：
1. 主模型完成执行。
2. 主模型生成 `final_answer`。
3. Runtime 追加一个新的 finalizing 子步骤。
4. 同一主模型在该步骤中仅输出 handoff JSON。

这意味着 final 阶段是一个显式双 step：
1. `finalizing(answer)`：面向用户的自然语言收尾。
2. `finalizing(handoff)`：面向系统的结构化交接。

### 7.2 为什么不单独起 handoff agent

原因：
1. 与原始执行上下文距离更近，忠实度更高。
2. 不重复启动额外总结链路。
3. 更符合现有 phase overlay / prompt 改写机制。
4. 更容易保证输出和 `final_answer`、todo/recovery、tool facts 一致。

### 7.3 为什么不和 final_answer 合并成同一次输出

不建议把用户回答和 handoff 混在一起输出，因为：
1. 用户回答需要自然语言。
2. handoff 需要严格 JSON。
3. 两类输出目标冲突，格式稳定性差。

因此推荐：
1. `finalizing(answer)`：自然语言回答。
2. `finalizing(handoff)`：结构化 JSON。

补充说明：
1. 双 step 指的是同一个 Runtime 在 final 阶段连续执行两个子步骤。
2. 不是两个 agent，也不是两个线程。
3. answer step 与 handoff step 各自失败时可独立观测和回退。

## 8. handoff 的输入上下文

V1 方案采用“直接读取 final 阶段已有上下文”的方式，不额外构造复杂的 `handoff_context` builder。

即：
1. handoff step 复用主链路在 `finalizing` 阶段已经保留的上下文。
2. handoff step 在 prompt 中被明确要求基于已有上下文抽取结构化事实。
3. Runtime 不再为了 handoff 专门组装一层新的复杂中间对象。

在显式双 step 下，`finalizing(handoff)` 默认读取：
1. `finalizing(answer)` 结束后的完整上下文。
2. 已生成的 `final_answer`。
3. 当前 run 的 stop / recovery / tool facts。

V1 中 handoff 实际可读取到的上下文应至少覆盖：
1. 用户输入与任务目标。
2. `final_answer`。
3. `stop_reason` 与 `runtime_status`。
4. final 阶段前的关键执行上下文。
5. todo / recovery 相关上下文。
6. run-start recall 注入过的轻量记忆上下文。

约束：
1. handoff step 直接吃上下文不等于“无约束自由总结”。
2. 需要通过 finalizing prompt 改写，明确要求模型关注完成项、关键产物、已知缺口、恢复信息与 memory seed。
3. 若后续发现长上下文下 handoff 稳定性不足，再在 V2 中补充结构化 `handoff_context`。

## 9. handoff schema（V1）

建议 handoff 统一输出为：

```json
{
  "goal": "string",
  "task_summary": "string",
  "final_status": "pass|partial|fail",
  "claimed_done_items": ["string"],
  "expected_artifacts": [
    {
      "path": "string",
      "status": "created|updated|missing|unknown",
      "summary": "string"
    }
  ],
  "key_evidence": [
    {
      "type": "tool|file|test|todo|recovery|memory",
      "name": "string",
      "summary": "string"
    }
  ],
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
    "subtask_number": 1,
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

字段说明：
1. `goal`
   - 用户原始目标的简明重述。
2. `task_summary`
   - 本次任务整体发生了什么。
3. `final_status`
   - 模型基于现有事实的自我状态判断。
4. `claimed_done_items`
   - 明确宣称已完成的事项。
5. `expected_artifacts`
   - 产物列表与状态。
6. `key_evidence`
   - 给 verifier 与 postmortem 的关键证据摘要。
7. `known_gaps`
   - 未完成项与证据不足项。
8. `risks`
   - 已知风险或后续注意事项。
9. `recovery`
   - 恢复闭环所需结构化信息。
10. `memory_seed`
   - 供 memory card 派生的唯一种子。

## 10. verifier 如何使用 handoff

新的优先级：
1. 若 `finalizing(handoff)` 成功产出合法 JSON，则 verifier 直接使用该 handoff。
2. 若 handoff step 失败、输出非法或严重缺字段，则退回规则 fallback handoff。

因此：
1. handoff 成为 verifier 的主路径输入。
2. 规则 fallback 退化为兜底逻辑，而不是主路径。

好处：
1. verifier 与 memory 使用同一事实源。
2. 手工 fallback 仅用于保障系统稳定，不再承担主总结职责。

## 11. memory card 如何从 handoff 派生

### 11.1 删除运行中候补记忆卡片

本方案明确规定：
1. 删除运行中 candidate / draft memory card 的主链路角色。
2. 执行过程中不允许直接沉淀长期 system memory。
3. 运行中记录的观察只能进入 event / trace。

约束：
1. 没有 final handoff，就没有正式 memory。
2. 没结束的任务不允许写入正式 memory card。

### 11.2 新的 memory 生命周期

新的 memory 流程仅保留：

`run start recall -> run execution -> final_answer -> handoff -> memory persist`

即：
1. 运行开始时只能读 memory recall。
2. 运行中不写 memory card。
3. 任务结束后只从 handoff 生成正式 memory card。

### 11.3 简化后的 memory card schema

正式 memory card 精简为：
1. `id`
2. `title`
3. `recall_hint`
4. `content`
5. `status`
6. `updated_at`
7. `expire_at`

字段来源：
1. `title <- handoff.memory_seed.title`
2. `recall_hint <- handoff.memory_seed.recall_hint`
3. `content <- handoff.memory_seed.content`
4. `status` 默认由 Runtime finalize 决定（如 `active`）
5. `updated_at / expire_at` 由系统写入

### 11.4 为什么 memory card 要更轻

原因：
1. 更适合作为 recall 单元。
2. 更适合作为向量检索索引对象。
3. 减少 schema 复杂度与长期治理成本。
4. 避免把“治理档案”和“召回对象”继续混在一起。

## 12. 向量检索的衔接方式

本方案不直接规定具体向量数据库，但明确 recall 对象是新的轻量 memory card。

建议 embedding 文本：

```text
title: {title}
recall_hint: {recall_hint}
content: {content}
```

run-start recall 过程：
1. 使用当前 `user_input` 构造检索向量。
2. 从向量库检索 top K memory cards。
3. prompt 注入仍然只注入：
   - `memory_id`
   - `recall_hint`
4. 如后续确有需要，再按 `memory_id` 拉取完整 `content`。

因此：
1. 向量索引层不需要索引整份 handoff。
2. handoff 只作为 memory card 的生成源。

## 13. Prompt / phase 机制改造建议

当前已有 `finalizing` phase overlay，建议扩展为两个子阶段：

1. `finalizing(answer)`
   - 目标：输出用户最终回答
   - 约束：不再扩张任务

2. `finalizing(handoff)`
   - 目标：输出 handoff JSON
   - 约束：
     - 不允许生成自然语言结语
     - 不允许虚构文件或成功项
     - 若证据不足必须写入 `known_gaps`
     - 只输出严格 JSON

说明：
1. 不新增独立 handoff agent。
2. 仅通过 final phase 的 prompt 改写完成 handoff 生成。
3. Runtime 需要把这两个子阶段作为显式顺序执行的 finalizing 子步骤，而不是把 handoff 继续藏在 verifier 前的内部 helper 中。

## 14. Runtime 侧改造建议

建议新增或调整以下结构：

1. `handoff_step`
   - 调用同一主模型，直接基于 final 阶段已有上下文输出 handoff JSON。
   - 该步骤在 `finalizing(answer)` 之后、`verification` 之前执行。

2. `verification input priority`
   - 优先使用 handoff_step 结果。

3. `memory persist from handoff`
   - 删除 run 中候补卡逻辑。
   - finalize 后从 `memory_seed` 直接生成正式 card。

4. `V2 optional path`
   - 若后续 handoff 在长上下文场景下稳定性不足，再引入结构化 `handoff_context` builder。

## 15. 失败回退策略

若 `handoff_step` 失败：
1. 生成规则 fallback handoff。
2. verifier 使用 fallback handoff 继续运行。
3. memory persist 可选择：
   - 跳过本次沉淀
   - 或使用 fallback 中有限字段生成低置信度 memory（V1 建议默认跳过）

回退原则：
1. handoff step 失败不能阻塞任务结束。
2. verifier 不能因为 handoff step 失败而整体失效。
3. 正式 memory 默认只接受 handoff 主路径结果，避免低质量回退数据污染 recall。

## 16. 实施顺序

建议分四步落地：

### Phase 1：schema 与职责收敛
1. 冻结新 handoff schema。
2. 冻结新 memory card schema。
3. 明确“正式 memory 只能由 handoff 生成”的规则。

### Phase 2：Runtime finalizing 改造
1. 新增 `finalizing(handoff)` step。
2. 将 final 阶段显式拆成 `answer -> handoff` 双 step。
3. 通过 prompt 改写让 handoff step 直接读取 final 阶段已有上下文。
4. 调整 verification 优先消费 handoff step 结果。

### Phase 3：memory finalize 改造
1. 删除或弱化运行中候补记忆卡主链路。
2. 将 memory persist 改为 handoff -> memory card。
3. 调整相关 observability 与测试。

### Phase 4：向量召回接入
1. 基于新的 memory card 建 embedding。
2. 在 run-start recall 接入向量检索。
3. 保持轻量注入策略不变。

## 17. 验收标准

1. Runtime 主链路最终能稳定产出合法 handoff JSON。
2. Runtime final 阶段已显式拆分为 `finalizing(answer)` 与 `finalizing(handoff)` 两个子步骤。
3. verifier 优先消费 handoff，并与 `final_answer`、tool facts 保持一致。
4. 系统中不再存在“运行中候补记忆卡片”的正式写入链路。
5. 正式 memory card 仅在任务结束后生成。
6. memory card schema 收敛到最小集合：`id/title/recall_hint/content/status/updated_at/expire_at`。
7. handoff 与 memory card 可稳定支撑后续向量检索接入。

## 18. 最终决议

本方案最终确定以下结论：
1. `handoff` 是 final 阶段主链路产出的核心结构化结果。
2. `handoff` 是 verification 与 memory 沉淀的共同事实源。
3. 不额外派生独立 handoff agent，而是在 `finalizing` 阶段追加 `handoff_step`。
4. final 阶段显式采用 `answer -> handoff` 双 step。
5. handoff 输入必须更完整，V1 直接读取 final 阶段已有上下文。
6. 删除运行中候补记忆卡片。
7. 正式 system memory 只能在任务结束后基于 handoff 生成。
8. memory card schema 精简为轻量 recall / vector index 友好格式。
