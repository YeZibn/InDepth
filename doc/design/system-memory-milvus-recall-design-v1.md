# System Memory Milvus 向量召回设计方案（V1）

更新时间：2026-04-20  
状态：Implemented（V1 主链路已落地）

## 1. 背景

当前 System Memory 的 run-start recall 已具备如下基础能力：
1. 任务开始时触发 recall。
2. 召回结果以轻注入形式进入 prompt，仅注入 `memory_id + recall_hint`。
3. 完整记忆按需通过 `get_memory_card_by_id` 拉取。
4. 观测链路已具备 `memory_triggered / memory_retrieved / memory_decision_made` 事件闭环。

但当前实现仍存在几个问题：
1. 首轮候选召回并未真正使用 `user_input` 做高质量检索。
2. 当前候选池主要依赖 SQLite 规则匹配，语义召回能力不足。
3. 当前存在 LLM rerank 路径，链路复杂，且不利于评估“召回本身”的真实效果。
4. 向量索引尚未与 `memory_card` 主表形成明确的双存储边界。

## 2. 目标

本方案目标：
1. run-start recall 仅使用 `user_input` 作为 query。
2. 为每条 memory card 生成 `title + recall_hint` 的向量，并存入 Milvus。
3. recall 时使用 `user_input embedding` 与 Milvus 中 memory embedding 直接做相似度检索。
4. 检索结果仅按向量相似度排序，不再使用 LLM rerank。
5. 召回结果经 SQLite 回表校验，仅保留 `active` 且未过期的记忆。
6. 若回表发现记忆已失效，则从 Milvus 删除对应向量索引。
7. 维持现有轻注入设计与 observability 事件闭环。

## 3. 非目标

本次不做：
1. 不改变 Runtime memory（`runtime_memory.db`）结构与压缩逻辑。
2. 不改变 memory card 主表的业务主键与核心字段语义。
3. 不引入规则召回与向量召回的混合排序。
4. 不保留 LLM 对 recall 结果的二次重排。
5. 不扩展 run 中自动二次召回。

## 4. 核心决策

### 4.1 Query 来源

默认决策：
1. recall query 仅来源于 `user_input`。
2. 不使用 `task_id`。
3. 不使用 `stage`。
4. 不使用 runtime 中间状态或历史 step 文本。

原因：
1. 避免流程命名噪音污染召回。
2. 保证相同 `user_input` 在不同任务上下文中的召回结果一致。
3. 让召回质量评估更清晰。

### 4.2 Embedding 文本

每条 memory card 的 embedding 文本固定为：

```text
title: {title}
recall_hint: {recall_hint}
```

默认决策：
1. 不使用完整 `content` 生成 embedding。
2. 不拼入 `task_id/run_id/时间戳/任务总结` 等流程噪音。
3. 缺失 `recall_hint` 时，仍沿用当前 fallback 逻辑先补齐 `recall_hint`，再生成 embedding。

原因：
1. `title` 提供主题辨识。
2. `recall_hint` 提供适用条件与建议动作。
3. 长文本 `content` 容易引入噪音，降低召回稳定性。

### 4.2.1 Embedding Provider

V1 已支持 embedding 通道与主 LLM 通道分离配置。

默认约定：
1. 主 LLM 继续使用 `LLM_MODEL_ID / LLM_API_KEY / LLM_BASE_URL`。
2. embedding 通道优先使用：
   - `LLM_EMBEDDING_MODEL_ID`
   - `LLM_EMBEDDING_API_KEY`
   - `LLM_EMBEDDING_BASE_URL`
3. 若 embedding 独立配置缺失，才回退到主 LLM 的 `api_key/base_url`。

这样做的原因：
1. embedding 服务与聊天模型常常来自不同 provider。
2. 便于接入 SiliconFlow、OpenAI、Azure OpenAI 等独立 embedding 通道。
3. 避免主模型 provider 不支持 `/embeddings` 时阻塞 recall。

### 4.3 存储分层

默认决策：
1. `SQLite` 是 system memory 的主事实源。
2. `Milvus` 仅承担向量索引职责。
3. 两者通过 `memory_id` 绑定。

含义：
1. `memory_card` 的正式字段仍以 SQLite 为准。
2. Milvus 中的向量索引是可重建副本，不是业务真源。
3. recall 结果在进入 prompt 前，必须回 SQLite 做最终真值校验。

### 4.4 排序与过滤

默认决策：
1. 仅使用向量相似度排序。
2. `top5` 为最终注入上限。
3. 设置 `min_score` 阈值；低于阈值则不采用。
4. 第一版移除 LLM rerank。

原因：
1. 链路更短，可解释性更强。
2. 便于单独评估 Milvus 向量召回效果。
3. 先把“候选召回正确性”做好，再决定未来是否需要重排。

## 5. 存储设计

### 5.1 SQLite 主表

沿用现有 `memory_card` 主表：
1. `id`
2. `title`
3. `recall_hint`
4. `content`
5. `status`
6. `updated_at`
7. `expire_at`

约束：
1. `memory_card.id` 是唯一业务主键。
2. recall 阶段最终是否可用，以 SQLite 中的 `status/expire_at` 为准。

### 5.2 Milvus Collection

建议新增 collection：`system_memory_card_embedding`

建议字段：
1. `memory_id`
2. `embedding`
3. `vector_text`
4. `vector_model`
5. `updated_at_ts`

字段职责：
1. `memory_id`
   - 与 SQLite `memory_card.id` 一一绑定。
2. `embedding`
   - `title + recall_hint` 生成的向量。
3. `vector_text`
   - 参与 embedding 的原始文本，便于调试与重建。
4. `vector_model`
   - 当前 embedding 模型标识，用于重建与兼容升级。
5. `updated_at_ts`
   - 向量更新时间戳，用于排查同步状态。

说明：
1. Milvus 中不存完整 `content`。
2. Milvus 中可不作为业务过滤真源。
3. 是否同步写入 `status/expire_at` metadata 不是 V1 必需项。
4. `memory_id` 作为字符串主键时，collection schema 必须显式提供 `max_length`。

### 5.2.1 当前已验证的本地配置

当前本地联调已验证的配置为：
1. embedding model：`Qwen/Qwen3-Embedding-8B`
2. embedding provider：`https://api.siliconflow.cn/v1`
3. Milvus URI：`http://127.0.0.1:19530`
4. embedding dimension：`4096`

注意：
1. `Qwen/Qwen3-Embedding-8B` 实测返回向量维度为 `4096`。
2. 若 `SYSTEM_MEMORY_EMBEDDING_DIM` 配置与真实返回维度不一致，Milvus 建索引会失败或后续 upsert/search 会报错。

## 6. 写入与更新流程

### 6.1 Upsert 流程

当 memory card 在 SQLite 中完成 upsert 后：
1. 读取标准化后的 `title` 与 `recall_hint`。
2. 生成 `vector_text`。
3. 调用 embedding 模型生成向量。
4. 以 `memory_id` 为主键 upsert 到 Milvus。

逻辑顺序：

`memory_card upsert(SQLite) -> build vector_text -> embed -> upsert vector(Milvus)`

约束：
1. SQLite upsert 成功后，Milvus upsert 失败不应回滚主流程。
2. Milvus upsert 失败需要记录日志或事件，以便后续补偿。
3. 同一 `memory_id` 的向量应允许覆盖更新。
4. 若 embedding provider 不可用，主流程仍应只写 SQLite，不得阻塞任务结束。

### 6.2 何时重建向量

以下情况应重建对应向量：
1. 新增 memory card。
2. `title` 变化。
3. `recall_hint` 变化。
4. embedding 模型版本变化，需要批量重建。

以下情况不要求立即重建：
1. `content` 变化但 `title/recall_hint` 未变化。
2. 仅 `updated_at` 变化。

## 7. Recall 流程

### 7.1 总体流程

run-start recall 统一改为：

`user_input -> query embedding -> Milvus search -> SQLite 回表 -> 失效清理 -> min_score 过滤 -> top5 -> 轻注入`

### 7.2 分步说明

1. 触发 recall
   - runtime 在任务开始阶段触发 system memory recall。

2. 生成 query embedding
   - 使用原始 `user_input` 直接生成 query 向量。
   - query text 不再做 token 提取或规则扩写。

3. Milvus 检索
   - 对 `system_memory_card_embedding` 做向量搜索。
   - 建议先取 `topN` 候选，默认可为 `10` 或 `20`。

4. SQLite 回表
   - 用 `memory_id` 回 SQLite 查询正式 `memory_card`。

5. 失效判断
   - 若 SQLite 中不存在该卡，判定为失效。
   - 若 `status != active`，判定为失效。
   - 若 `expire_at` 已过期，判定为失效。

6. 失效清理
   - 对失效 `memory_id` 执行 Milvus 删除。
   - 删除失败不阻塞本次主流程。

7. 相似度过滤
   - 仅保留 `score >= min_score` 的有效卡片。

8. Top-K 裁剪
   - 对有效卡片按相似度降序取前 `5` 条。

9. 轻注入
   - 仅向 prompt 注入 `memory_id + recall_hint`。

10. 按需拉整卡
   - 若执行中判断某条记忆关键，仍通过 `get_memory_card_by_id` 拉取完整内容。

### 7.3 Recall 未命中策略

若发生以下任一情况：
1. Milvus 查询为空。
2. 候选全部低于 `min_score`。
3. 候选回表后全部失效。

则：
1. 不注入任何 system memory。
2. 不阻塞主流程。
3. 仍记录 recall 相关决策事件。

## 8. 失效淘汰策略

### 8.1 失效定义

在 recall 回表阶段，满足以下任一条件即视为失效记忆：
1. `memory_id` 在 SQLite 中不存在。
2. `status != active`。
3. `expire_at` 早于当前日期。

### 8.2 淘汰动作

默认动作：
1. 从 Milvus 删除对应 `memory_id` 的向量。
2. 本次 recall 不返回该条记忆。

### 8.3 失败容错

删除失败时：
1. 不影响本次用户任务主流程。
2. 不影响其他有效记忆继续返回。
3. 需要记录日志或事件，便于后续补偿与排查。

### 8.4 为什么采用“读时淘汰”

原因：
1. 能借真实访问流量逐步清理脏索引。
2. 不要求 V1 先构建复杂的后台治理任务。
3. 与 SQLite 真值回表天然同路径，逻辑简单。

### 8.5 后续可选增强

后续可选增加离线清理任务：
1. 周期扫描 SQLite 中已归档、已过期或已删除的卡片。
2. 批量删除 Milvus 中对应向量。
3. 与 run-start 的读时淘汰形成双保险。

该项不属于 V1 必做范围。

## 9. 对现有链路的改造要求

### 9.1 移除 LLM rerank

V1 默认移除现有 recall 中的 LLM rerank 逻辑。

具体含义：
1. 不再让 LLM 基于候选 `title` 做语义重排。
2. 最终结果完全由向量相似度分数决定。
3. `enable_memory_recall_reranker` 相关逻辑应停止参与 recall 主链路。

原因：
1. 避免“向量召回 + LLM 重排”混合后难以评估效果来源。
2. 降低 recall 时延与成本。
3. 让召回行为更接近“单一排序事实源”。

### 9.2 保留轻注入

V1 保留当前轻注入格式：
1. 每条仅注入 `memory_id`
2. 每条附带 `recall_hint`
3. 不直接注入完整 `content`

原因：
1. 控制 prompt token 成本。
2. 降低错误记忆过度干扰主任务的风险。
3. 继续支持“按 id 拉整卡”的渐进式使用模式。

## 10. 模块分层建议

### 10.1 SQLite Store

建议继续由 `SystemMemoryStore` 负责：
1. `memory_card` 的 CRUD。
2. `get_card`。
3. active/expire 校验。

### 10.2 Milvus Vector Store

建议新增独立的向量索引存储抽象，例如：
1. `SystemMemoryVectorStore`
2. 或 `MilvusMemoryIndexStore`

建议职责：
1. `upsert_memory_vector(memory_id, vector_text, embedding, model)`
2. `search_memory_vectors(query_embedding, top_k)`
3. `delete_memory_vector(memory_id)`

说明：
1. Runtime 不应直接耦合 Milvus SDK 细节。
2. recall 生命周期模块只依赖抽象接口，而不感知底层实现。

### 10.3 Recall Orchestrator

建议由 recall 生命周期模块统一编排：
1. 生成 query embedding。
2. 调用 Milvus 检索。
3. 回 SQLite 校验。
4. 处理失效淘汰。
5. 执行 min_score / top5 策略。
6. 渲染轻注入 block。

## 11. 配置建议

建议新增配置项：
1. `ENABLE_SYSTEM_MEMORY_VECTOR_RECALL`
2. `SYSTEM_MEMORY_VECTOR_TOP_N`
3. `SYSTEM_MEMORY_RECALL_TOP_K`
4. `SYSTEM_MEMORY_RECALL_MIN_SCORE`
5. `SYSTEM_MEMORY_EMBEDDING_MODEL`
6. `SYSTEM_MEMORY_MILVUS_COLLECTION`
7. `LLM_EMBEDDING_API_KEY`
8. `LLM_EMBEDDING_BASE_URL`

默认建议值：
1. `ENABLE_SYSTEM_MEMORY_VECTOR_RECALL = true`
2. `SYSTEM_MEMORY_VECTOR_TOP_N = 10`
3. `SYSTEM_MEMORY_RECALL_TOP_K = 5`
4. `SYSTEM_MEMORY_RECALL_MIN_SCORE = 0.65`
5. `SYSTEM_MEMORY_EMBEDDING_DIM = 4096`（若使用 `Qwen/Qwen3-Embedding-8B`）

说明：
1. `topN` 用于 Milvus 初筛。
2. `topK` 用于最终注入上限。
3. `min_score` 需要在真实样本上调优，不建议写死在逻辑代码中。
4. `LLM_EMBEDDING_*` 用于单独指定 embedding provider，避免与主 LLM 通道耦合。

## 12. Observability 要求

V1 仍需保留以下事件链路：
1. `memory_triggered`
2. `memory_retrieved`
3. `memory_decision_made`

建议新增/调整 payload：

### 12.1 `memory_triggered`

建议记录：
1. `source=runtime_start_recall`
2. `query_text=user_input`
3. `retrieval_mode=milvus_vector`
4. `top_n`
5. `top_k`
6. `min_score`

### 12.2 `memory_retrieved`

每条被最终采用的记忆建议记录：
1. `memory_id`
2. `score`
3. `source=runtime_start_recall`
4. `retrieval_mode=milvus_vector`

### 12.3 失效清理事件

建议对失效清理至少记录日志；如扩展事件，可记录：
1. `memory_id`
2. `reason=not_found|inactive|expired`
3. `cleanup=milvus_delete_attempted|milvus_delete_failed|milvus_delete_succeeded`

该扩展项可在 V1 实现中按复杂度决定是否落库。

### 12.4 `memory_decision_made`

建议记录：
1. `decision=accepted|skipped`
2. `reason=no_vector_match|below_min_score|all_invalid|recalled_n_cards`

## 13. 兼容性与迁移

### 13.1 对现有 SQLite 的兼容

本方案不要求重建现有 `memory_card` 主表。

仅需：
1. 对已有 active 记忆批量补建 Milvus 向量索引。
2. 新写入卡片自动同步到 Milvus。

### 13.2 对现有 recall 逻辑的兼容

现有规则检索与 LLM rerank 路径可在代码中保留为过渡实现，但不再作为默认主链路。

默认主链路应切换为：
1. vector recall
2. SQLite 回表校验
3. 轻注入

### 13.3 回退策略

若 Milvus 或 embedding 服务不可用：
1. recall 异常不得阻塞主任务。
2. 本轮可直接跳过 system memory 注入。
3. 需要记录错误日志或错误事件。

V1 默认不要求在异常时自动回退到规则召回。

## 13.4 当前实现状态

V1 当前已落地：
1. `title + recall_hint` 的向量文本构造。
2. 独立 embedding provider 配置。
3. Milvus collection 自动创建。
4. run-start recall 改为纯向量检索 + SQLite 回表校验。
5. 回表发现失效记忆时，尝试删除对应 Milvus 索引。
6. LLM rerank 已退出 recall 主链路。
7. 提供本地自检脚本 `scripts/check_system_memory_vector_recall.py`。

V1 尚未落地但建议后续补充：
1. 历史 `memory_card` 的批量 backfill 脚本。
2. 离线孤儿索引清理任务。

## 14. 验收口径

### 14.1 行为层

1. 相同 `user_input` 在相同库数据下，召回结果稳定。
2. recall 结果仅依赖 `user_input`，不依赖 `task_id/stage`。
3. 最终注入条数不超过 `5`。
4. 低于 `min_score` 的结果不进入 prompt。
5. 已失效记忆不会进入 prompt。

### 14.2 存储层

1. SQLite 中新增或更新 memory card 后，Milvus 中存在对应 `memory_id` 向量。
2. 回表发现失效记忆时，会尝试删除 Milvus 中对应索引。
3. Milvus 删除失败不会影响主流程完成。

### 14.3 架构层

1. `SQLite = source of truth`
2. `Milvus = vector index`
3. recall 主链路不再依赖 LLM rerank

## 15. 默认结论

V1 的最终默认方案为：
1. 仅用 `user_input` 生成 query embedding。
2. 仅用 `title + recall_hint` 生成 memory embedding。
3. SQLite 存主数据，Milvus 存向量索引。
4. 两边通过 `memory_id` 绑定。
5. recall 仅按向量相似度排序。
6. 仅保留 `top5` 且 `score >= min_score` 的有效卡片。
7. 回 SQLite 发现失效时，删除 Milvus 中对应向量。
8. 删除失败不阻塞主流程。
9. 保留轻注入，移除 LLM rerank。
