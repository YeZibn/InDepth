# S6-T5 Tool Call 进入状态流 / 事件流 / 证据链路径（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S6-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 tool call 如何进入：

1. 状态流
2. 事件流
3. 证据链

目标是：

1. 明确不同工具域的写回路径
2. 明确 tool result 不应直接散落写状态
3. 让 `tool protocol -> tool domain -> runtime 落账` 闭合

## 2. 正式结论

本任务最终结论如下：

1. 所有工具调用都先产出统一 tool envelope
2. 所有工具调用都进入事件流
3. `execution` 域结果默认先沉入当前 `NodePatch`
4. `task_graph` 域结果只能通过 orchestrator 落正式 graph state
5. `closeout` 域只允许在 `finalize` 中调用
6. 证据链统一采用“摘要 + ref”，不保留原始大结果正文

## 3. 总体路径

第一版推荐统一路径如下：

```text
tool call
  -> tool envelope
  -> tool events
  -> domain-specific interpretation
  -> state writeback
  -> evidence capture
```

含义是：

1. 先有统一协议
2. 再有统一事件
3. 然后按工具域决定如何写回状态
4. 最后进入证据链

## 4. 所有工具调用的共通规则

本任务明确规定：

1. 所有工具统一返回 `success / error / result / meta`
2. 所有工具调用都至少发出：
   - `tool_called`
   - `tool_succeeded` 或 `tool_failed`
3. 事件中的 payload 只保留摘要
4. 证据链只保留“摘要 + ref”
5. 不允许把完整原始工具结果同时塞入：
   - `RunContext`
   - 事件 payload
   - 证据链正文

## 5. execution 域路径

`execution` 域包括：

1. `bash`
2. `read_file`
3. `write_file`
4. `get_current_time`

第一版正式规则：

1. `execution` 域工具结果默认先沉入当前 `NodePatch`
2. 不直接写 run 级主状态
3. runtime 不对其做业务语义感知

推荐落点如下：

1. 产物类结果 -> `append_artifacts`
2. 观察类结果 -> `append_evidence`
3. 执行备注 -> `append_notes`

也就是说：

1. `execution` 工具结果优先服务当前 `active_node`
2. 它们先变成 node 级执行痕迹，再由 orchestrator 应用

## 6. task_graph 域路径

`task_graph` 域包括：

1. `plan_task_graph`
2. `update_node_status`
3. `get_next_node`
4. `reopen_node`
5. `append_followup_nodes`

第一版正式规则：

1. `task_graph` 域结果可以直接影响 graph 正式状态
2. 但不允许工具结果自己直接写入 `TaskGraphState`
3. 所有正式 graph 写回仍由 orchestrator 执行

推荐路径如下：

```text
task_graph tool result
  -> StepResult / graph mutation request
  -> orchestrator apply
  -> TaskGraphState updated
```

这意味着：

1. `task_graph` 域工具负责产出结构化状态变更结果
2. orchestrator 负责正式落账

## 7. closeout 域路径

`closeout` 域包括：

1. `build_handoff`
2. `run_final_verification`
3. `build_run_outcome`

第一版正式规则：

1. `closeout` 域只允许在 `finalize` 中调用
2. 不允许在 `execute` 中途调用
3. `closeout` 结果直接进入收尾闭环

推荐路径如下：

### `build_handoff`

1. 生成正式 `handoff`
2. 发出 `handoff_built`
3. 写入 finalize 当前上下文

### `run_final_verification`

1. 消费 `handoff`
2. 产出 `VerificationResult`
3. 发出：
   - `final_verification_started`
   - `final_verification_passed` 或 `final_verification_failed`

### `build_run_outcome`

1. 只在 verification pass 后调用
2. 产出正式 `RunOutcome`
3. 发出：
   - `run_outcome_built`
   - `handoff_attached_to_outcome`

## 8. memory_search 域路径

`memory_search` 域包括：

1. recall 类工具
2. preference recall 类工具
3. search 类工具

第一版正式规则：

1. 这一域只做上下文补充
2. 不直接推进 graph
3. runtime 只做域级识别

推荐路径如下：

1. 调用结果进入当前 step 的上下文装配
2. 必要时以摘要形式进入 `append_evidence`
3. 不直接写 `TaskGraphState`

## 9. subagent 域路径

`subagent` 域包括：

1. 创建 subagent
2. 执行 subagent
3. 收集 subagent 结果

第一版正式规则：

1. `subagent` 域不直接写主 graph 正式状态
2. subagent 结果先进入 step 上下文或 node 级证据
3. 如需 graph 变化，必须通过 `StepResult` 显式表达

## 10. 事件流路径

本任务建议最小事件顺序如下：

```text
tool_called
  -> tool_succeeded / tool_failed
  -> domain apply events (if any)
```

例如：

### execution 工具成功

1. `tool_called`
2. `tool_succeeded`
3. `node_patch_applied`

### task_graph 工具导致切换

1. `tool_called`
2. `tool_succeeded`
3. `node_status_changed`
4. `active_node_switched`

### closeout 工具触发 verification fail

1. `tool_called`
2. `tool_succeeded`
3. `final_verification_failed`
4. `finalize_return_prepared`

## 11. 证据链路径

本任务明确规定：

1. 工具结果进入证据链时，只保留摘要与引用
2. 不保留原始大结果正文

推荐结构方向：

```ts
type ToolEvidence = {
  tool_name: string;
  category: string;
  summary: string;
  result_ref?: string;
};
```

落点规则如下：

1. 当前 node 相关证据 -> `append_evidence`
2. handoff / final verification 相关证据 -> `handoff` 引用或 verification 结果引用
3. 大对象正文由外部存储或正式结果对象承接

## 12. 与 StepResult 的关系

本任务与 `S3-T5` 对齐如下：

1. `execution` 域主要服务 `node_patch`
2. `task_graph` 域主要服务 `node_decision` 与 `followup_nodes`
3. `closeout` 域主要服务 `handoff / VerificationResult / RunOutcome`
4. `memory_search` 与 `subagent` 域主要服务 step 上下文补充

## 13. 第一版边界

第一版明确不采用以下做法：

1. 工具直接写 `RunContext`
2. 工具直接写 `TaskGraphState`
3. 工具原始大结果直接进入事件 payload
4. `closeout` 工具在 `execute` 中途乱入
5. `memory_search` / `subagent` 域直接推进 graph 正式状态

## 14. 对其他任务的直接输入

`S6-T5` 直接服务：

1. `S6-T6` tool registry skeleton
2. `S12-T3` runtime / closeout 事件对齐
3. `S12-T4` payload 最小规范
4. `S3-T5` StepResult 执行路径
5. `S11-T4` finalize 闭环

同时它直接依赖：

1. `S6-T2` 统一 tool protocol
2. `S6-T4` 工具分域结构
3. `S3-T5` Step / Orchestrator 契约
4. `S12-T3` 事件对齐

## 15. 本任务结论摘要

可以压缩成 5 句话：

1. 所有工具调用都先走统一协议和统一事件
2. `execution` 域结果默认先沉当前 `NodePatch`
3. `task_graph` 域结果只能通过 orchestrator 落正式 graph state
4. `closeout` 域只允许在 `finalize` 中调用
5. 证据链统一只保留摘要与引用
