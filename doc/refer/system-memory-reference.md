# InDepth System 经验记忆参考

更新时间：2026-04-19

返回总览：
- [Memory 总览](./memory-reference.md)

## 1. 模块定位

System Memory 负责“跨任务经验沉淀与召回”。

它的目标不是保存完整会话，而是把值得复用的任务经验沉淀成结构化 card，在后续类似任务开始时轻量召回。

适合放进这里的内容：
- 某类任务的成功经验
- 常见失败模式与规避方式
- 可复用的处理路径
- 值得长期保留的 runtime postmortem 事实

不适合放进这里的内容：
- 当前 task 的完整消息历史
- 用户个人偏好

## 2. 关键文件

- `app/core/memory/system_memory_store.py`
- `app/core/runtime/system_memory_lifecycle.py`
- `app/core/memory/recall_service.py`
- `app/core/memory/memory_metadata_service.py`

## 3. 存储

默认数据库：

- `db/system_memory.db`

核心表：

1. `memory_card`
   - 主体经验卡
   - 关键字段包括：
     - `id`
     - `title`
     - `recall_hint`
     - `memory_type`
     - `domain`
     - `scenario_stage`
     - `status`
     - `expire_at`
     - `payload_json`

System Memory 的主读写单位是“card”，不是“message”。

## 4. 两个核心阶段

### 4.1 finalize：任务结束后沉淀经验

入口：

- `finalize_task_memory(...)`

触发时机：

- task 结束收尾阶段

它会做的事：

1. 生成经验卡基础内容
2. 为卡片生成：
   - `title`
   - `recall_hint`
3. 调用 `SystemMemoryStore.upsert_card(...)`
4. 发出 memory 事件三连：
   - `memory_triggered`
   - `memory_retrieved`
   - `memory_decision_made`

### 4.2 recall：新任务开始时召回经验

入口：

- `inject_system_memory_recall(...)`

触发时机：

- `AgentRuntime.run()` 启动早期

它会做的事：

1. 基于当前 `user_input` 构造 recall query
2. 从 `memory_card` 中取候选卡
3. 可选地用 LLM rerank
4. 选出少量高相关 card
5. 渲染成轻量 recall block
6. 注入 system prompt

## 5. 数据语义

一张 system memory card 本质上是一条“经验记录”。

当前实现里比较重要的语义字段：

1. `title`
   - 经验卡标题
2. `recall_hint`
   - 给 runtime 注入时真正使用的高信号提示
3. `scenario`
   - 经验适用场景
4. `problem_pattern`
   - 经验对应的问题模式
5. `solution`
   - 推荐路径
6. `constraints`
   - 适用条件与依赖
7. `anti_pattern`
   - 不适用条件或风险信号
8. `lifecycle`
   - `status / expire_at / last_reviewed_at`

## 6. 检索方式

当前 `SystemMemoryStore.search_cards(...)` 的检索是轻量的。

重点：
- title 驱动
- 只搜 active card
- 过期卡默认不参与

如果开启 reranker，`inject_system_memory_recall(...)` 会进一步筛选。

最终注入 prompt 的不是完整 card，而是：
- `memory_id`
- `recall_hint`

这是为了控制注入成本，避免 system memory 自己把上下文撑爆。

## 7. 和 Runtime Memory 的关系

它们很容易混，但语义完全不同：

1. Runtime Memory
   - 保存当前 task 的历史上下文
   - 为“当前任务继续跑”服务

2. System Memory
   - 保存跨任务经验卡
   - 为“未来类似任务更快复用”服务

一个简单判断方法：

如果内容随着当前 task 结束就可以被折叠掉，它更像 Runtime Memory。

如果内容值得在未来别的 task 中再次召回，它更像 System Memory。

## 8. 观测

System Memory 相关事件主要是：

- `memory_triggered`
- `memory_retrieved`
- `memory_decision_made`

这些事件同时落：
- JSONL
- SQLite memory event store

详情见：
- [Observability 参考](./observability-reference.md)

## 9. 你应该用它来回答什么问题

System Memory 最适合回答：

- 为什么这个新任务一开始就注入了某些经验
- 某条经验卡是怎么生成的
- 某条经验为什么会被召回
- 某张 card 现在是否 active / 是否过期

如果你的问题是下面这些，就不该优先看这里：

- “当前上下文为什么被压缩”
  - 去看 [Runtime 会话记忆](./runtime-memory-reference.md)
- “用户为什么总想要中文、简洁回答”
  - 去看 [User Preference 记忆](./user-preference-reference.md)
