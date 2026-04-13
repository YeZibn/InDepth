# InDepth 架构参考

更新时间：2026-04-13

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           User / CLI / API                               │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         BaseAgent / RuntimeAgent                          │
│  - 组合系统指令（InDepth.md）                                             │
│  - 注入技能系统提示（Skills manager）                                     │
│  - 组装工具注册表                                                         │
│  - 启动 Runtime 执行循环                                                   │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          AgentRuntime                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ ModelProvider│  │ToolRegistry │  │MemoryStore  │  │   Eval      │    │
│  │             │  │             │  │             │  │Orchestrator │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐      ┌─────────────────────┐      ┌───────────────┐
│ Default Tools │      │   SubAgentManager    │      │   Observ.     │
│ - bash        │      │  - create/run/list   │      │   Events      │
│ - file r/w    │      │  - async parallel    │      │   JSONL       │
│ - search guard│      │  - role routing      │      │   postmortem  │
│ - todo        │      └─────────────────────┘      └───────────────┘
│ - time        │                  │
└───────────────┘                  ▼
                    ┌─────────────────────────────┐
                    │      SubAgent (角色隔离)     │
                    │  researcher / builder /     │
                    │  reviewer / verifier /       │
                    │  general                     │
                    └─────────────────────────────┘
```

## 2. 核心模块职责

### 2.1 AgentRuntime (`app/core/runtime/agent_runtime.py`)

**职责**：执行中枢，把对话请求转为可控循环

**关键流程**：
1. 组装消息（system + 历史 + user）
2. 调用 ModelProvider.generate()
3. 处理 finish_reason（stop/length/tool_calls）
4. 执行工具并回写消息
5. 任务结束触发评估与观测
6. 强制记忆沉淀 + 最终压缩

**关键状态**：
- `final_answer` / `task_status` / `stop_reason`
- `consecutive_tool_calls`
- `last_tool_failures`

### 2.2 ModelProvider (`app/core/model/http_chat_provider.py`)

**职责**：模型适配层，屏蔽不同模型 API 差异

**默认实现**：`HttpChatModelProvider`
- 接口：`POST <LLM_BASE_URL>/chat/completions`
- 默认重试：`max_retries=4`
- 退避：`retry_backoff_seconds=1.2`（指数退避）
- 默认超时：`timeout_seconds=120`
- 空 tools 时不发送 tools/tool_choice

### 2.3 ToolRegistry (`app/core/tools/registry.py`)

**职责**：工具的注册、发现与调用

**调用链**：
```
@tool(...) -> ToolFunction -> register_tool_functions() -> ToolRegistry.register()
                                                    -> ToolRegistry.invoke()
```

**invoke 结果约定**：
- 异常：`success=false, error=<exception>`
- `Error:` 字符串开头：视为失败
- JSON `{"success":false}`：视为失败
- 其余：`success=true, result=<output>`

### 2.4 MemoryStore (`app/core/memory/`)

**两条链路**：
1. `SQLiteMemoryStore`：Runtime 会话记忆（`db/runtime_memory_*.db`）
2. `SystemMemoryStore`：系统经验记忆（`db/system_memory.db`）

**压缩触发**（`_maybe_compact_mid_run`）：
1. token 使用比 >= `strong_token_ratio` -> `mode=strong`
2. 连续工具调用数 >= `tool_burst_threshold` -> `mode=light`
3. 轮次命中 `round_interval` -> `mode=light`
4. token 使用比 >= `light_token_ratio` -> `mode=light`

### 2.5 EvalOrchestrator (`app/eval/orchestrator.py`)

**职责**：区分"回答完成"与"任务完成"

**判定流程**：
1. 构建 verifier 链（deterministic + 可选 LLM judge）
2. 顺序执行，收集 `VerifierResult`
3. 硬失败优先：任一 `hard=true && passed=false` -> `fail`
4. 软检查：平均分 < 阈值 -> `partial`
5. 否则 `pass`

### 2.6 Observability (`app/observability/`)

**事件模型**：`EventRecord`
- `event_id/task_id/run_id/timestamp/actor/role/event_type/status/duration_ms/payload`

**落点**：
- JSONL：`app/observability/data/events.jsonl`
- SQLite：`db/system_memory.db`（仅 memory events）

## 3. 目录结构

```
app/
├── agent/                          # Agent 封装
│   ├── agent.py                    # BaseAgent
│   ├── sub_agent.py                # SubAgent
│   ├── runtime_agent.py            # CLI 入口
│   ├── create_skill_agent.py       # 技能创建 Agent
│   └── prompts/sub_agent_roles/    # 角色提示词模板
│
├── core/
│   ├── runtime/
│   │   └── agent_runtime.py         # 主循环
│   ├── model/
│   │   ├── base.py                 # ModelProvider 抽象
│   │   └── http_chat_provider.py   # HTTP 模型适配
│   ├── tools/
│   │   ├── decorator.py            # @tool 装饰器
│   │   ├── registry.py             # 工具注册表
│   │   ├── validator.py            # 参数校验
│   │   └── adapters.py             # 工具组装
│   ├── memory/
│   │   ├── sqlite_memory_store.py  # 会话记忆
│   │   ├── system_memory_store.py  # 系统记忆
│   │   └── context_compressor.py   # 压缩逻辑
│   ├── skills/
│   │   ├── factory.py              # skills manager 构建入口
│   │   ├── loaders.py              # 本地技能加载器
│   │   ├── manager.py              # 技能管理
│   │   └── skill.py                # 技能抽象
│   ├── bootstrap.py                # 初始化入口
│   └── config/
│       └── runtime_config.py       # 配置加载
│
├── tool/                           # 具体工具实现
│   ├── bash_tool.py
│   ├── read_file_tool.py
│   ├── write_file_tool.py
│   ├── get_current_time_tool.py
│   ├── search_tool/
│   │   ├── ddg_search_tool.py      # DuckDuckGo 搜索
│   │   ├── url_search_tool.py
│   │   └── search_guard.py         # 搜索门禁
│   ├── sub_agent_tool/
│   │   └── sub_agent_tool.py       # SubAgent 编排
│   └── todo_tool/
│       └── todo_tool.py            # 任务管理
│
├── eval/                           # 评估体系
│   ├── schema.py                   # 数据模型
│   ├── orchestrator.py             # 评估协调器
│   ├── verifiers/                 # Verifier 实现
│   │   ├── deterministic.py        # 确定性验证
│   │   └── llm_judge.py            # LLM 判官
│   └── agent/
│       └── verifier_agent.py       # 验证 Agent
│
├── observability/                  # 可观测性
│   ├── events.py                   # 事件发射
│   ├── store.py                    # 事件存储
│   ├── metrics.py                  # 指标聚合
│   ├── postmortem.py               # 复盘生成
│   └── trace.py                    # trace 构建
│
└── skills/                         # 项目内技能
    ├── memory-knowledge-skill/     # 记忆知识技能
    ├── ppt-skill/                 # PPT 生成技能
    └── skill-creator/              # 技能创建工具
```

## 4. 关键交互流程

### 4.1 任务执行流程

```
User Input
    │
    ▼
BaseAgent.chat()
    │
    ▼
AgentRuntime.run()
    │
    ├──▶ MemoryStore.get_recent_messages() ──▶ 加载历史
    │
    ▼
ModelProvider.generate(messages, tools)
    │
    ├──▶ finish_reason=stop ──▶ 返回 final_answer
    │
    ├──▶ finish_reason=length ──▶ 标记 stop_reason=length
    │
    └──▶ finish_reason=tool_calls
              │
              ▼
         ToolRegistry.invoke(name, args)
              │
              ▼
         emit_event(tool_succeeded/tool_failed)
              │
              ▼
         回写 tool 消息到 memory
              │
              ▼
         循环直到 stop/length/超过 max_steps
    │
    ▼
emit_event(task_finished)
    │
    ▼
EvalOrchestrator.evaluate()
    │
    ▼
emit_event(task_judged)
    │
    ▼
_finalize_task_memory() ──▶ SystemMemoryStore.upsert_card()
    │
    ▼
memory_store.compact_final()
```

说明：若本轮命中澄清状态（`awaiting_user_input`），运行时会先发 `verification_skipped` 并返回澄清问题；同一 `run_id` 在用户补充后通过 `run_resumed` 继续，不在该阶段触发 `task_judged`。

### 4.2 SubAgent 并行流程

```
create_sub_agent(name, description, task, role)
    │
    ├──▶ role routing（auto mode）
    │
    ▼
SubAgentManager.create() ──▶ AgentInstance(id, agent, role)
    │
    ▼
run_sub_agents_parallel(tasks_json)
    │
    ├──▶ asyncio.gather() ──▶ 线程池并行执行
    │
    ▼
返回 JSON 结果列表
```

## 5. 技术选型依据

### 5.1 为什么用 SQLite 做记忆存储？

- **轻量**：无需额外部署，适合本地 Agent 场景
- **持久化**：跨会话保留历史，支持复杂查询
- **事务**：写入安全，支持并发
- **可审计**：直接 SQL 查询，便于调试

### 5.2 为什么用 JSONL 做事件日志？

- **append-only**：高并发写入友好
- **可回放**：完整时间线可重建
- **可观测**：事后分析无需侵入业务代码

### 5.3 为什么用角色隔离 SubAgent？

- **职责清晰**：researcher/builder/reviewer/verifier 各司其职
- **工具隔离**：避免能力污染，减少误调用
- **可扩展**：新增角色只需添加 prompt 模板和工具集

## 6. 配置体系

### 6.1 环境变量（必填）

```bash
LLM_MODEL_ID         # 主模型 ID
LLM_MODEL_MINI_ID    # 轻量模型（压缩用）
LLM_API_KEY          # API Key
LLM_BASE_URL         # API 基础 URL
```

### 6.2 压缩配置（可选）

```bash
ENABLE_MID_RUN_COMPACTION=true
COMPACTION_ROUND_INTERVAL=4
COMPACTION_LIGHT_TOKEN_RATIO=0.70
COMPACTION_STRONG_TOKEN_RATIO=0.82
COMPACTION_CONTEXT_WINDOW_TOKENS=16000
COMPACTION_KEEP_RECENT_TURNS=8
COMPACTION_TOOL_BURST_THRESHOLD=3
COMPACTION_CONSISTENCY_GUARD=true
```

## 7. 扩展指南

### 7.1 添加新工具

1. 在 `app/tool/` 创建 `*_tool.py`
2. 使用 `@tool` 装饰器
3. 注册到 `build_default_registry()`

### 7.2 添加新角色

1. 在 `app/agent/prompts/sub_agent_roles/` 创建 `.md`
2. 在 `sub_agent_tool.py` 添加角色常量
3. 在 `SubAgent._build_tools()` 添加工具映射

### 7.3 添加新 Verifier

1. 继承 `VerifierBase`
2. 实现 `verify()` 方法
3. 在 `build_default_deterministic_verifiers()` 追加
