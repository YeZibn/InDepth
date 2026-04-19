# InDepth Observability 参考

更新时间：2026-04-18

## 1. 目标

观测层提供三件事：
1. **过程可追溯**：事件时间线
2. **结果可审计**：task_judged + postmortem
3. **记忆链路可量化**：memory event SQLite

核心问题：
- 如何让执行过程可审计？
- 如何生成可读的复盘报告？

如果从整体运行逻辑看，观测层贯穿整个执行链路，但在当前系统里最重要的角色有三类：
1. 在运行中记录事实
   例如模型调用、工具调用、todo binding warning、tool failure、memory event
2. 在 run 结束时固化关键节点
   例如 `task_finished`、`verification_started`、`verification_failed`、`task_judged`
3. 在失败恢复场景里保留恢复证据
   例如 `todo_orphan_failure_detected`、自动 recovery 规划结果、最终 recovery 摘要

如果把主线压缩成一句话，就是：
Runtime 和工具在执行过程中不断发事件，观测层把这些事件沉淀为“过程时间线 + 最终 judgement + postmortem”，从而让 todo/recovery 这条链路能够被事后回放。

这里最关键的运行节点包括：
- `tool_called / tool_succeeded / tool_failed`
- `todo_binding_missing_warning`
- `todo_orphan_failure_detected`
- `task_finished`
- `verification_started / verification_failed / verification_passed`
- `task_judged`

其中与失败恢复关系最紧密的是：
- run 失败出口时记录的 recovery 相关事件
- `task_finished` 触发的初版 postmortem
- `task_judged` 触发的最终 judgement 与终版 postmortem

因此，观测层不是简单的日志落盘，而是把“运行节点”稳定地变成“可追溯证据”。

相关代码：
- `app/observability/schema.py` - 事件模型
- `app/observability/events.py` - 事件发射
- `app/observability/store.py` - 事件存储
- `app/observability/metrics.py` - 指标聚合
- `app/observability/trace.py` - trace 构建
- `app/observability/postmortem.py` - 复盘生成

## 2. 架构图

### 2.1 观测模块架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          观测模块架构                                     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      emit_event()                                 │   │
│  │  (统一入口，所有组件调用)                                           │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│          ┌─────────────────────┼─────────────────────┐                │
│          ▼                     ▼                     ▼                │
│  ┌───────────────┐   ┌─────────────────┐   ┌───────────────┐       │
│  │  JSONL Writer │   │ SQLite Writer    │   │  Side Effects │       │
│  │               │   │ (仅 memory 事件)  │   │               │       │
│  │ events.jsonl  │   │                 │   │ postmortem     │       │
│  └───────────────┘   └─────────────────┘   └───────────────┘       │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      事件消费层                                    │   │
│  │                                                                  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────┐ │   │
│  │  │ aggregate_  │  │ build_trace │  │ postmortem  │  │ metrics│ │   │
│  │  │ task_metrics│  │             │  │ _generate   │  │       │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 事件发射流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                       事件发射流程                                      │
│                                                                      │
│  任意组件调用 emit_event(...)                                          │
│           │                                                           │
│           ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │  1. 构建 EventRecord                                        │     │
│  │     - event_id: uuid                                        │     │
│  │     - timestamp: ISO 8601                                   │     │
│  │     - actor/role/event_type/payload...                      │     │
│  └─────────────────────────────────────────────────────────────┘     │
│           │                                                           │
│           ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │  2. 写入 JSONL (所有事件)                                    │     │
│  │     └── append to events.jsonl                               │     │
│  └─────────────────────────────────────────────────────────────┘     │
│           │                                                           │
│           ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │  3. 判断事件类型                                              │     │
│  │     │                                                        │     │
│  │     ├── memory_* ──▶ 写入 SystemMemoryEventStore SQLite    │     │
│  │     │              (异常不阻断主流程)                          │     │
│  │     │                                                        │     │
│  │     └── task_finished/task_judged ──▶ 触发 postmortem      │     │
│  │                                        生成/覆盖写            │     │
│  └─────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 postmortem 生成时机

```
┌─────────────────────────────────────────────────────────────────────┐
│                       postmortem 生成时机                              │
│                                                                      │
│  事件               │  操作                                          │
│  ─────────────────┼────────────────────────────────                  │
│  task_finished     │  生成初版 postmortem.md                          │
│                    │  (给 VerifierAgent 提供同 run 证据)              │
│  ─────────────────┼────────────────────────────────                  │
│  task_judged      │  覆盖写最终版 postmortem.md                       │
│                    │  (包含完整 judgement)                            │
└─────────────────────────────────────────────────────────────────────┘
```

## 3. 事件模型

### 3.1 EventRecord

```python
@dataclass
class EventRecord:
    event_id: str           # UUID，唯一标识
    task_id: str            # 任务 ID
    run_id: str             # 运行 ID
    timestamp: str           # ISO 8601 时间戳
    actor: str              # 参与者: main/subagent/verifier
    role: str               # 角色: general/researcher/builder/...
    event_type: str         # 事件类型
    status: Optional[str]  # 状态: ok/error/...
    duration_ms: Optional[int]  # 持续时间
    payload: Optional[Dict[str, Any]]  # 额外数据
```

### 3.2 事件类型总表

| 类别 | 事件 | 说明 |
|------|------|------|
| **任务** | `task_started` | 任务开始 |
| | `task_finished` | 任务结束 |
| | `task_judged` | 任务判定完成 |
| | `task_updated` | todo 顶层更新 |
| | `task_fallback_recorded` | 记录 subtask fallback 事实 |
| | `task_recovery_planned` | 生成恢复决策 |
| | `run_resumed` | 同一 run 从等待态恢复 |
| | `user_clarification_received` | 接收到用户澄清补充 |
| | `clarification_requested` | 模型请求用户澄清 |
| | `clarification_judge_started` | 澄清判定开始 |
| | `clarification_judge_completed` | 澄清判定完成（LLM） |
| | `clarification_judge_fallback` | 澄清判定回退启发式 |
| **模型** | `model_reasoning` | 模型思考中 |
| | `model_failed` | 模型调用失败 |
| | `model_stopped_length` | 超出长度限制 |
| | `model_stopped_content_filter` | 内容过滤 |
| **工具** | `tool_called` | 工具被调用 |
| | `tool_succeeded` | 工具成功 |
| | `tool_failed` | 工具失败 |
| **子代理** | `subagent_created` | SubAgent 创建 |
| | `subagent_started` | SubAgent 开始 |
| | `subagent_finished` | SubAgent 完成 |
| | `subagent_failed` | SubAgent 失败 |
| **Todo** | `status_updated` | 状态更新 |
| | `subtask_updated` | subtask 增量更新 |
| | `subtask_reopened` | subtask 重新激活 |
| | `followup_subtasks_appended` | 追加 follow-up subtasks |
| | `todo_binding_missing_warning` | 已进入 todo 流但未绑定 active subtask |
| | `todo_orphan_failure_detected` | 失败发生时没有 active subtask 可归属 |
| | `todo_recovery_auto_planned` | runtime 自动恢复规划已生成 |
| **检索** | `search_guard_initialized` | 检索门禁初始化 |
| | `search_round_started` | 检索轮次开始 |
| | `search_round_finished` | 检索轮次结束 |
| | `search_stopped` | 检索停止 |
| | `search_budget_auto_overridden` | 检索预算自动扩容 |
| **模型请求** | `model_request_started` | step 级模型请求开始，含 token 统计 |
| **记忆** | `memory_triggered` | 记忆触发 |
| | `memory_retrieved` | 记忆检索 |
| | `memory_decision_made` | 记忆决策 |
| **用户偏好** | `user_preference_recall_succeeded` | 用户偏好召回成功 |
| | `user_preference_recall_failed` | 用户偏好召回失败 |
| | `user_preference_extract_started` | 用户偏好提取开始 |
| | `user_preference_extract_succeeded` | 用户偏好提取成功 |
| | `user_preference_extract_failed` | 用户偏好提取失败 |
| | `user_preference_capture_succeeded` | 用户偏好写回成功 |
| | `user_preference_capture_failed` | 用户偏好写回失败 |
| **压缩** | `context_compression_started` | 开始压缩 |
| | `context_compression_succeeded` | 压缩成功 |
| | `context_compression_failed` | 压缩失败 |
| | `context_consistency_check_failed` | 一致性检查失败 |
| **评估** | `verification_started` | 开始评估 |
| | `verification_passed` | 评估通过 |
| | `verification_failed` | 评估失败 |
| | `verification_skipped` | 评估跳过（等待用户输入） |

### 3.3 未知事件处理

若传入未知 `event_type`：
- 自动归一化为 `unknown_event_type`
- 在 payload 注入 `_original_event_type` 与 warning 标记

注意：
- 已被业务代码真实发射的事件类型，应优先补入 `EVENT_TYPES`
- `unknown_event_type` 只用于真正未建模的新事件，不应用来承载已知业务链路

## 4. 事件落点

### 4.1 JSONL

- 路径：`app/observability/data/events.jsonl`
- 所有事件都写入 JSONL
- append-only 模式，高并发友好

### 4.2 SQLite (仅 memory 事件)

`SystemMemoryEventStore` 仅接收三类事件：

| 事件 | 表名 |
|------|------|
| `memory_triggered` | `memory_trigger_event` |
| `memory_retrieved` | `memory_retrieval_event` |
| `memory_decision_made` | `memory_decision_event` |

默认 DB：`db/system_memory.db`

**写入策略**：memory 事件同时写 JSONL + SQLite，SQLite 异常不阻塞主流程

## 5. 指标聚合

### 5.1 aggregate_task_metrics

```python
def aggregate_task_metrics(events: List[EventRecord]) -> Dict[str, Any]:
    """从事件列表聚合任务指标"""
```

**输出结构**：

```python
{
    # 规模
    "event_count": int,
    "duration_seconds": float,

    # 状态
    "success_count": int,
    "failure_count": int,

    # 工具
    "tool_called_count": int,
    "tool_failed_count": int,

    # 子代理
    "subagent_started_count": int,
    "subagent_failed_count": int,

    # 评估
    "verification_started_count": int,
    "task_judged_count": int,

    # 质量
    "srr": float,          # Self-Report Rate (自报告成功率)
    "vsr": float,          # Verified Success Rate (验证成功率)
    "overclaim_rate": float,

    # 分布
    "event_type_breakdown": Dict[str, int],
    "role_breakdown": Dict[str, int>,
}
```

### 5.2 指标计算公式

```
srr = self_reported_success_count / total_count
vsr = verified_success_count / total_count
overclaim_rate = overclaim_count / total_count
```

## 6. trace 构建

### 6.1 build_trace

```python
def build_trace(events: List[EventRecord]) -> List[Dict]:
    """构建可读的时间线"""
```

**处理步骤**：
1. 按 timestamp 升序排序
2. 生成 step 序号
3. 每步包含 `event_type/actor/role/status/payload`

**输出示例**：

```python
[
    {
        "step": 1,
        "event_type": "task_started",
        "actor": "main",
        "role": "general",
        "status": "ok",
        "timestamp": "2024-01-01T10:00:00Z",
        "payload": {"task_id": "xxx"}
    },
    {
        "step": 2,
        "event_type": "tool_called",
        "actor": "main",
        "role": "general",
        "status": "ok",
        "timestamp": "2024-01-01T10:00:01Z",
        "payload": {"name": "bash", "arguments": {...}}
    },
    # ...
]
```

## 7. postmortem 生成

### 7.1 输出路径

默认路径：
- `observability-evals/<task_id>/<run_id>/postmortem.md`
- 无 run_id 时：`observability-evals/<task_id>/postmortem.md`
- 当 `run_id == task_id` 时，采用任务根目录：`observability-evals/<task_id>/postmortem.md`（避免重复嵌套目录）

同目录补充文件：
- `events.jsonl`（该 run 事件流水）
- `judgement.json`（该 run 最终判定，若存在）

任务根目录补充文件：
- `task_summary.json`（任务级 run 聚合）
- `task_judgement.json`（最新一次任务判定快照）
- `task_judgement_history.jsonl`（全部 task_judged 历史）

Todo 场景约定：
- 观测 schema 字段仍为 `task_id/run_id`
- 但值统一映射为 `todo-id:<todo_id>`，用于与 Runtime 主任务 ID 解耦

### 7.2 内容结构

固定 6 段：

```markdown
# Postmortem: <task_id>

## 1. 执行摘要
<goal>
<final_answer 摘要>
<stop_reason>

## 2. 工具与子代理指标
<tool_called_count / tool_failed_count>
<subagent_started_count / subagent_failed_count>

## 3. 评估结论
<final_status>
<verdict>

## 4. 关键时间线
<前 40 条 trace>

## 5. 失败与修复线索
<error 分析>
<potential_issues>

## 6. 改进建议 (Top 3)
<top 3 recommendations>
```

### 7.3 文件管理

目录写入时会清理 legacy `postmortem_*.md` 快照，保留单一 canonical 文件。

## 8. 关键事件详解

### 8.1 任务事件

```
task_started
    payload: {task_id, run_id}

task_finished
    payload: {
        stop_reason,
        runtime_state,
        tool_failure_count,
        has_tool_failures
    }

task_judged
    payload: {
        final_status,
        verified_success,
        failure_type,
        verifier_breakdown
    }

verification_skipped
    payload: {
        reason,          # awaiting_user_input
        stop_reason,
        runtime_state
    }

clarification_requested
    payload: {
        question_preview,
        missing_info_hints,
        judge_source,        # llm / heuristic_fallback / heuristic
        judge_confidence,    # 0~1
        judge_reason,
        step
    }

clarification_judge_started
    payload: {
        step,
        content_preview
    }

clarification_judge_completed
    payload: {
        step,
        decision,
        decision_raw,
        confidence,
        threshold,
        source,              # llm
        reason,
        latency_ms
    }

clarification_judge_fallback
    payload: {
        step,
        reason,
        fallback_decision,
        source,              # heuristic
        latency_ms
    }
```

### 8.2 工具事件

```
tool_called
    payload: {name, arguments}

tool_succeeded
    payload: {name, result_preview}

tool_failed
    payload: {name, error}
```

### 8.3 压缩事件

```
model_request_started
    payload: {
        step,
        model,
        encoding,
        token_counter_kind,        # tiktoken
        messages_tokens,
        tools_tokens,
        input_tokens,
        reserved_output_tokens,
        total_window_claim_tokens,
        context_usage_ratio,
        compression_trigger_window_tokens,
        model_context_window_tokens
    }

context_compression_started
    payload: {
        trigger,
        mode,
        estimated_tokens,
        context_usage_ratio,
        compression_trigger_window_tokens,
        model_context_window_tokens
    }

context_compression_succeeded
    payload: {
        before_messages,
        after_messages,
        dropped_messages
    }

context_compression_failed
    payload: {error}

context_consistency_check_failed
    payload: {reason}
```

## 9. 测试映射

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_memory_observability_events.py` | memory 事件 SQLite 落盘 |
| `tests/test_postmortem_output_layout.py` | postmortem 格式与文件管理 |
| `tests/test_runtime_eval_integration.py` | 评估事件链路 |
| `tests/test_event_schema.py` | EventRecord 构造与校验 |
| `tests/test_metrics_aggregation.py` | 指标聚合计算 |
