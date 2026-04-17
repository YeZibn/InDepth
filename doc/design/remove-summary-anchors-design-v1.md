# Runtime Summary 移除 Anchors 设计稿（V1）

更新时间：2026-04-17  
状态：Implemented

## 1. 背景

当前 runtime summary 结构中包含 `anchors` 字段，用于记录摘要内容大致来源于哪些历史消息。单条 anchor 典型包含：
1. `msg_id`
2. `turn`
3. `role`
4. `reason`

这类信息更偏“来源索引”而非“续跑语义”。在当前实现里：
1. 后续对话续跑并不直接依赖 `anchors`
2. `render_summary_prompt(...)` 主要消费的是 `task_state / constraints / decisions / open_questions / artifacts`
3. `anchors` 会增加 `summary_json` 体积，并放大后续 merge 成本

因此，`anchors` 目前的投入产出比偏低，适合从 runtime summary 中移除。

## 2. 目标

本方案目标：
1. 从 runtime summary 中移除 `anchors` 字段
2. 保持现有续跑语义不受影响
3. 缩小 `summary_json` 体积，减少无效上下文负担
4. 尽量以最小改动完成落地

## 3. 非目标

本次不做：
1. 不重构 `task_state / constraints / decisions / artifacts / open_questions`
2. 不调整 compaction 触发策略
3. 不改造 observability 事件结构
4. 不引入新的来源追踪替代字段

## 4. 方案

### 4.1 数据结构调整

从 summary 结构中删除：
1. `anchors`

调整后保留：
1. `version`
2. `task_state`
3. `decisions`
4. `constraints`
5. `artifacts`
6. `open_questions`
7. `compression_meta`

### 4.2 规则压缩器调整

`ContextCompressor.merge_summary(...)`：
1. 不再生成 `anchors`
2. 不再合并历史 `anchors`

### 4.3 LLM 压缩器调整

`LLMContextCompressor`：
1. output schema 中删除 `anchors`
2. normalize 过程中不再处理 `anchors`

### 4.4 兼容策略

读取历史 summary 时：
1. 允许旧数据中仍然存在 `anchors`
2. 但新生成 summary 不再写入该字段

即：
1. 读兼容旧结构
2. 写统一新结构

## 5. 风险与判断

风险较低，原因是：
1. 当前主链路没有明显依赖 `anchors`
2. 注入 prompt 也不以 `anchors` 为主要输入
3. 它更像内部索引，而不是核心语义

需要确认的一点：
1. 是否有离线分析脚本或人工排查流程依赖 `anchors`

若没有，则可直接删除。

## 6. 落地步骤

1. 更新设计稿
2. 修改 `ContextCompressor`
3. 修改 `LLMContextCompressor`
4. 更新相关测试
5. 更新 memory/runtime 参考文档

## 7. 预期收益

落地后：
1. `summary_json` 结构更简洁
2. 压缩摘要更聚焦“续跑需要的信息”
3. 减少无直接业务价值的字段占用

一句话总结：
1. 移除 `anchors`，让 runtime summary 从“带来源索引的摘要”收敛为“面向续跑的最小语义摘要”。
