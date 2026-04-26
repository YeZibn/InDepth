# S8-T1 Runtime Memory 链路清单（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S8-T1`

## 1. 当前主要文件

1. `app/core/memory/sqlite_memory_store.py`
2. `app/core/memory/context_compressor.py`
3. `app/core/runtime/agent_runtime.py`

## 2. 当前职责

当前 runtime memory 主要承载：

1. 消息持久化
2. 历史摘要
3. 压缩结果
4. recent messages 恢复

## 3. 当前主要入口

从现有代码看，runtime memory 主要通过 `AgentRuntime` 直接驱动：

1. 在 run 过程中持续 `append_message`
2. 在恢复或新一轮执行前 `get_recent_messages`
3. 在上下文压力下做 compaction / summarize

## 4. 当前数据形态

当前主要数据形态包括：

1. `messages`
2. `summaries`
3. tool chain 摘要
4. 压缩后的 summary prompt

## 5. 当前触发时机

目前主要触发点包括：

1. 用户输入进入 run 时
2. assistant 输出产生时
3. tool call 相关消息写入时
4. 上下文接近阈值时触发压缩

## 6. 与 v2 当前主干的关系

按目前已经收敛的 v2 设计，runtime memory 与新主干的关系应理解为：

1. 它不进入正式 `RunContext`
2. 它服务主链路上下文装配
3. 它与 `compression_state` 配合，但不等于 `compression_state`

## 7. 当前问题

当前最主要的问题有 4 个：

1. runtime memory 与 `messages` 深度耦合
2. 压缩策略和存储结构耦合在一起
3. 它既像基础设施，又承载了部分 runtime policy
4. 与 v2 极简 `RunContext` 的边界还未彻底拉开

## 8. 对后续的直接输入

这份清单直接服务：

1. `S8-T2` runtime memory 模型
2. `S8-T7` memory hook / injection 设计
3. `S7-T5` context budget 对接
4. `S4-T4` RunContext 与 message system 解耦

## 9. 本任务结论摘要

可以压缩成 5 句话：

1. runtime memory 当前主要保存消息、摘要和压缩结果
2. 它主要由 `AgentRuntime` 直接驱动
3. 它服务上下文装配，但不应进入正式 `RunContext`
4. 它和 compression 紧密相关，但不应等同于 compression state
5. v2 下一步需要把它从 runtime policy 中进一步拆开
