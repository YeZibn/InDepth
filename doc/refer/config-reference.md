# InDepth 配置参考

更新时间：2026-04-15

## 1. 目标

配置层统一管理运行时所需的所有参数，包括模型配置、压缩配置和生成参数。

相关代码：
- `app/config/runtime_config.py` - 配置加载
- `app/core/model/http_chat_provider.py` - 模型配置消费
- `app/core/bootstrap.py` - 初始化入口
- `app/agent/agent.py` - Agent 配置

## 2. 架构图

### 2.1 配置架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           配置体系架构                                    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                       环境变量 (.env)                              │   │
│  │  LLM_MODEL_ID / LLM_API_KEY / LLM_BASE_URL / ...                │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   RuntimeConfigLoader                              │   │
│  │  - load_runtime_model_config()                                    │   │
│  │  - load_runtime_compression_config()                              │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│          ┌─────────────────────┼─────────────────────┐                │
│          ▼                     ▼                     ▼                │
│  ┌───────────────┐   ┌─────────────────┐   ┌───────────────┐       │
│  │RuntimeModel   │   │RuntimeCompression│  │Generation     │       │
│  │Config         │   │Config            │  │Config         │       │
│  │               │   │                  │  │               │       │
│  │- model_id    │   │- enabled_mid_run │  │- temperature │       │
│  │- api_key     │   │- round_interval  │  │- top_p       │       │
│  │- base_url    │   │- token_ratios    │  │- max_tokens  │       │
│  │- max_retries │   │- thresholds      │  │- ...         │       │
│  └───────┬───────┘   └─────────────────┘   └───────────────┘       │
│          │                     │                     │               │
│          ▼                     ▼                     ▼               │
│  ┌───────────────┐   ┌─────────────────┐   ┌───────────────┐       │
│  │ HttpChat      │   │ AgentRuntime    │   │ ModelProvider │       │
│  │ Provider      │   │ _maybe_compact  │   │ generate()    │       │
│  └───────────────┘   └─────────────────┘   └───────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 配置加载流程

```
应用启动
    │
    ▼
create_runtime() / create_agent()
    │
    ▼
load_runtime_model_config()
    │
    ├──▶ 检查 LLM_MODEL_ID (必填)
    ├──▶ 检查 LLM_API_KEY (必填)
    ├──▶ 检查 LLM_BASE_URL (必填)
    │
    ├─── 缺失任一 ──▶ ValueError
    │
    ▼
load_runtime_compression_config()
    │
    ├──▶ 读取环境变量
    ├──▶ 类型转换与校验
    └──▶ clamp 到合法区间
```

## 3. 模型配置（必填）

### 3.1 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_MODEL_ID` | ✅ | 主模型 ID |
| `LLM_MODEL_MINI_ID` | ❌ | 轻量模型（压缩用），为空时回退到 `LLM_MODEL_ID` |
| `LLM_API_KEY` | ✅ | API Key |
| `LLM_BASE_URL` | ✅ | API 基础 URL |

**验证规则**：
- 缺失任一必填项会抛出 `ValueError`
- 阻断 provider 初始化

### 3.2 RuntimeModelConfig

```python
@dataclass
class RuntimeModelConfig:
    model_id: str           # LLM_MODEL_ID
    model_mini_id: str     # LLM_MODEL_MINI_ID (回退到 model_id)
    api_key: str           # LLM_API_KEY
    base_url: str          # LLM_BASE_URL
    max_retries: int = 4  # 默认重试次数
```

## 4. 压缩配置（可选）

### 4.1 环境变量映射

| 环境变量 | 字段 | 默认值 | 说明 |
|----------|------|--------|------|
| `ENABLE_MID_RUN_COMPACTION` | `enabled_mid_run` | `True` | 是否启用运行时压缩 |
| `COMPACTION_ROUND_INTERVAL` | `round_interval` | `4` | 兼容保留配置（当前 mid-run 不使用 round 触发） |
| `COMPACTION_MIDRUN_TOKEN_RATIO` | `midrun_token_ratio` | `0.82` | mid-run 压缩阈值（0~1，兼容旧 `COMPACTION_STRONG_TOKEN_RATIO`） |
| `COMPACTION_CONTEXT_WINDOW_TOKENS` | `context_window_tokens` | `16000` | 上下文窗口大小（最小 1024） |
| `COMPACTION_KEEP_RECENT_TURNS` | `keep_recent_turns` | `8` | 预算不可用时的轮次兜底（最小 1） |
| `COMPACTION_TOOL_BURST_THRESHOLD` | `tool_burst_threshold` | `5` | 单次 `tool_calls` 条目阈值（最小 1） |
| `COMPACTION_CONSISTENCY_GUARD` | `consistency_guard` | `True` | 是否启用一致性守护 |
| `COMPACTION_TARGET_KEEP_RATIO_MIDRUN` | `target_keep_ratio_midrun` | `0.40` | midrun 压缩保留比例（0~1，兼容旧 `COMPACTION_TARGET_KEEP_RATIO_STRONG`） |
| `COMPACTION_TARGET_KEEP_RATIO_FINALIZE` | `target_keep_ratio_finalize` | `0.40` | finalize 压缩保留比例（0~1） |
| `COMPACTION_MIN_KEEP_TURNS` | `min_keep_turns` | `3` | 最小保留轮次数（最小 1） |
| `COMPACTION_COMPRESSOR_KIND` | `compressor_kind` | `auto` | 压缩器类型：`auto / rule / llm` |
| `COMPACTION_COMPRESSOR_LLM_MAX_TOKENS` | `compressor_llm_max_tokens` | `1200` | LLM 压缩器生成摘要时的 `max_tokens` |
| `COMPACTION_EVENT_SUMMARIZER_KIND` | `event_summarizer_kind` | `auto` | `event` 工具链替代摘要器类型：`auto / rule / llm` |
| `COMPACTION_EVENT_SUMMARIZER_MAX_TOKENS` | `event_summarizer_max_tokens` | `280` | `event` 工具链 mini 摘要生成 `max_tokens` |

### 4.2 RuntimeCompressionConfig

```python
@dataclass
class RuntimeCompressionConfig:
    enabled_mid_run: bool = True
    round_interval: int = 4
    midrun_token_ratio: float = 0.82
    context_window_tokens: int = 16000
    keep_recent_turns: int = 8
    tool_burst_threshold: int = 5
    consistency_guard: bool = True
    target_keep_ratio_midrun: float = 0.40
    target_keep_ratio_finalize: float = 0.40
    min_keep_turns: int = 3
    compressor_kind: str = "auto"
    compressor_llm_max_tokens: int = 1200
    event_summarizer_kind: str = "auto"
    event_summarizer_max_tokens: int = 280
```

补充说明：
- `COMPACTION_MIN_KEEP_TURNS` 表示压缩后至少保留最近多少轮原文上下文

### 4.2.1 压缩器选择规则

- `compressor_kind=auto`
  - 真实模型提供者：使用 `LLMContextCompressor`
  - `MockModelProvider`：自动退回 `ContextCompressor`
- `compressor_kind=rule`
  - 始终使用规则压缩
- `compressor_kind=llm`
  - 强制优先使用 LLM 压缩，但在模型报错、输出非合法 JSON、或一致性校验失败时回退到规则压缩

### 4.2.2 适用范围

- `midrun` 与 `finalize` 的摘要压缩路径支持 `rule / llm / auto`
- `event` 触发仍保持工具链替换压缩，但替代摘要生成支持独立的 `rule / llm / auto`

### 4.2.3 Event 摘要器选择规则

- `event_summarizer_kind=auto`
  - 真实模型提供者：优先使用 mini 模型生成工具链替代摘要
  - `MockModelProvider`：自动退回规则摘要
- `event_summarizer_kind=rule`
  - 始终使用规则替代摘要
- `event_summarizer_kind=llm`
  - 强制优先使用 LLM 生成替代摘要，但在模型报错、输出非合法 JSON、或 `summary` 为空时回退到规则摘要

### 4.2.1 Event 替换压缩安全默认值（SQLiteMemoryStore）

以下为 `SQLiteMemoryStore` 内建默认（非环境变量）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `keep_recent_event_tool_pairs` | `1` | 保留最近 1 个工具单元原文 |
| `event_stateful_tools` | `plan_task,get_next_task,update_task_status,init_search_guard` | 状态工具不参与 event 替换压缩 |

### 4.3 解析规则

- **int/float 解析失败**：回退默认值
- **float 范围**：clamp 到 [0.0, 1.0]
- **int 范围**：clamp 到 [最小值, ∞)
- **bool 解析**：支持 `1/true/yes/y/on`（不区分大小写）

### 4.4 压缩触发条件

| 条件 | trigger | mode | 说明 |
|------|---------|------|------|
| `token_ratio >= midrun_token_ratio` | `token` | `midrun` | 运行中 token 压缩 |
| `current_tool_calls_count >= tool_burst_threshold` | `event` | `event` | 事件触发（工具链替换压缩） |

## 5. GenerationConfig（运行时推理参数）

### 5.1 字段定义

```python
@dataclass
class GenerationConfig:
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[Union[str, List[str]]] = None
    seed: Optional[int] = None
    n: Optional[int] = None
    max_tokens: Optional[int] = None
    enable_thinking: Optional[bool] = None
    provider_options: Optional[Dict[str, Any]] = None
```

### 5.2 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `temperature` | float | 采样温度，越高越随机 |
| `top_p` | float | 核采样概率 |
| `presence_penalty` | float | 存在惩罚（-2.0 ~ 2.0） |
| `frequency_penalty` | float | 频率惩罚（-2.0 ~ 2.0） |
| `stop` | str/List | 停止序列 |
| `seed` | int | 随机种子 |
| `n` | int | 候选数量 |
| `max_tokens` | int | 最大生成 token 数 |
| `enable_thinking` | bool | 是否启用思考模式 |
| `provider_options` | dict | 供应商特定参数 |

### 5.3 请求体构建

`HttpChatModelProvider._build_payload()` 按"非 None 才下发"规则拼接：

```python
payload = {
    "model": self.config.model_id,
    "messages": formatted_messages,
}
if temperature is not None:
    payload["temperature"] = temperature
if top_p is not None:
    payload["top_p"] = top_p
# ... 其他参数同理
```

## 6. Provider 请求行为

### 6.1 HttpChatModelProvider

```python
class HttpChatModelProvider:
    def __init__(
        self,
        config: RuntimeModelConfig,
        timeout_seconds: int = 120,
        retry_backoff_seconds: float = 1.2,
    ):
        self.config = config
        self.timeout = timeout_seconds
        self.backoff = retry_backoff_seconds
        self.max_retries = config.max_retries
```

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 接口 | `POST <LLM_BASE_URL>/chat/completions` | OpenAI 兼容 |
| 默认重试 | `max_retries=4` | 指数退避 |
| 退避策略 | `retry_backoff_seconds=1.2` | 指数退避基数 |
| 默认超时 | `timeout_seconds=120` | 请求超时 |
| tools 为空 | 不发送 `tools/tool_choice` | 兼容部分 provider |

### 6.2 重试策略

```
请求失败
    │
    ├──▶ 检查是否在重试次数内
    │
    ├──▶ 是 ──▶ 等待 backoff * (1.2 ^ retry_count) 秒
    │         │
    │         └──▶ 重试
    │
    └──▶ 否 ──▶ 抛出异常
```

## 7. 主/子代理默认差异

### 7.1 BaseAgent vs SubAgent

| 配置项 | BaseAgent | SubAgent |
|--------|-----------|---------|
| `max_steps` | 100 | 25 |
| runtime memory DB | `db/runtime_memory_main_agent.db` | `db/runtime_memory_subagent_<role>.db` |
| `enable_llm_judge` | True | False |
| skills 来源 | 调用方传入 `skills`/`skill_paths` | 默认 `app/skills/memory-knowledge-skill` |
| skills 注入方式 | `<skills_system>` + 技能访问工具（有技能时） | `<skills_system>` + 技能访问工具 |

### 7.2 SubAgent 按角色差异

| 角色 | runtime memory DB |
|------|------------------|
| `general` | `db/runtime_memory_subagent_general.db` |
| `researcher` | `db/runtime_memory_subagent_researcher.db` |
| `builder` | `db/runtime_memory_subagent_builder.db` |
| `reviewer` | `db/runtime_memory_subagent_reviewer.db` |
| `verifier` | `db/runtime_memory_subagent_verifier.db` |

## 8. 澄清判定配置（运行时构造参数）

说明：以下参数目前是 `AgentRuntime(...)` 构造参数，不是环境变量。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enable_llm_clarification_judge` | real provider: `True`; `MockModelProvider`: `False` | 是否启用 LLM 澄清判定 |
| `clarification_judge_confidence_threshold` | `0.60` | LLM 判定为澄清的最小置信度阈值 |
| `enable_clarification_heuristic_fallback` | `True` | LLM 判定失败时是否回退启发式规则 |

判定规则：
1. `is_clarification_request=true && confidence>=threshold` 才进入 `awaiting_user_input`。
2. LLM 异常或输出非法时，按 fallback 策略回退到启发式判定。

## 9. 调参建议

### 8.1 压缩相关

| 问题 | 解决方案 |
|------|---------|
| 压缩触发过晚（length 频发） | 降低 `LIGHT_TOKEN_RATIO` 或 `ROUND_INTERVAL` |
| 压缩过度导致语义丢失 | 提高 `KEEP_RECENT_TURNS`，保持 `CONSISTENCY_GUARD=true` |
| 工具回合过密 | 调小 `TOOL_BURST_THRESHOLD` |

### 8.2 Provider 相关

| 问题 | 解决方案 |
|------|---------|
| 请求超时 | 提高 `timeout_seconds` |
| 频繁超时 | 降低 `max_retries` 或提高超时 |
| provider 兼容性问题 | 通过 `provider_options` 透传供应商特定参数 |

### 8.3 Generation 相关

| 场景 | 建议配置 |
|------|---------|
| 创意任务 | `temperature=0.8-1.0` |
| 确定性任务 | `temperature=0.0-0.3` |
| 平衡场景 | `temperature=0.5-0.7` |

## 10. 配置消费地图

```
RuntimeModelConfig
├── HttpChatModelProvider
│   └── _make_request() ──▶ POST /chat/completions
│
RuntimeCompressionConfig
├── AgentRuntime
│   └── _maybe_compact_mid_run()
│
GenerationConfig
├── BaseAgent.__init__()
├── SubAgent.__init__()
└── create_runtime()
```

## 11. 测试映射

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_runtime_config.py` | 配置加载、默认值、解析规则 |
| `tests/test_model_provider.py` | Provider 请求、重试、超时 |
| `tests/test_compression_config.py` | 压缩配置、触发条件 |
| `tests/test_generation_config.py` | Generation 参数构建 |
