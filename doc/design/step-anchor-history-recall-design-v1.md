# Step Anchor And History Recall 设计稿（V1）

更新时间：2026-04-18  
状态：V1 设计中（待实现）

## 1. 背景与问题

当前 Runtime memory 的结构化摘要已经可以在 `midrun/finalize` 阶段沉淀：
1. `task_state`
2. `decisions`
3. `constraints`
4. `artifacts`
5. `open_questions`

但系统仍缺少稳定的“回溯原始执行现场”的能力，主要问题有：

1. 结构化摘要缺少稳定来源指针。
- 当前 `decision / constraint / artifact` 只表达“归纳后的结论”，不表达“结论来自哪次执行的哪一步”。

2. `step` 是 runtime 内部概念，但没有在 `messages` 表持久化。
- 当前可以在单次 run 执行过程中知道“第几步”，但消息落库后无法再稳定回查“某条消息属于哪个 step”。

3. `run_id` 虽在 runtime 中存在，但未写入消息层。
- 这导致跨 run 时难以可靠区分消息来自哪次执行。

4. 当前缺少一个面向模型的、可控的历史回溯入口。
- 即使默认不再 destructive finalize，模型也不会自动重新看到旧消息。
- 缺少一个显式工具来按执行单元把历史证据重新召回到上下文。

对于当前 Runtime 来说，问题的关键不是“是否保留原始消息”，而是：
1. 原始消息能否按稳定执行边界被索引；
2. 结构化摘要能否指向这些边界；
3. 模型能否在必要时以受控方式回看对应原文。

## 2. 目标

V1 目标：
1. 在 `messages` 表中持久化 `run_id` 与 `step_id`。
2. 为结构化摘要中的 `decision / constraint / artifact` 引入轻量 `source_anchor`。
3. `source_anchor` 第一版仅索引：
   - `run_id`
   - `step_id`
4. 提供一个显式 `history_recall` tool，默认按 `step` 粒度召回原始消息。
5. 保持对现有历史数据的兼容，不要求立即迁移补齐所有旧消息的 `run_id / step_id`。

## 3. 非目标

V1 不做：
1. 不在本稿中引入自动回溯策略；回溯只通过 tool 显式触发。
2. 不在第一版 anchor 中写入 `primary_message_id`。
3. 不为 `task_state.goal / progress / next_step` 增加 anchor。
4. 不引入独立 anchor 表或图结构。
5. 不重写现有 summary merge 主流程，只做可选增强。

说明：
1. 本稿先解决“step 级执行现场定位”和“tool 化回溯入口”。
2. 更细粒度的 message 级证据链可以作为后续 V2 能力。

## 4. 设计原则

1. 回溯应以稳定执行边界为中心，而不是以脆弱的临时位置索引为中心。
2. 第一版 anchor 必须足够轻量，不应显著增加 summary merge 复杂度。
3. 回溯能力默认应当显式、可控、易调试。
4. 优先使用现有 runtime 概念：`run_id + step_id`，避免重新发明新的轮次模型。

## 5. 核心概念

### 5.1 `run`

`run` 指一次 runtime 执行周期。

特征：
1. 对每次 `runtime.run(...)` 都存在一个稳定的 `run_id`
2. 跨 run 时会重新生成
3. `run_id` 适合作为跨执行批次的一级边界

### 5.2 `step`

`step` 指单次 run 内的一步执行单元。

特征：
1. 对应 runtime 内部一次模型请求及其紧邻产物
2. 在 run 内单调递增
3. 跨 run 会重置，因此必须与 `run_id` 组合使用

### 5.3 `source_anchor`

`source_anchor` 指结构化对象对执行来源的轻量指针。

V1 中仅包含：
1. `run_id`
2. `step_id`

语义：
1. 该结构化对象主要来源于哪次 run 的哪一步
2. 不承担“定位到某条具体消息”的职责
3. 用于回溯 tool 的 step 级召回

## 6. 方案概览

### 6.1 消息层：补 `run_id + step_id`

在 `messages` 表新增：
1. `run_id TEXT`
2. `step_id TEXT`

要求：
1. Runtime 在落消息时应尽量写入当前 `run_id + step_id`
2. 历史数据允许为空
3. 后续查询与 recall 要兼容空值

### 6.2 摘要层：为部分结构化对象增加 `source_anchor`

第一版支持对象：
1. `decisions`
2. `constraints`
3. `artifacts`

不支持对象：
1. `task_state.goal`
2. `task_state.progress`
3. `task_state.next_step`

原因：
1. `task_state` 更像聚合结果，来源通常跨多个 step，不适合第一版强行锚定。

### 6.3 Tool 层：新增 `history_recall`

新增一个显式工具，默认按 `step` 粒度召回原始消息。

输入方式建议：
1. 直接传 `run_id + step_id`
2. 或传结构化对象中的 `source_anchor`

返回内容：
1. 该 step 下的原始消息列表
2. 按写入顺序排序
3. 可选附带前后相邻 step 的轻量预览

## 7. 数据模型设计

### 7.1 `messages` 表变更

当前 `messages` 主要字段包括：
1. `id`
2. `conversation_id`
3. `role`
4. `content`
5. `tool_call_id`
6. `tool_calls_json`

V1 建议新增：

```sql
ALTER TABLE messages ADD COLUMN run_id TEXT;
ALTER TABLE messages ADD COLUMN step_id TEXT;
```

说明：
1. 允许为空
2. 不要求对历史数据做回填
3. 新写入消息尽量完整写入

### 7.2 `step_id` 形态

建议：
1. 使用 `TEXT` 而不是 `INTEGER`
2. V1 可直接存简单字符串，如：
   - `"1"`
   - `"2"`
   - `"3"`

原因：
1. 避免未来扩展时受列类型限制
2. 对当前用途足够简单

### 7.3 `source_anchor` 结构

建议采用内嵌对象，而不是扁平字段。

示例：

```json
{
  "id": "d_1",
  "what": "先修改配置层，再调整 runtime 接线",
  "why": "降低回归风险",
  "turn": 4,
  "confidence": "high",
  "source_anchor": {
    "run_id": "runtime_cli_29837942",
    "step_id": "7"
  }
}
```

约束：
1. `source_anchor` 为可选字段
2. V1 不写 `primary_message_id`
3. 当来源不明确或跨多个 step 时，可省略

## 8. 写入与接线设计

### 8.1 Runtime 消息写入

需要统一调整 Runtime 中向 `memory_store.append_message(...)` 写消息的路径。

建议：
1. 为 `append_message(...)` 增加可选参数：
   - `run_id: str = ""`
   - `step_id: str = ""`
2. `SQLiteMemoryStore` 在落库时将其写入 `messages.run_id / messages.step_id`
3. 现有调用方若未传值，默认空字符串或 `NULL`

### 8.2 哪些消息要写 `run_id + step_id`

V1 建议至少覆盖：
1. assistant 消息
2. tool 消息
3. 运行中补写的 user 消息（如果当前 runtime 会把 user 输入写入 messages）

原则：
1. 同一个 step 内写入的多条消息共享相同的 `run_id + step_id`
2. step 内部的 assistant/tool 往返由相同 step 标识绑定

### 8.3 Summary merge 时的 anchor 生成

V1 只要求“高置信度时才写 anchor”。

建议规则：
1. 若某个 `decision / constraint / artifact` 明显主要来源于本次压缩输入中的单一 step，则写入该 step 的 `source_anchor`
2. 若来源跨多个 step 或无法确定，则不写 `source_anchor`

即：
1. anchor 是可选增强，不是强制字段
2. 优先保证正确性，不追求覆盖率

## 9. Tool 设计

### 9.1 Tool 名称

建议：
1. `history_recall`

### 9.2 Tool 定位

职责：
1. 按 `run_id + step_id` 召回该 step 下的原始消息
2. 为模型提供可控、可解释的历史回看入口

不负责：
1. 自动决定何时触发
2. 重新生成 summary
3. 修改 memory 数据

### 9.3 输入结构

V1 建议支持如下输入：

```json
{
  "run_id": "runtime_cli_29837942",
  "step_id": "7",
  "include_neighbor_steps": false
}
```

可选增强：
1. 允许直接传：

```json
{
  "source_anchor": {
    "run_id": "runtime_cli_29837942",
    "step_id": "7"
  }
}
```

### 9.4 输出结构

建议返回：

```json
{
  "success": true,
  "run_id": "runtime_cli_29837942",
  "step_id": "7",
  "messages": [
    {
      "message_id": 128,
      "role": "assistant",
      "content": "...",
      "tool_call_id": "",
      "created_at": "2026-04-18 12:00:00"
    }
  ]
}
```

说明：
1. 虽然 V1 anchor 不写 `message_id`，但 tool 返回结果可以带 `message_id`
2. 这有利于后续扩展更细粒度回溯

### 9.5 默认粒度

V1 默认粒度：
1. `step`

理由：
1. 当前问题的关键是精确回看“某一步发生了什么”
2. `dialog turn` 粒度过粗
3. `message` 粒度过细，不适合作为默认回溯单元

## 10. 查询与索引建议

### 10.1 查询模式

`history_recall` 的核心查询是：

```sql
SELECT id, role, content, tool_call_id, tool_calls_json, created_at
FROM messages
WHERE conversation_id = ?
  AND run_id = ?
  AND step_id = ?
ORDER BY id ASC
```

### 10.2 索引建议

若后续查询量上升，建议增加索引：

```sql
CREATE INDEX IF NOT EXISTS idx_messages_conv_run_step
ON messages(conversation_id, run_id, step_id, id);
```

V1 可选：
1. 若数据量尚小，可先不加
2. 但设计上应预留该索引建议

## 11. 兼容策略

### 11.1 历史消息兼容

历史消息没有 `run_id / step_id` 时：
1. 不影响现有功能
2. `history_recall` 对该类数据无法做 step 精确回溯
3. 返回时可提示：
   - `reason = "missing_step_metadata"`

### 11.2 历史 summary 兼容

历史 `summary_json` 没有 `source_anchor` 时：
1. 按“无 anchor”处理
2. 不需要迁移旧数据

### 11.3 Tool 兼容

`history_recall` 在无法定位时：
1. 不应抛异常中断主流程
2. 应返回结构化失败结果，便于模型决定下一步是否改用模糊搜索或继续询问用户

## 12. 风险与缓解

风险 1：只记录 `run_id + step_id`，无法精确定位到单条消息。  
缓解：
1. V1 明确目标是 step 级回溯
2. tool 返回结果中保留 `message_id`
3. 后续如需更细粒度，可在 V2 扩展 `primary_message_id`

风险 2：并非所有结构化对象都能可靠映射到单一 step。  
缓解：
1. `source_anchor` 设计为可选
2. 仅在高置信度时写入

风险 3：消息写入路径较多，容易漏接 `run_id / step_id`。  
缓解：
1. 统一收口 `append_message(...)` 参数
2. 增加测试验证 assistant/tool 主要路径是否已写入

风险 4：历史数据没有 step 元数据，回溯体验不一致。  
缓解：
1. 明确 V1 仅保证新数据链路完整
2. 对旧数据返回可解释的失败原因

## 13. 测试计划

建议新增或调整以下回归：

1. `sqlite_memory_store_should_persist_run_id_and_step_id`
2. `history_recall_tool_should_return_messages_for_run_and_step`
3. `history_recall_tool_should_return_structured_failure_when_step_metadata_missing`
4. `summary_anchor_should_embed_run_id_and_step_id_for_decision`
5. `summary_anchor_should_embed_run_id_and_step_id_for_artifact`
6. `summary_anchor_should_skip_when_source_step_is_ambiguous`
7. `runtime_message_write_paths_should_forward_run_id_and_step_id`

## 14. 落地步骤

1. 为 `messages` 表新增 `run_id / step_id` 字段。
2. 扩展 `append_message(...)` 接口与 SQLite 落库逻辑。
3. 在 runtime 消息写入链路中接入当前 `run_id + step_id`。
4. 新增 `history_recall` tool。
5. 在 summary merge 路径中为 `decision / constraint / artifact` 增加可选 `source_anchor`。
6. 补充测试。
7. 更新相关 reference 文档。

## 15. 预期收益

1. 结构化摘要第一次具备稳定的执行来源指针。
2. 模型第一次具备显式、可控的 step 级历史回溯能力。
3. 后续若继续扩展 `primary_message_id`、自动回溯或更复杂证据链，将有稳定基础设施可复用。
