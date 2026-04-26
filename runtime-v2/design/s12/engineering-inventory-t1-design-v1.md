# S12-T1 Engineering 现状清单（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S12-T1`

## 1. 当前工程化组成

### Observability

1. `app/observability/events.py`
2. `app/observability/schema.py`
3. `app/observability/store.py`
4. `app/observability/postmortem.py`
5. `app/observability/README.md`

### Eval / Artifacts

1. `observability-evals/`
2. postmortem 输出
3. judgement 输出

### Tests

当前测试主要覆盖：

1. runtime
2. todo
3. eval
4. memory
5. skills
6. subagent
7. observability

### Design Docs

1. `doc/design/*`
2. `runtime-v2/design/*`

## 2. 当前已有正式结构

1. `EventRecord`
2. `EVENT_TYPES`
3. postmortem 生成链路
4. 多个模块级与集成级测试

## 3. 当前问题

1. v1 设计文档与 runtime-v2 文档还并存
2. 事件模型虽然已有，但还不是 v2 正式协议
3. 测试围绕现有实现展开，尚未围绕 v2 状态机重组

## 4. 对后续的直接输入

这份清单直接服务：

1. `S12-T2` 正式事件模型
2. `S12-T3` 证据链模型
3. `S12-T5` 测试分层方案
4. `S12-T6` 文档同步机制
