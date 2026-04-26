# S12-T7 Observability / Test Skeleton（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S12-T7`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 observability skeleton 与 test scaffolding skeleton。

目标是：

1. 为正式事件模型提供统一入口骨架
2. 为协议层、状态机层、链路层测试提供统一 scaffolding
3. 为 memory 相关测试预留独立 fixture

## 2. 正式结论

本任务最终结论如下：

1. `S12-T7` 同时覆盖 observability skeleton 与 test scaffolding skeleton
2. observability skeleton 围绕统一 `EventRecord` 与 `emit_event` 建立
3. test scaffolding 围绕协议夹具、状态机夹具、flow 夹具建立
4. memory 相关测试单独预留 fixture

## 3. Observability Skeleton

第一版 observability skeleton 的主入口建议围绕：

1. `EventRecord`
2. `emit_event`
3. `EventStore`

## 3.1 推荐最小方向

```ts
type EventRecord = {
  event_id: string;
  task_id: string;
  run_id: string;
  timestamp: string;
  event_type: string;
  actor?: string;
  status?: string;
  payload?: Record<string, unknown>;
};

interface EventEmitter {
  emit_event(event: EventRecord): void;
}

interface EventStore {
  append(event: EventRecord): void;
  list(run_id: string): EventRecord[];
}
```

## 3.2 第一版边界

observability skeleton 第一版明确不急于讨论：

1. 存储后端实现细节
2. 查询引擎
3. 可视化 UI

第一版只要求：

1. 正式事件可被发出
2. 正式事件可被收集
3. 正式事件可按 run 回放

## 4. Test Scaffolding Skeleton

本任务与 `S12-T5` 直接对齐，测试 scaffolding 围绕 3 层主结构建立：

1. 协议夹具
2. 状态机夹具
3. flow 夹具

## 4.1 协议夹具

协议夹具主要服务：

1. schema / payload 测试
2. prompt contract 测试
3. handoff / memory payload 测试

推荐最小方向：

```ts
interface ProtocolFixtures {
  make_step_result(): unknown;
  make_handoff(): unknown;
  make_verification_result(): unknown;
  make_event_record(): EventRecord;
}
```

## 4.2 状态机夹具

状态机夹具主要服务：

1. `step -> orchestrator -> state writeback`
2. node 状态迁移
3. finalize 回退 execute

推荐最小方向：

```ts
interface StateMachineFixtures {
  make_run_context(): unknown;
  make_task_graph_state(): unknown;
  make_active_node(): unknown;
}
```

## 4.3 Flow 夹具

flow 夹具主要服务：

1. execute -> finalize -> verification pass
2. execute -> finalize -> verification fail -> execute
3. closeout memory hooks

推荐最小方向：

```ts
interface FlowFixtures {
  make_finalize_handoff(): unknown;
  make_finalize_return_input(): unknown;
  make_run_outcome(): unknown;
}
```

## 5. Memory Fixtures

本任务明确规定：

1. memory 相关测试应单独预留 fixture

第一版建议至少保留：

1. `long_term_memory_fixture`
2. `user_preference_md_fixture`
3. `memory_payload_fixture`
4. `preference_payload_fixture`

## 5.1 推荐方向

```ts
interface MemoryFixtures {
  make_long_term_memory_item(): unknown;
  make_user_preference_markdown(): string;
  make_memory_payload(): unknown;
  make_preference_payload(): unknown;
}
```

## 6. 与当前主干的关系

本任务与当前主干直接对齐如下：

1. `EventRecord` 对齐 `S12-T2~T4`
2. protocol fixtures 对齐 `S1/S6/S11/S8`
3. state-machine fixtures 对齐 `S3/S4/S5`
4. flow fixtures 对齐 `S11 finalize pipeline`
5. memory fixtures 对齐 `S8`

## 7. 为什么要一起做

本任务明确采用 observability 与 test skeleton 一起收口，原因如下：

1. 当前很多测试都要围绕正式事件展开
2. 当前很多 flow 断言本身就需要事件锚点
3. 分开建立两套骨架会重复抽象

## 8. 第一版边界

第一版明确不建议：

1. 直接写重型 postmortem 框架
2. 直接上大而全 integration harness
3. 把所有 fixture 混成一个万能工厂

更合适的方式是：

1. 先有统一事件入口
2. 再有分层测试夹具
3. 最后按需要补具体验证器

## 9. 对其他任务的直接输入

`S12-T7` 直接服务：

1. `S3-T5` step / orchestrator 实现
2. `S8-T8` memory interfaces 实现
3. `S11-T7` verification skeleton 实现
4. `S12-T6` 文档与实现同步

同时它直接依赖：

1. `S12-T2` 正式事件模型
2. `S12-T4` event payload 规范
3. `S12-T5` 测试分层方案
4. `S8-T8` memory interfaces

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. `S12-T7` 同时建立 observability 和 test 两套 skeleton
2. observability skeleton 围绕统一 `EventRecord` 和 `emit_event`
3. 测试夹具按协议层、状态机层、flow 层组织
4. memory 测试单独预留 fixture
5. 这套骨架足以支撑后续实现与验证落地
