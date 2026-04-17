# InDepth Runtime 参考

更新时间：2026-04-17

## 1. 定位

`AgentRuntime`（`app/core/runtime/agent_runtime.py`）是执行中枢，负责把对话请求转为可控执行循环，并在结束时完成评估、观测、记忆收尾。

核心职责：
- 管理多步推理循环（Tool Calling Loop）
- 处理模型响应与工具执行
- 装配 stop policy、todo recovery、clarification、memory lifecycle
- 触发评估与观测事件
- 沉淀任务记忆与用户偏好

## 2. 架构图

### 2.1 模块架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              AgentRuntime                                │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │
│  │  ModelProvider   │  │  ToolRegistry    │  │     MemoryStore         │ │
│  │                 │  │                  │  │                         │ │
│  │ ┌─────────────┐ │  │ ┌─────────────┐  │  │ ┌───────────────────┐  │ │
│  │ │HttpChatModel│ │  │ │   invoke()  │  │  │ │SQLiteMemoryStore  │  │ │
│  │ │ Provider    │ │  │ └─────────────┘  │  │ └───────────────────┘  │ │
│  │ └─────────────┘ │  │                  │  │ ┌───────────────────┐  │ │
│  │                 │  │ ┌─────────────┐  │  │ │SystemMemoryStore  │  │ │
│  │ ┌─────────────┐ │  │ │list_tools()│  │  │ └───────────────────┘  │ │
│  │ │ MockProvider│ │  │ └─────────────┘  │  │                         │ │
│  │ └─────────────┘ │  │                  │  │ ┌───────────────────┐  │ │
│  └─────────────────┘  │ tools=[]        │  │ │ContextCompressor  │  │ │
│                        └─────────────────┘  │ └───────────────────┘  │ │
│                                               └─────────────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │
│  │EvalOrchestrator │  │ Observability   │  │  CompressionConfig      │ │
│  │                 │  │                 │  │                         │ │
│  │ ┌─────────────┐ │  │ emit_event()   │  │ strong_token_ratio     │ │
│  │ │ evaluate()  │ │  │                 │  │ event/tool thresholds  │ │
│  │ └─────────────┘ │  │ postmortem     │  │ tool_burst_threshold   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 执行流程

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      run() 主循环 (max_steps)                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Step N:                                                     │   │
│  │                                                              │   │
│  │  1. _maybe_compact_mid_run() ──▶ 判断是否触发上下文压缩     │   │
│  │                           │                                  │   │
│  │  2. MemoryStore.get_recent_messages() ──▶ 加载历史消息      │   │
│  │                           │                                  │   │
│  │  3. model_provider.generate(messages, tools) ──▶ 调用模型   │   │
│  │                           │                                  │   │
│  │  4. 解析 finish_reason                                           │   │
│  │      │                                                          │   │
│  │      ├─── tool_calls ──▶ _handle_native_tool_calls()          │   │
│  │      │                        │                               │   │
│  │      │                   ToolRegistry.invoke()                │   │
│  │      │                        │                               │   │
│  │      │                   emit_event(tool_*)                    │   │
│  │      │                        │                               │   │
│  │      │                   回写 tool 消息                        │   │
│  │      │                        │                               │   │
│  │      ├─── stop ──────────────▶ 正常收敛，输出 final_answer   │   │
│  │      │                                                          │   │
│  │      ├─── length ────────────▶ 标记 stop_reason=length        │   │
│  │      │                                                          │   │
│  │      └─── content_filter ──▶ 标记 stop_reason=content_filter │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    任务结束处理                                 │   │
│  │                                                               │   │
│  │  emit_event(task_finished)                                    │   │
│  │        │                                                      │   │
│  │  EvalOrchestrator.evaluate()                                  │   │
│  │        │                                                      │   │
│  │  emit_event(task_judged)                                      │   │
│  │        │                                                      │   │
│  │  _finalize_task_memory() ──▶ SystemMemoryStore.upsert_card() │   │
│  │        │                                                      │   │
│  │  MemoryStore.compact_final()                                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## 3. 核心组件详解

### 3.1 ModelProvider

**职责**：封装模型 API，屏蔽不同模型供应商差异

**默认实现**：`HttpChatModelProvider`

```python
class HttpChatModelProvider:
    def generate(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        generation_config: Optional[GenerationConfig] = None,
    ) -> LLMResponse:
        # POST <LLM_BASE_URL>/chat/completions
        # 处理重试、退避、超时
```

**关键特性**：
- 接口：`POST <LLM_BASE_URL>/chat/completions`
- 默认重试：`max_retries=4`
- 退避策略：`retry_backoff_seconds=1.2`（指数退避）
- 默认超时：`timeout_seconds=120`
- 空 tools 时不发送 `tools/tool_choice`（兼容部分 provider）

### 3.2 ToolRegistry

**职责**：工具的注册、发现与调用

```python
class ToolRegistry:
    def register(self, tool_functions: List[ToolFunction]) -> None
    def invoke(self, name: str, args: Dict[str, Any]) -> ToolResult
    def list_tool_schemas(self) -> List[Dict]
```

**调用链**：
```
@tool(...) ---> ToolFunction
      │
      ▼
register_tool_functions() ---> ToolRegistry.register()
      │
      ▼
Runtime.generate() ---> ToolRegistry.list_tools() ---> tools=[] in request
      │
      ▼
Model returns tool_calls ---> ToolRegistry.invoke(name, args)
      │
      ▼
返回 ToolResult {success, result/error}
```

### 3.3 Runtime Strategy Modules

当前 `AgentRuntime` 已把主要策略拆到独立模块：

1. `runtime_stop_policy.py`
2. `runtime_finalization.py`
3. `runtime_compaction_policy.py`
4. `clarification_policy.py`
5. `todo_runtime_lifecycle.py`
6. `user_preference_lifecycle.py`
7. `system_memory_lifecycle.py`

### 3.4 MemoryStore

**职责**：管理会话历史与上下文压缩

三条链路：
1. `SQLiteMemoryStore`：Runtime 会话记忆
2. `SystemMemoryStore`：系统经验记忆
3. `UserPreferenceStore`：用户偏好记忆（用于个性化提示词注入）

### 3.5 EvalOrchestrator

**职责**：区分"回答完成"与"任务完成"

```python
class EvalOrchestrator:
    def evaluate(
        self,
        run_outcome: RunOutcome,
    ) -> RunJudgement:
        # 1. 构建 verifier 链
        # 2. 顺序执行，收集 VerifierResult
        # 3. 硬失败优先
        # 4. 返回 RunJudgement
```

## 4. run() 主循环详解

### 4.1 方法签名

```python
def run(
    self,
    user_input: str,
    task_id: str = "runtime_task",
    run_id: str = "runtime_run",
    resume_from_waiting: bool = False,
) -> str:
```

### 4.2 关键状态

| 状态变量 | 类型 | 说明 |
|---------|------|------|
| `final_answer` | `Optional[str]` | 最终回答文本 |
| `task_status` | `str` | `ok` / `error` |
| `stop_reason` | `str` | 收敛原因 |
| `runtime_state` | `str` | `running/awaiting_user_input/completed/failed` |
| `last_tool_failures` | `List[Dict]` | 工具失败记录 |
| `_active_todo_context` | `Dict[str, Any]` | 当前活跃的 todo 执行上下文，包含 `todo_id/active_subtask_id/active_subtask_number/execution_phase/binding_required/binding_state/todo_bound_at` |
| `_latest_todo_recovery` | `Dict[str, Any]` | 最近一次自动恢复链路产物 |
| `consecutive_tool_calls` | `int` | 当前一次 `tool_calls` 响应的条目数 |

### 4.3 finish_reason 处理

| finish_reason | 处理逻辑 | stop_reason |
|--------------|---------|-------------|
| `stop` + 澄清意图 | 由 LLM 判定（失败回退启发式），命中后挂起等待用户输入（同 run 可恢复） | `awaiting_user_input` |
| `stop` + 非澄清 | 正常收敛 | `stop` |
| `length` | 超出上下文 | `length` |
| `content_filter` | 内容过滤 | `content_filter` |
| `tool_calls` | 执行工具（循环） | - |
| 其他 + 有文本 | fallback 收敛 | `fallback_content` |
| 其他 + 空 | 标记错误 | `model_failed` |

### 4.4 澄清判定与恢复链路

`finish_reason=stop` 且有文本时：
1. 进入澄清判定子流程 `_judge_clarification_request(...)`。
2. 优先调用 LLM judge（mini 模型）输出 JSON：
   - `is_clarification_request: bool`
   - `confidence: float(0~1)`
   - `reason: str`
3. 仅当 `is_clarification_request=true && confidence>=threshold(默认 0.60)` 判为澄清。
4. 若 judge 调用异常或输出非法，则回退到 `is_clarification_request(...)` 启发式规则。
5. 命中澄清时：
   - `runtime_state=awaiting_user_input`
   - 发 `clarification_requested`
   - 跳过 verifier（发 `verification_skipped`）

#### 澄清恢复机制

当 Runtime 进入 `awaiting_user_input` 状态后：

```
用户输入补充信息
    │
    ▼
emit_event(user_clarification_received)
    │
    ▼
emit_event(run_resumed)
    │
    ▼
AgentRuntime.run(
    user_input=<补充信息>,
    resume_from_waiting=True,  # 关键参数
    task_id=<相同task_id>,
    run_id=<相同run_id>        # 保持连续性
)
    │
    ▼
从上次中断点继续执行（保留完整对话历史）
```

**关键特性**：
- **同一 run_id**：恢复执行使用相同的 `run_id`，保证观测事件连续性
- **会话记忆保留**：`SQLiteMemoryStore` 中保留完整对话历史
- **自动检测**：`resume_from_waiting=True` 时自动检测并恢复状态

### 4.5 Todo 恢复自动接入

当前 Runtime 已接入 todo 恢复链路。

#### 4.5.1 活跃 todo 上下文

Runtime 会基于工具执行结果维护当前活跃的 todo 上下文：
- `todo_id`
- `active_subtask_id`
- `active_subtask_number`
- `execution_phase`
- `binding_required`
- `binding_state`
- `todo_bound_at`

主要来源工具：
- `create_task`
- `update_task_status`
- `update_subtask`
- `record_task_fallback`
- `reopen_subtask`
- `get_next_task`

当前语义：
- `create_task` 后会记录 `todo_id`，并进入 `planning`
- `create_task` 若当前 task 已绑定 active todo，默认会被拒绝；只有显式 `force_new_cycle=true` 才允许切新周期
- `update_task_status(..., status="in-progress")` 后会记录 `active_subtask_number`，并进入 `executing`
- `update_subtask(...)` 后会同步当前 active subtask 的 `subtask_id/subtask_number`
- `update_task_status(..., status in {blocked, failed, partial, awaiting_input, timed_out})` 后会进入 `recovering`
- `record_task_fallback` 后会把该 subtask 视为当前恢复目标，并进入 `recovering`
- `reopen_subtask` 后会把该 subtask 重新视为当前执行目标，并进入 `executing`
- `get_next_task` 返回 ready subtask 后会记录候选 `active_subtask_number`，但此时仍更接近“待激活”的 `planning`
- run 完成后当前 todo 绑定会切换到 `closed`

这层上下文的作用不只是记忆，而是帮助 Runtime 判断：
- 当前是否已经进入 todo 执行流
- 当前失败是否能归属到具体 subtask
- 当前是否应当要求工具调用绑定到 active subtask

#### 4.5.2 自动触发时机

当 Runtime 进入以下未完成出口时，会自动尝试恢复链路：
- `awaiting_user_input`
- `tool_failed_before_stop`
- `max_steps_reached`
- 其他 `runtime_state=failed` 分支

自动顺序为：
1. `record_task_fallback`
2. `update_task_status`
3. `plan_task_recovery`
4. 若 `needs_derived_recovery_subtask=true && decision_level=auto && stop_auto_recovery=false`，则 `append_followup_subtasks`

#### 4.5.3 自动恢复结果

Runtime 会把自动恢复结果保存在 `_latest_todo_recovery` 中，随后继续外溢到：
- `verification_handoff.recovery`
- `task_judged.payload.verification_handoff`
- postmortem “交付内容”区块
- 最终用户回复中的“恢复摘要”
- **空输入处理**：空输入不会触发模型调用，提示用户补充信息

#### 4.5.4 Todo Binding Warning

当前 Runtime 已新增一层 `warn` 级 todo binding guard。

触发条件：
- 已存在 `todo_id`
- `binding_required = true`
- 当前没有 `active_subtask_number`
- 模型仍尝试调用普通业务工具

当前效果：
- Runtime 会发出 `todo_binding_missing_warning`
- 不会立即中断整个执行循环
- 目的是先显式暴露“todo 已创建但执行未绑定 subtask”的编排问题

当前默认视为编排/补救工具，因此不会触发该 warning 的工具包括：
- `create_task`
- `list_tasks`
- `get_next_task`
- `get_task_progress`
- `generate_task_report`
- `update_task_status`
- `record_task_fallback`
- `plan_task_recovery`
- `append_followup_subtasks`

#### 4.5.5 Orphan Failure

当前 Runtime 已新增 `orphan failure` 分支。

定义：
- todo 已创建
- Runtime 已知 `todo_id`
- 但失败发生时没有 `active_subtask_number`

当前行为：
- Runtime 不再直接跳过恢复逻辑
- 会生成一份最小恢复结果并写入 `_latest_todo_recovery`
- 该恢复结果通常包含：
  - `reason_code = orphan_subtask_unbound`
  - `primary_action = decision_handoff`
  - `decision_level = agent_decide`

注意：
- 这类失败当前不会自动修改某个具体 subtask 的状态
- 因为 Runtime 无法确定该失败究竟属于哪个 subtask
- 它暴露的是“编排绑定缺口”，而不是普通业务失败

## 5. 上下文压缩

### 5.1 压缩触发条件

按优先级依次检查：

```
1. token_ratio >= midrun_token_ratio ──▶ trigger=token, mode=midrun
                                            (运行中 token 压缩)

2. current_tool_calls_count >= tool_burst_threshold ──▶ trigger=event, mode=event
                                                      (事件驱动，工具链替换压缩)
```

### 5.2 压缩执行流程

```
compact_mid_run(conversation_id, trigger, mode)
    │
    ├──▶ if trigger == event:
    │       ├──▶ 定位最近连续工具调用段（assistant(tool_calls)+tool...）
    │       ├──▶ 过滤状态工具（create_task/get_next_task/update_task_status/init_search_guard）
    │       ├──▶ 保留最近 1 个工具单元原文
    │       ├──▶ UPDATE 锚点为 [tool-chain-compact] 摘要 + DELETE 其余消息
    │       └──▶ 不写 summaries
    │
    └──▶ else (token/finalize):
            ├──▶ 按 token 预算从最新 turn 向前累计计算保留区间
            ├──▶ ContextCompressor.merge_summary()
            ├──▶ validate_consistency()（一致性守护）
            ├──▶ UPSERT summaries
            └──▶ 删除被摘要覆盖的前缀消息
```

### 5.3 结构化摘要 v1

```json
{
  "version": "v1",
  "task_state": {
    "goal": "当前任务目标",
    "progress": "已完成的工作",
    "next_step": "下一步计划",
    "completion": "完成度评估"
  },
  "decisions": [
    {"id": "d1", "content": "决策内容", "anchor": "对应消息ID"}
  ],
  "constraints": [
    {"id": "c1", "content": "必须遵守的约束", "immutable": true}
  ],
  "artifacts": [
    {"id": "a1", "path": "文件路径", "desc": "产出物描述"}
  ],
  "open_questions": [
    {"id": "q1", "content": "未解决的问题"}
  ]
}
```

## 6. 评估与判定

### 6.1 判定流程

```
task_finished 事件
        │
        ▼
EvalOrchestrator.evaluate(run_outcome)
        │
        ├──▶ build_default_deterministic_verifiers()
        │       │
        │       ├──▶ StopReasonVerifier (硬检查)
        │       └──▶ ToolFailureVerifier (硬检查)
        │
        ├──▶ 顺序执行每个 verifier
        │
        ├──▶ 硬失败优先检查
        │       └──▶ 任何 hard=true && passed=false ──▶ fail
        │
        └──▶ soft 平均分检查
                └──▶ avg < run_outcome.verification_handoff.soft_score_threshold ──▶ partial
```

### 6.2 判定结果

| 条件 | final_status |
|------|-------------|
| 硬检查失败 | `fail` |
| 硬检查通过 + soft < 阈值 | `partial` |
| 硬检查通过 + soft >= 阈值 | `pass` |

### 6.3 Verification Handoff 来源观测

- 生成时机：step 内进入终态（非 `awaiting_user_input`）时立即生成；循环外仅保底生成。
- `verification_started.payload.handoff_source`：`llm` 或 `fallback_rule`
- `task_judged.payload.verification_handoff_source`：`llm` 或 `fallback_rule`
- `task_judged.payload.verification_handoff`：结构化交付快照（postmortem 用于渲染“交付内容”）

## 7. 记忆生命周期

### 7.1 run_start：系统记忆召回注入

首次模型请求前执行 `_inject_system_memory_recall()`：

```python
def _inject_system_memory_recall(self, task_id, run_id, user_input, messages):
    # 1) 触发事件
    emit_event(..., event_type="memory_triggered", payload={"source": "runtime_start_recall"})

    # 2) 拉取 active 且未过期候选池
    rows = system_memory.search_cards(query="", only_active=True, limit=50)

    # 3) LLM 基于 user_input + title 做 Top-K 重排
    selected = rerank_by_llm(user_input=user_input, titles=rows)[:5]

    # 4) 逐条 retrieval + 汇总 decision
    # 5) 轻注入（memory_id + recall_hint）到 system prompt
```

关键规则：
1. 精确率优先，最多 5 条。
2. 未命中不阻塞主流程。
3. 仅注入 `memory_id + recall_hint`，不注入整卡全文。

### 7.2 run_end：_finalize_task_memory()

任务结束时强制执行：

```python
def _finalize_task_memory(self, task_id, run_id, task_status):
    # 1. 写入 postmortem 经验卡
    card_id = f"mem_task_{task_slug}_{run_slug}"
    card = {
        "id": card_id,
        "scenario": {"stage": "postmortem"},
        "problem_pattern": {"risk_level": "P1" if task_status == "error" else "P3"},
        "...": "..."
    }
    SystemMemoryStore.upsert_card(card)

    # 2. 追加记忆事件三连
    emit_event(task_id=task_id, event_type="memory_triggered", payload={"source": "runtime_forced_finalize"})
    emit_event(task_id=task_id, event_type="memory_retrieved", payload={"reason": "task_end_finalization"})
    emit_event(task_id=task_id, event_type="memory_decision_made", payload={"decision": "accepted"})
```

### 7.3 run_during：候选 capture（tool）

运行中候选经验仍通过 `capture_runtime_memory_candidate` tool 显式调用完成，Runtime 不做隐式自动 capture。

## 8. 关键事件总表

| 事件类型 | 说明 | 载荷 |
|---------|------|------|
| `task_started` | 任务开始 | task_id, run_id |
| `model_reasoning` | 模型思考中 | reasoning_content |
| `model_failed` | 模型调用失败 | error |
| `model_stopped_length` | 超出长度限制 | - |
| `model_stopped_content_filter` | 内容过滤 | - |
| `tool_called` | 工具调用 | name, arguments |
| `tool_succeeded` | 工具成功 | name, result |
| `tool_failed` | 工具失败 | name, error |
| `todo_binding_missing_warning` | todo 已创建但普通工具调用缺少 active subtask 绑定 | todo_id, tool, execution_phase, guard_mode |
| `todo_orphan_failure_detected` | todo 流失败时没有 active subtask，无法归属失败 | todo_id, stop_reason, runtime_state, execution_phase |
| `context_compression_started` | 开始压缩 | trigger, mode |
| `context_compression_succeeded` | 压缩成功 | before, after |
| `context_compression_failed` | 压缩失败 | error |
| `verification_started` | 开始评估 | stop_reason, handoff_source |
| `verification_passed` | 评估通过 | verifier_results |
| `verification_failed` | 评估失败 | verifier_results |
| `verification_skipped` | 跳过评估（等待用户输入） | reason, runtime_state |
| `clarification_requested` | 请求用户补充信息 | question_preview, judge_source, judge_confidence |
| `clarification_judge_started` | 澄清判定开始 | step, content_preview |
| `clarification_judge_completed` | 澄清判定完成（LLM） | decision, confidence, threshold, latency_ms |
| `clarification_judge_fallback` | 澄清判定回退启发式 | reason, fallback_decision, source |
| `user_clarification_received` | 收到用户补充 | - |
| `run_resumed` | 同一 run 恢复执行 | - |
| `task_finished` | 任务结束 | stop_reason, tool_failure_count |
| `task_judged` | 任务判定 | 完整 judgement + verification_handoff_source + verification_handoff |
| `memory_triggered` | 记忆触发 | context_id, risk_level, source/source_event |
| `memory_retrieved` | 记忆检索 | trigger_event_id, memory_id, score, source/reason |
| `memory_decision_made` | 记忆决策 | trigger_event_id, memory_id, decision, reason |

## 9. 配置参数

### 9.1 运行时配置

```python
@dataclass
class RuntimeConfig:
    max_steps: int = 50          # 最大步数
    trace_steps: bool = True     # 是否打印追踪
    enable_llm_judge: bool = False  # 是否启用 LLM 评判
    enable_llm_clarification_judge: bool = True  # 是否启用 LLM 澄清判定
    clarification_judge_confidence_threshold: float = 0.60  # 澄清置信度阈值
    enable_clarification_heuristic_fallback: bool = True  # 判定失败时回退启发式
```

### 9.2 压缩配置

```python
@dataclass
class RuntimeCompressionConfig:
    enabled_mid_run: bool = True
    round_interval: int = 4              # 兼容保留（当前 mid-run 不再使用 round 触发）
    midrun_token_ratio: float = 0.82      # 运行中压缩阈值
    context_window_tokens: int = 16000    # 上下文窗口大小
    keep_recent_turns: int = 8            # 仅在预算不可用时的兜底策略
    tool_burst_threshold: int = 5         # 单次 tool_calls 条目阈值
    consistency_guard: bool = True        # 一致性守护
    target_keep_ratio_midrun: float = 0.40
    target_keep_ratio_finalize: float = 0.40
    min_keep_turns: int = 3
    compressor_kind: str = "auto"
    compressor_llm_max_tokens: int = 1200
    event_summarizer_kind: str = "auto"
    event_summarizer_max_tokens: int = 280
```

压缩器策略说明：
- `auto`：真实模型走 LLM 压缩，`MockModelProvider` 自动使用规则压缩
- `rule`：全程规则压缩
- `llm`：优先走 LLM 压缩，失败时自动回退规则压缩
- `midrun/finalize` 路径由 `compressor_kind` 控制结构化摘要压缩
- `event` 路径由独立的 `event_summarizer_kind` 控制工具链替代摘要；真实 provider 默认优先使用 mini 模型，失败时回退规则摘要

## 10. 入口点

| 入口 | 文件 | 说明 |
|------|------|------|
| `create_runtime()` | `app/core/bootstrap.py` | CLI Runtime 构造 |
| `RuntimeAgent` | `app/agent/runtime_agent.py` | 交互式 CLI |
| `BaseAgent` | `app/agent/agent.py` | 主 Agent 封装 |
| `SubAgent` | `app/agent/sub_agent.py` | 子 Agent 封装 |

### 10.1 Runtime CLI（单一 task 模式）

当前 `runtime_agent.py` 采用单一 `task` 模式：
1. 启动即进入 `task` 模式，并初始化 `task` 任务。
2. 普通输入统一走执行链路（不再按模式禁用工具）。
3. `/mode` 仅保留兼容提示：当前只支持 `task` 单模式。
4. 可用命令：
   - `/task <label>`：结束旧任务并开启新任务
   - `/newtask <label>`：`/task` 别名
   - `/new [label]`：结束旧任务并开启新任务
   - `/status`：查看 `mode=task` 与当前 `task_id`
   - `/help`、`/exit`

### 10.2 CLI 澄清交互

当前 CLI 在澄清态（`awaiting_user_input`）增强行为：
1. 输出样式：
   - `[需要澄清]`
   - Agent 原问题
   - `请直接回复补充信息，我会在当前任务中继续。`
2. 用户下一次正常输入默认作为澄清补充，沿用同一 `run_id` 恢复执行。
3. 空输入不会触发模型调用，会提示：`[需要澄清] 请补充信息后继续...`
4. 支持 `/new [label]` 立即结束旧任务并启动新任务（清空澄清等待态）。

### 10.3 Completed Run 收尾

completed run 当前分为两段：
1. 主链路串行完成：`task_finished -> verification -> task_judged`
2. 收尾任务并行执行，并在全部完成后返回 `run()`

并行收尾任务包括：
1. postmortem 生成
2. system memory finalize
3. user preference capture
4. final memory compaction

## 11. 测试

- `tests/test_runtime_context_compression.py`：压缩触发、摘要结构、一致性守护
- `tests/test_runtime_eval_integration.py`：评估链路、记忆沉淀
- `tests/test_main_agent.py`：澄清态 run 复用、CLI 输出格式与 `/new` 任务切换
