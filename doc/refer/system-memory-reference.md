# InDepth System 经验记忆参考

更新时间：2026-04-20

返回总览：
- [Memory 总览](./memory-reference.md)

## 1. 模块定位

System Memory 负责“跨任务经验沉淀与召回”。

它不保存完整会话，也不承担用户偏好管理，而是把任务结束后值得复用的经验收敛成轻量卡片，供未来类似任务在开始阶段参考。

适合放进这里的内容：
- 可跨任务复用的经验
- 稳定的做法、避坑点、风险提示
- 来自最终交付与收尾阶段的高价值结论

不适合放进这里的内容：
- 当前 run 的完整消息历史
- 运行中尚未收敛的中间判断
- 用户个人长期偏好

## 2. 关键文件

- `app/core/memory/system_memory_store.py`
- `app/core/runtime/system_memory_lifecycle.py`
- `app/core/memory/recall_service.py`
- `app/eval/verification_handoff_service.py`

## 3. 存储模型

默认数据库：

- `db/system_memory.db`

主表：

1. `memory_card`
   - 当前使用轻量 schema
   - 字段固定为：
     - `id`
     - `title`
     - `recall_hint`
     - `content`
     - `status`
     - `updated_at`
     - `expire_at`

事件表：

1. `memory_trigger_event`
2. `memory_retrieval_event`
3. `memory_decision_event`

说明：
- 主卡表已经简化，只保留召回和治理真正需要的字段。
- 三张事件表继续保留，用于观测、指标和 postmortem。
- `SystemMemoryStore` 内置了旧版 `memory_card` 到轻量 schema 的自动迁移。

## 4. 生命周期

### 4.1 任务开始：recall

入口：

- `inject_system_memory_recall(...)`

触发时机：

- `AgentRuntime.run()` 早期，在首轮主请求前

当前流程：

1. 基于 `user_input` 构造 recall query
2. 从 `memory_card` 读取候选卡
3. 可选地用 LLM 做 rerank
4. 只把少量高相关卡以轻量 block 注入 prompt
5. 注入内容默认只包含：
   - `memory_id`
   - `recall_hint`
6. 如果后续需要完整细节，再通过 `get_memory_card_by_id` 拉全卡

### 4.2 任务结束：persist

入口：

- `finalize_task_memory(...)`

触发时机：

- Runtime 结束后的 finalization 阶段

当前流程：

1. Runtime 先完成 `finalizing(answer)`
2. 再完成 `finalizing(handoff)`
3. verification 与 memory 都消费同一份 `verification_handoff`
4. memory 只读取 `verification_handoff.memory_seed`
5. 若 `memory_seed.title / recall_hint / content` 全空，则不写卡
6. 否则 upsert 一张正式 `memory_card`

关键约束：

- 不再有“运行中候补记忆卡片”的默认主链路写入
- 正式 memory 只能在任务结束后由 handoff 派生
- handoff 是 verification 与 memory 的共同事实源

## 5. handoff 与 memory 的关系

当前系统里，handoff 不再只是给 verifier 的附加材料。

它现在承担两件事：

1. 给 Eval 提供结构化交接事实
2. 给 System Memory 提供 `memory_seed`

当前 handoff 中和 memory 最相关的部分是：

```json
{
  "memory_seed": {
    "title": "string",
    "recall_hint": "string",
    "content": "string"
  }
}
```

卡片字段映射关系：

1. `memory_card.title <- verification_handoff.memory_seed.title`
2. `memory_card.recall_hint <- verification_handoff.memory_seed.recall_hint`
3. `memory_card.content <- verification_handoff.memory_seed.content`
4. `memory_card.status <- active`
5. `memory_card.expire_at <- 默认 180 天后`

## 6. 检索方式

`SystemMemoryStore.search_cards(...)` 当前是轻量关键词检索。

当前实现特点：

1. 检索字段覆盖：
   - `title`
   - `recall_hint`
   - `content`
2. 默认只返回：
   - `status = active`
   - 未过期卡
3. 结果按 `updated_at DESC` 取候选，再结合简单分数排序
4. Runtime recall 可选叠加 LLM rerank，以减少误召回

这意味着：

- 现在还没有向量检索
- 现在也不是旧版的重字段结构检索
- `recall_hint` 是轻注入的主语义入口，`content` 用于补充召回面

## 7. 和 Runtime Memory 的区别

两者容易混淆，但职责完全不同：

1. Runtime Memory
   - 服务当前任务继续执行
   - 保存消息、摘要、压缩结果

2. System Memory
   - 服务未来任务复用经验
   - 保存轻量经验卡

一个简单判断方法：

- 随当前 run 结束即可折叠的内容，属于 Runtime Memory
- 未来相似任务仍值得召回的内容，属于 System Memory

## 8. 观测

System Memory 相关事件主要是：

- `memory_triggered`
- `memory_retrieved`
- `memory_decision_made`

这些事件用于：

1. 记录 recall 与持久化链路
2. 支撑指标计算
3. 为 postmortem 提供可追溯事实

## 9. 当前推荐理解

可以把 System Memory 理解成一条很窄但很稳定的链路：

`run start recall -> task execution -> finalizing(answer) -> finalizing(handoff) -> verification -> memory persist`

重点不是“多存字段”，而是：

1. 只在任务结束后沉淀
2. 只沉淀已经收敛的经验
3. 让 recall 成本保持轻量
4. 为以后接向量检索预留干净的卡片载体
