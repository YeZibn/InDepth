# S12-T4 事件 Payload 最小规范（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S12-T4`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版事件记录的最小字段规范。

目标是：

1. 统一事件公共字段
2. 收敛关键事件的最小 payload
3. 避免事件再次膨胀成完整状态快照

## 2. 正式结论

本任务最终结论如下：

1. 所有事件都采用统一公共头
2. `payload` 只保留当前事件最关键的摘要字段
3. 事件不复制完整 `RunContext`
4. 事件不复制完整 `TaskGraphState`
5. 事件字段优先围绕定位、切换、结果 3 类信息

## 3. 公共字段

第一版所有事件建议至少包含：

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
```

## 4. 公共字段约束

### `event_id`

1. 事件唯一标识

### `task_id`

1. 标识所属任务

### `run_id`

1. 标识所属 run

### `timestamp`

1. 统一记录事件发生时间

### `event_type`

1. 使用正式事件名
2. 不在实现层继续发明语义重复的别名

### `actor`

第一版按需使用，例如：

1. `step`
2. `orchestrator`
3. `verifier`
4. `tool`

### `status`

第一版按需使用，例如：

1. `started`
2. `completed`
3. `failed`

## 5. Step 相关事件

## 5.1 `step_started`

建议 payload：

```ts
{
  phase: "execute";
  active_node_id: string;
}
```

## 5.2 `step_completed`

建议 payload：

```ts
{
  phase: "execute" | "finalize";
  active_node_id?: string;
  node_action?: string;
  next_phase?: string;
}
```

## 5.3 `step_failed`

建议 payload：

```ts
{
  phase: string;
  active_node_id?: string;
  reason: string;
}
```

## 6. Node / Graph 相关事件

## 6.1 `node_patch_applied`

建议 payload：

```ts
{
  node_id: string;
  artifact_count?: number;
  evidence_count?: number;
  note_count?: number;
}
```

## 6.2 `node_status_changed`

建议 payload：

```ts
{
  node_id: string;
  from_status?: string;
  to_status: string;
}
```

## 6.3 `active_node_switched`

建议 payload：

```ts
{
  from_node_id: string;
  to_node_id: string;
  reason: "switch" | "abandon";
}
```

## 6.4 `followup_nodes_appended`

建议 payload：

```ts
{
  source_node_id: string;
  node_ids: string[];
  count: number;
}
```

## 6.5 `node_abandoned`

建议 payload：

```ts
{
  node_id: string;
  target_node_id?: string;
}
```

## 7. Handoff 相关事件

## 7.1 `handoff_built`

建议 payload：

```ts
{
  handoff_id: string;
  graph_id: string;
  final_node_ids: string[];
}
```

## 7.2 `handoff_attached_to_outcome`

建议 payload：

```ts
{
  handoff_id: string;
  outcome_id?: string;
}
```

## 8. Final Verification 相关事件

## 8.1 `final_verification_started`

建议 payload：

```ts
{
  handoff_id: string;
}
```

## 8.2 `final_verification_passed`

建议 payload：

```ts
{
  handoff_id: string;
  summary: string;
}
```

## 8.3 `final_verification_failed`

建议 payload：

```ts
{
  handoff_id: string;
  summary: string;
  issue_count: number;
}
```

## 9. Finalize Return 相关事件

## 9.1 `finalize_return_prepared`

建议 payload：

```ts
{
  issue_count: number;
  summary: string;
}
```

## 9.2 `execute_returned_from_finalize`

建议 payload：

```ts
{
  issue_count: number;
}
```

## 10. Outcome 相关事件

## 10.1 `run_outcome_built`

建议 payload：

```ts
{
  result_status: string;
  stop_reason?: string;
}
```

## 10.2 `final_answer_committed`

建议 payload：

```ts
{
  answer_length?: number;
}
```

## 11. 第一版边界

第一版明确不建议把以下内容直接塞进 payload：

1. 完整 `RunContext`
2. 完整 `TaskGraphState`
3. 完整 `handoff` 正文
4. 完整 verifier 输出
5. 完整 tool 原始结果

更合适的做法是：

1. 事件中保留摘要
2. 大对象通过 ref 或独立正式状态读取

## 12. 对其他任务的直接输入

`S12-T4` 直接服务：

1. `S12-T3` runtime / closeout 事件对齐
2. `S11-T3` handoff 结构
3. `S11-T4` finalize 闭环
4. `S3-T5` StepResult 落地执行

同时它直接依赖：

1. `S12-T2` 正式事件模型
2. `S12-T3` closeout 事件补强

## 13. 本任务结论摘要

可以压缩成 5 句话：

1. 所有事件都应使用统一公共头
2. payload 只保留最小摘要字段
3. node / handoff / verification / outcome 都有各自最小 payload 模板
4. verification fail 回灌 execute 也应有专门 payload
5. 事件不应复制完整状态对象
