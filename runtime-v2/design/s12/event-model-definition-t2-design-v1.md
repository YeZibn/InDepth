# S12-T2 正式事件模型定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S12-T2`

## 1. 目标

本任务用于定义 `runtime-v2` 的正式事件模型。

目标是：

1. 让 v2 的事件体系围绕状态流和关键动作建立
2. 保留 phase、tool、verification 的主干事件
3. 正式保留 memory 相关事件，但不让其主导第一版事件模型

## 2. 正式结论

本任务最终结论如下：

1. v2 事件模型围绕“状态流 + 关键动作”设计
2. 事件模型分成两层：
   - 主干事件域
   - 扩展事件域
3. phase 事件保留显式边界：
   - `phase_started`
   - `phase_completed`
4. tool 事件保留三段式：
   - `tool_called`
   - `tool_succeeded`
   - `tool_failed`
5. verification 单独成组
6. memory 相关事件正式保留，但归入扩展事件域

## 3. 基础事件结构

第一版继续沿用统一事件记录结构：

1. `event_id`
2. `task_id`
3. `run_id`
4. `timestamp`
5. `actor`
6. `role`
7. `event_type`
8. `status`
9. `payload`

说明：

1. 事件是运行证据，不是完整状态镜像
2. 事件主要记录关键切换与关键动作
3. `RunOutcome` 不直接复制到每条事件里

## 4. 主干事件域

主干事件域是第一版必须稳定的事件集合。

## 4.1 Lifecycle Events

这一组用于标识一次 run 的生命周期边界。

建议保留：

1. `task_started`
2. `task_finished`
3. `task_judged`
4. `run_resumed`
5. `user_clarification_received`

作用：

1. 标记一轮运行的起点、终点、恢复点和最终判定

## 4.2 Phase Events

这一组用于标识 phase 切换边界。

建议保留：

1. `phase_started`
2. `phase_completed`

作用：

1. 明确 prepare / execute / finalize 的边界
2. 支撑状态机视角的回放与复盘

## 4.3 Tool Events

这一组用于记录工具调用主链路。

建议保留：

1. `tool_called`
2. `tool_succeeded`
3. `tool_failed`

作用：

1. 记录关键工具动作
2. 为状态流和证据链提供调用依据
3. 与 `S6-T2` 的统一 tool protocol 对齐

## 4.4 Verification Events

这一组用于记录验证和最终判定过程。

建议保留：

1. `verification_started`
2. `verification_passed`
3. `verification_failed`
4. `verification_skipped`

作用：

1. 清晰表达 verification 是否发生、是否通过
2. 为 `RunOutcome` 和 judgement 结果提供事件证据

## 5. 扩展事件域

扩展事件域是第一版正式保留、但不作为主干驱动中心的事件集合。

## 5.1 Memory Events

memory 事件正式保留，建议归为扩展事件域。

当前建议保留：

1. `memory_triggered`
2. `memory_retrieved`
3. `memory_decision_made`

作用：

1. 记录 system memory / runtime memory 相关召回与决策
2. 保留经验召回证据

结论：

1. memory 会记录
2. 但不作为第一版主干事件域的核心支柱

## 5.2 Preference Events

建议保留：

1. `user_preference_recall_succeeded`
2. `user_preference_recall_failed`
3. `user_preference_extract_started`
4. `user_preference_extract_succeeded`
5. `user_preference_extract_failed`
6. `user_preference_capture_succeeded`
7. `user_preference_capture_failed`

## 5.3 SubAgent Events

建议保留：

1. `subagent_created`
2. `subagent_started`
3. `subagent_finished`
4. `subagent_failed`

## 5.4 Search / Compression / 其他扩展事件

这一组暂时继续归为扩展域：

1. search guard 相关事件
2. clarification judge 相关事件
3. context compression 相关事件

## 6. 第一版建模原则

第一版事件模型明确采用以下原则：

1. 状态机事件优先于工具日志细节
2. 主干事件域优先稳定
3. 扩展事件域允许后续继续细化
4. memory 正式记录，但不抢占主干结构中心
5. `payload` 以摘要为主，不把所有运行数据塞入事件

## 7. 与其他结构的关系

`S12-T2` 直接对接：

1. `S3-T2` RuntimeOrchestrator
   事件由 orchestrator 和 phase 边界驱动
2. `S4-T2` 核心状态对象
   事件描述状态切换，但不替代状态对象
3. `S6-T2` tool protocol
   tool 事件直接承接统一工具信封
4. `S11-T2` RunOutcome
   verification 和 lifecycle 事件围绕 `RunOutcome` 收口
5. `S8-T2`
   memory 相关事件作为扩展事件域保留

## 8. 本任务结论摘要

可以压缩成 5 句话：

1. v2 事件模型分成主干事件域和扩展事件域
2. 主干事件域包括 lifecycle、phase、tool、verification
3. phase 保留 `phase_started / phase_completed`
4. tool 保留 `tool_called / tool_succeeded / tool_failed`
5. memory 相关事件正式保留，但归入扩展事件域
