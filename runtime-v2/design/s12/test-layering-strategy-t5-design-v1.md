# S12-T5 测试分层方案（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S12-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版测试分层方案。

目标是：

1. 让测试围绕当前正式协议和状态机展开
2. 避免一开始就把验证压力全部压到大而全 e2e
3. 让协议、状态机、链路闭环都有清晰测试层次

## 2. 正式结论

本任务最终结论如下：

1. 第一版测试按 3 个主层组织：
   - 协议层
   - 状态机层
   - 链路层
2. prompt 相关测试主要放在协议层
3. `step -> orchestrator -> state writeback` 是状态机层重点
4. 保留少量关键闭环链路测试
5. memory 相关测试作为单独子层横跨协议层和链路层

## 3. 第一版主测试层

## 3.1 协议层

这一层主要验证：

1. 数据结构
2. 接口契约
3. payload 结构
4. prompt contract

典型对象包括：

1. `StepResult`
2. `NodePatch`
3. `NodeExecutionDecision`
4. `RunContext`
5. `Handoff`
6. `VerificationResult`
7. `MemoryPayload`
8. `PreferencePayload`
9. tool envelope
10. event payload

## 3.2 状态机层

这一层主要验证：

1. 状态迁移
2. orchestrator 执行规则
3. graph 写回规则
4. finalize 回退规则

状态机层的核心对象是：

1. `step`
2. `orchestrator`
3. `RunContext`
4. `TaskGraphState`

## 3.3 链路层

这一层主要验证：

1. 主链路关键闭环
2. phase 间衔接
3. final verification 闭环
4. memory hooks 接入

它是少量关键流程测试，不是大规模全覆盖。

## 4. 协议层测试范围

第一版协议层建议重点覆盖：

1. `StepResult` schema
2. `RunContext` 极简结构
3. `Handoff` 结构
4. `VerificationResult` 结构
5. `MemoryPayload / PreferencePayload`
6. tool protocol
7. tool category
8. event record / event payload

## 5. Prompt 相关测试的位置

本任务明确规定：

1. prompt 相关测试主要放在协议层
2. 不把 prompt contract 全部推到 e2e 去测

第一版应重点验证：

1. `handoff` prompt contract
2. prompt / state boundary
3. `finalize_return_input` 注入边界
4. memory / preference recall 注入边界

## 6. 状态机层重点

本任务明确规定：

1. `step -> orchestrator -> state writeback` 是状态机层重点

第一版建议重点验证：

1. `switch` 导致：
   - 当前 node -> `paused`
   - `active_node_id` 切换
   - 目标 node -> `running`
2. `abandon` 导致：
   - 当前 node -> `abandoned`
   - 后续承接目标存在
3. `followup_nodes` 落图规则
4. `active_node_id` 必须对应 `running`
5. `finalize -> verification fail -> execute` 回退闭环

## 7. 链路层重点

本任务明确规定：

1. 链路层保留少量关键闭环测试
2. 不追求一开始就全靠超大 end-to-end 测试

第一版建议至少保留以下链路测试：

1. `execute -> finalize -> verification pass -> RunOutcome`
2. `execute -> finalize -> verification fail -> execute`
3. `run-start -> long-term memory recall -> prompt injection`
4. `finalize-closeout -> memory write / preference write`

## 8. Memory 测试子层

memory 相关测试建议作为独立子层横跨协议层和链路层。

### 协议侧

重点验证：

1. `LongTermMemoryItem`
2. `MemoryPayload`
3. `PreferencePayload`
4. runtime memory processor 输入输出

### 链路侧

重点验证：

1. 长期记忆 recall 只在 run 开始时发生一次
2. 用户偏好整页注入
3. system memory write 消费 `handoff.memory_payload`
4. user preference write 消费 `handoff.preference_payload`

## 9. 为什么不把一切都压到 E2E

本任务明确避免以下做法：

1. 所有验证都依赖大而全 runtime e2e

原因是：

1. 当前正式协议很多
2. 当前状态机规则很多
3. 如果没有协议层和状态机层测试
4. 后面很难定位问题是：
   - 接口错
   - 状态迁移错
   - 还是整链路错

## 10. 推荐测试骨架

可以用下面这张图理解：

```text
protocol tests
  -> schemas / payloads / prompt contracts

state-machine tests
  -> step / orchestrator / graph transitions

flow tests
  -> execute-finalize-verification closeout

memory tests
  -> recall / write hooks / payloads
```

## 11. 对其他任务的直接输入

`S12-T5` 直接服务：

1. `S12-T7` test scaffolding skeleton
2. `S3-T5` step / orchestrator 实现
3. `S11-T6` finalize pipeline 实现
4. `S8-T8` memory interfaces 实现

同时它直接依赖：

1. `S3-T5` step / orchestrator 契约
2. `S4-T4` 极简 RunContext
3. `S11-T3~T7`
4. `S8-T2~T8`

## 12. 本任务结论摘要

可以压缩成 5 句话：

1. 第一版测试按协议层、状态机层、链路层组织
2. prompt contract 主要在协议层测
3. `step -> orchestrator -> state writeback` 是状态机层重点
4. 保留少量关键闭环链路测试
5. memory 相关测试作为独立子层横跨协议和链路
