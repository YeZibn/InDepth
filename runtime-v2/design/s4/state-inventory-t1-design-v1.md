# S4-T1 状态字段总表（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S4-T1`

## 1. 当前主要状态域

当前项目的状态大致分成 5 类：

1. runtime 状态
2. todo / execution 状态
3. verification 状态
4. observability 事件状态
5. model / generation 配置状态

## 2. 关键状态对象

### Runtime

1. `last_runtime_state`
2. `last_stop_reason`
3. `_runtime_phase`
4. `_prepare_phase_completed`
5. `_prepare_phase_result`

### Todo

1. `TodoContext`
2. `TodoExecutionPhase`
3. `TodoBindingState`
4. `TodoSubtaskStatus`
5. `TodoSnapshot`

### Verification

1. `RunOutcome`
2. `VerifierResult`
3. `RunJudgement`

### Observability

1. `EventRecord`
2. `event_type`
3. `status`
4. `payload`

### Model

1. `GenerationConfig`
2. `ModelOutput`

## 3. 当前问题

1. runtime state 和 message state 还没完全分开
2. todo state 既是领域对象，又承担 runtime 控制语义
3. handoff / judgement / event payload 之间有重复字段

## 4. 对后续的直接输入

这份清单直接服务：

1. `S4-T2` 定义核心状态对象集合
2. `S4-T3` 输出统一状态图
3. `S4-T4` 定义状态分层规则
