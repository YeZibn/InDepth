# InDepth Runtime 参考

更新时间：2026-04-12

## 1. 定位

`AgentRuntime`（`app/core/runtime/agent_runtime.py`）是执行中枢，负责把对话请求转为可控执行循环，并在结束时完成评估、观测、记忆收尾。

核心职责：
- 管理多步推理循环（Tool Calling Loop）
- 处理模型响应与工具执行
- 控制任务收敛条件
- 触发评估与观测事件
- 沉淀任务记忆

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
│  │ ┌─────────────┐ │  │ emit_event()   │  │ light_token_ratio      │ │
│  │ │ evaluate()  │ │  │                 │  │ strong_token_ratio     │ │
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

### 3.3 MemoryStore

**职责**：管理会话历史与上下文压缩

两条链路：
1. `SQLiteMemoryStore`：Runtime 会话记忆
2. `SystemMemoryStore`：系统经验记忆

### 3.4 EvalOrchestrator

**职责**：区分"回答完成"与"任务完成"

```python
class EvalOrchestrator:
    def evaluate(
        self,
        task_spec: TaskSpec,
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
    task_spec: Optional[Dict[str, Any]] = None,
) -> str:
```

### 4.2 关键状态

| 状态变量 | 类型 | 说明 |
|---------|------|------|
| `final_answer` | `Optional[str]` | 最终回答文本 |
| `task_status` | `str` | `ok` / `error` |
| `stop_reason` | `str` | 收敛原因 |
| `last_tool_failures` | `List[Dict]` | 工具失败记录 |
| `consecutive_tool_calls` | `int` | 连续工具调用计数 |

### 4.3 finish_reason 处理

| finish_reason | 处理逻辑 | stop_reason |
|--------------|---------|-------------|
| `stop` | 正常收敛 | `stop` |
| `length` | 超出上下文 | `length` |
| `content_filter` | 内容过滤 | `content_filter` |
| `tool_calls` | 执行工具（循环） | - |
| 其他 + 有文本 | fallback 收敛 | `fallback_content` |
| 其他 + 空 | 标记错误 | `model_failed` |

## 5. 上下文压缩

### 5.1 压缩触发条件

按优先级依次检查：

```
1. token_ratio >= strong_token_ratio ──▶ trigger=token, mode=strong
                                            (激进压缩，保留更少历史)

2. consecutive_tool_calls >= tool_burst_threshold ──▶ trigger=event, mode=light
                                                      (事件驱动，轻量压缩)

3. round % round_interval == 0 ──▶ trigger=round, mode=light
                                     (轮次驱动，定期压缩)

4. token_ratio >= light_token_ratio ──▶ trigger=token, mode=light
                                        (容量触发，轻量压缩)
```

### 5.2 压缩执行流程

```
compact_mid_run(conversation_id, trigger, mode)
    │
    ├──▶ 检查消息数量是否达到 min_total
    │
    ├──▶ 计算裁剪点: cut = total - keep_recent
    │
    ├──▶ 提取旧消息 + 旧摘要
    │
    ├──▶ ContextCompressor.merge_summary()
    │       │
    │       ├──▶ 提取 goal/constraints/decisions/artifacts
    │       │
    │       └──▶ 生成结构化摘要 v1
    │
    ├──▶ validate_consistency() ──▶ 一致性守护
    │
    ├──▶ UPSERT summaries 表
    │
    └──▶ 删除已裁剪消息 (id <= last_anchor_msg_id)
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
  ],
  "anchors": [
    {"msg_id": "xxx", "type": "constraint", "reason": "原因"}
  ]
}
```

## 6. 评估与判定

### 6.1 判定流程

```
task_finished 事件
        │
        ▼
EvalOrchestrator.evaluate(task_spec, run_outcome)
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
                └──▶ avg < threshold ──▶ partial
```

### 6.2 判定结果

| 条件 | final_status |
|------|-------------|
| 硬检查失败 | `fail` |
| 硬检查通过 + soft < 阈值 | `partial` |
| 硬检查通过 + soft >= 阈值 | `pass` |

## 7. 记忆收尾

### 7.1 _finalize_task_memory()

任务结束时强制执行：

```python
def _finalize_task_memory(self, task_id, run_id, task_status):
    # 1. 写入 postmortem 经验卡
    card_id = f"mem_task_{task_slug}_{run_slug}"
    card = {
        "card_id": card_id,
        "stage": "postmortem",
        "risk_level": "P1" if task_status == "error" else "P3",
        "payload": {...}
    }
    SystemMemoryStore.upsert_card(card)

    # 2. 追加记忆事件三连
    emit_event(task_id=task_id, event_type="memory_triggered")
    emit_event(task_id=task_id, event_type="memory_retrieved")
    emit_event(task_id=task_id, event_type="memory_decision_made")
```

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
| `context_compression_started` | 开始压缩 | trigger, mode |
| `context_compression_succeeded` | 压缩成功 | before, after |
| `context_compression_failed` | 压缩失败 | error |
| `verification_started` | 开始评估 | - |
| `verification_passed` | 评估通过 | verifier_results |
| `verification_failed` | 评估失败 | verifier_results |
| `task_finished` | 任务结束 | stop_reason, tool_failure_count |
| `task_judged` | 任务判定 | 完整 judgement |
| `memory_triggered` | 记忆触发 | card_id |
| `memory_retrieved` | 记忆检索 | query, count |
| `memory_decision_made` | 记忆决策 | decision |

## 9. 配置参数

### 9.1 运行时配置

```python
@dataclass
class RuntimeConfig:
    max_steps: int = 50          # 最大步数
    trace_steps: bool = True     # 是否打印追踪
    enable_llm_judge: bool = False  # 是否启用 LLM 评判
```

### 9.2 压缩配置

```python
@dataclass
class RuntimeCompressionConfig:
    enabled_mid_run: bool = True
    round_interval: int = 4              # 每 N 轮压缩一次
    light_token_ratio: float = 0.70      # 轻量压缩阈值
    strong_token_ratio: float = 0.82      # 强力压缩阈值
    context_window_tokens: int = 16000    # 上下文窗口大小
    keep_recent_turns: int = 8            # 保留最近 N 轮
    tool_burst_threshold: int = 3         # 连续工具调用阈值
    consistency_guard: bool = True        # 一致性守护
```

## 10. 入口点

| 入口 | 文件 | 说明 |
|------|------|------|
| `create_runtime()` | `app/core/bootstrap.py` | CLI Runtime 构造 |
| `RuntimeAgent` | `app/agent/runtime_agent.py` | 交互式 CLI |
| `BaseAgent` | `app/agent/agent.py` | 主 Agent 封装 |
| `SubAgent` | `app/agent/sub_agent.py` | 子 Agent 封装 |

## 11. 测试

- `tests/test_runtime_context_compression.py`：压缩触发、摘要结构、一致性守护
- `tests/test_runtime_eval_integration.py`：评估链路、记忆沉淀
