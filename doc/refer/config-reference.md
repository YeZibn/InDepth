# InDepth 配置参考

更新时间：2026-04-13

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
| `COMPACTION_ROUND_INTERVAL` | `round_interval` | `4` | 每 N 轮压缩一次（最小 1） |
| `COMPACTION_LIGHT_TOKEN_RATIO` | `light_token_ratio` | `0.70` | 轻量压缩阈值（0~1） |
| `COMPACTION_STRONG_TOKEN_RATIO` | `strong_token_ratio` | `0.82` | 强力压缩阈值（0~1） |
| `COMPACTION_CONTEXT_WINDOW_TOKENS` | `context_window_tokens` | `16000` | 上下文窗口大小（最小 1024） |
| `COMPACTION_KEEP_RECENT_TURNS` | `keep_recent_turns` | `8` | 保留最近 N 轮（最小 1） |
| `COMPACTION_TOOL_BURST_THRESHOLD` | `tool_burst_threshold` | `3` | 连续工具调用阈值（最小 1） |
| `COMPACTION_CONSISTENCY_GUARD` | `consistency_guard` | `True` | 是否启用一致性守护 |

### 4.2 RuntimeCompressionConfig

```python
@dataclass
class RuntimeCompressionConfig:
    enabled_mid_run: bool = True
    round_interval: int = 4
    light_token_ratio: float = 0.70
    strong_token_ratio: float = 0.82
    context_window_tokens: int = 16000
    keep_recent_turns: int = 8
    tool_burst_threshold: int = 3
    consistency_guard: bool = True
```

### 4.3 解析规则

- **int/float 解析失败**：回退默认值
- **float 范围**：clamp 到 [0.0, 1.0]
- **int 范围**：clamp 到 [最小值, ∞)
- **bool 解析**：支持 `1/true/yes/y/on`（不区分大小写）

### 4.4 压缩触发条件

| 条件 | trigger | mode | 说明 |
|------|---------|------|------|
| `token_ratio >= strong_token_ratio` | `token` | `strong` | 强力压缩 |
| `consecutive_tool_calls >= tool_burst_threshold` | `event` | `light` | 事件触发 |
| `round % round_interval == 0` | `round` | `light` | 定期压缩 |
| `token_ratio >= light_token_ratio` | `token` | `light` | 容量触发 |

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

## 8. 调参建议

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

## 9. 配置消费地图

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

## 10. 测试映射

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_runtime_config.py` | 配置加载、默认值、解析规则 |
| `tests/test_model_provider.py` | Provider 请求、重试、超时 |
| `tests/test_compression_config.py` | 压缩配置、触发条件 |
| `tests/test_generation_config.py` | Generation 参数构建 |
