# InDepth Agent 协同参考

更新时间：2026-04-13

## 1. 目标

Agent 协同层负责主从 Agent 的生命周期管理、角色路由与并行执行。

核心问题：
- 主 Agent 与 SubAgent 如何分工？
- SubAgent 角色体系如何设计？
- 如何实现并行执行？

相关代码：
- `app/agent/agent.py::BaseAgent` - 主 Agent
- `app/agent/sub_agent.py::SubAgent` - 子 Agent
- `app/tool/sub_agent_tool/sub_agent_tool.py` - SubAgent 编排
- `app/core/runtime/agent_runtime.py` - 统一执行内核

## 2. 架构图

### 2.1 Agent 协同架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Agent 协同架构                                   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                         BaseAgent (主 Agent)                      │   │
│  │                                                                  │   │
│  │  - 组合系统指令 (InDepth.md)                                      │   │
│  │  - 注入技能系统提示 (Skills manager)                              │   │
│  │  - 组装工具注册表                                                 │   │
│  │  - 启动 Runtime 执行循环                                           │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│         ┌──────────────────────┼──────────────────────┐                │
│         ▼                      ▼                      ▼                │
│  ┌───────────────┐    ┌─────────────────────┐   ┌───────────────┐     │
│  │  直接执行     │    │  SubAgent 编排       │   │  Tool 调用    │     │
│  │               │    │                     │   │               │     │
│  │ BaseAgent     │    │ SubAgentManager     │   │ create_task   │     │
│  │ 自带工具链    │    │                     │   │ capture_memory│     │
│  │               │    │  ┌─────────────┐   │   │ search_guard  │     │
│  │               │    │  │ create()   │   │   │               │     │
│  │               │    │  │ run_task() │   │   └───────────────┘     │
│  │               │    │  │ run_tasks_ │   │                        │
│  │               │    │  │ parallel() │   │                        │
│  │               │    │  └─────────────┘   │                        │
│  └───────────────┘    └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      SubAgentManager (编排层)                            │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     角色路由 (Role Routing)                         │   │
│  │                                                                  │   │
│  │  route_sub_agent_role(name, description, task)                    │   │
│  │         │                                                        │   │
│  │         ▼                                                        │   │
│  │  ┌─────────────────────────────────────────────────────────┐   │   │
│  │  │  reviewer ──▶ 审查、风险、回归                              │   │   │
│  │  │  verifier  ──▶ 验证、lint、typecheck                         │   │   │
│  │  │  researcher ──▶ 调研、搜索、资料                            │   │   │
│  │  │  builder   ──▶ 开发、写代码、修复                            │   │   │
│  │  │  general   ──▶ 默认                                          │   │   │
│  │  └─────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    实例管理 (Instance Management)                   │   │
│  │                                                                  │   │
│  │  instances: Dict[str, AgentInstance]                            │   │
│  │         │                                                        │   │
│  │         ├── agent_id_1: AgentInstance(idle)                     │   │
│  │         ├── agent_id_2: AgentInstance(running)                   │   │
│  │         └── agent_id_3: AgentInstance(completed)                 │   │
│  │                                                                  │   │
│  │  thread_pool: ThreadPoolExecutor(max_workers=10)                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        SubAgent (角色隔离)                                │
│                                                                         │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐              │
│  │  researcher   │  │    builder    │  │   reviewer    │              │
│  │               │  │               │  │               │              │
│  │ 工具:         │  │ 工具:         │  │ 工具:         │              │
│  │ - search      │  │ - bash        │  │ - read_file   │              │
│  │ - time        │  │ - read/write  │  │ - time        │              │
│  │ - read_file   │  │ - time        │  │ - memory      │              │
│  │ - memory      │  │               │  │               │              │
│  └───────────────┘  └───────────────┘  └───────────────┘              │
│                                                                         │
│  ┌───────────────┐  ┌───────────────┐                                 │
│  │   verifier    │  │   general     │                                 │
│  │               │  │               │                                 │
│  │ 工具:         │  │ 工具:         │                                 │
│  │ - bash        │  │ - bash        │                                 │
│  │ - time        │  │ - search      │                                 │
│  │ - read_file   │  │ - read/write  │                                 │
│  │ - memory      │  │ - time        │                                 │
│  └───────────────┘  └───────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 SubAgent 生命周期

```
create_sub_agent(name, description, task, role, ...)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  1. 角色规范化                                              │
│     - 非法 role ──▶ 回退 general                            │
│     - reviewer/verifier ──▶ 检查 acceptance_criteria       │
│       + output_format (必填)                                 │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 创建 SubAgent 实例                                      │
│     - 分配 agent_id                                         │
│     - 初始化 AgentInstance                                  │
│     - 状态: idle                                            │
│     - 挂载角色工具集                                         │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 事件发射                                                │
│     - emit_event(subagent_created)                          │
│     - emit_event(subagent_started)                          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 执行 Runtime.run()                                      │
│     - max_steps=25                                         │
│     - runtime memory: db/runtime_memory_subagent_<role>.db │
└─────────────────────────────────────────────────────────────┘
         │
         ├─── 成功 ──▶ emit_event(subagent_finished)
         │
         └─── 失败 ──▶ emit_event(subagent_failed)
```

### 2.3 并行执行流程

```
run_sub_agents_parallel(tasks_json)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  1. 解析任务列表                                             │
│     tasks_json ──▶ List[TaskSpec]                          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 批量创建 SubAgent                                       │
│     for task in tasks:                                     │
│         create_sub_agent(...)                               │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 线程池并行执行                                           │
│     with ThreadPoolExecutor(max_workers=10) as executor:   │
│         futures = [executor.submit(run_task, agent_id)       │
│                     for agent_id in agent_ids]             │
│         results = asyncio.gather(*futures)                 │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  4. 收集结果                                                │
│     return [                                                           │
│         {success, result/error, start_time, end_time},      │
│         ...                                                         │
│     ]                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 3. 主 Agent（BaseAgent）

### 3.1 职责

```
BaseAgent
├── 组合系统指令
│   └── InDepth.md (运行协议)
├── 注入技能系统提示
│   └── build_skills_manager(...).get_system_prompt_snippet()
├── 组装工具注册表
│   └── ToolRegistry + build_default_registry()
└── 启动 Runtime
    └── AgentRuntime.run()
```

### 3.2 默认配置

| 配置项 | 值 |
|--------|-----|
| `max_steps` | 100 |
| runtime memory DB | `db/runtime_memory_main_agent.db` |
| `enable_llm_judge` | True (可关) |

## 4. SubAgent 角色体系

### 4.1 角色枚举

| 角色 | 关键词 | 默认工具 |
|------|--------|---------|
| `general` | 默认 | bash, search guard, read/write, time |
| `researcher` | research, search, 检索, 搜索, 调研 | time, read_file, memory, search guard |
| `builder` | build, implement, fix, code, 写, 实现 | bash, time, read/write |
| `reviewer` | review, 审查, 评审, 风险, 回归 | time, read_file, memory |
| `verifier` | verify, 验证, test, lint, typecheck | bash, time, read_file, memory |

### 4.2 角色路由算法

```python
def route_sub_agent_role(name: str, description: str, task: str) -> str:
    text = " ".join([name or "", description or "", task or ""]).lower()

    reviewer_kw = ["review", "审查", "评审", "风险", "回归", "检查"]
    verifier_kw = ["verify", "验证", "test", "lint", "typecheck", "构建检查"]
    researcher_kw = ["research", "search", "检索", "搜索", "调研", "资料", "新闻"]
    builder_kw = ["build", "implement", "fix", "code", "写", "实现", "修改", "开发", "重构"]

    if any(k in text for k in reviewer_kw):
        return ROLE_REVIEWER
    if any(k in text for k in verifier_kw):
        return ROLE_VERIFIER
    if any(k in text for k in researcher_kw):
        return ROLE_RESEARCHER
    if any(k in text for k in builder_kw):
        return ROLE_BUILDER
    return ROLE_GENERAL
```

### 4.3 角色工具隔离

SubAgent._build_tools() 按角色挂载不同工具集：

| 角色 | time | bash | read | write | search | memory |
|------|------|------|------|-------|--------|--------|
| `general` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `researcher` | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| `builder` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| `reviewer` | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| `verifier` | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |

**额外**：所有 SubAgent 统一挂载技能访问工具（当前默认技能：`memory-knowledge-skill`）

## 5. SubAgentManager

### 5.1 核心接口

```python
class SubAgentManager:
    # 创建
    def create(
        self,
        name: str,
        description: str,
        task: str,
        role: str,
        acceptance_criteria: Optional[str] = None,
        output_format: Optional[str] = None,
    ) -> Dict

    # 执行
    def run_task(self, agent_id: str, message: str) -> Dict
    def run_task_async(self, agent_id: str, message: str) -> Dict
    def run_tasks_parallel(self, tasks_json: str) -> List[Dict]

    # 管理
    def list_all(self) -> List[Dict]
    def get_info(self, agent_id: str) -> Optional[Dict]
    def destroy(self, agent_id: str) -> bool
    def destroy_all(self) -> None
```

### 5.2 实例状态机

```
┌─────────┐   create    ┌─────────┐   run    ┌─────────┐
│ (不存在) │ ─────────▶ │  idle   │ ───────▶ │ running │
└─────────┘            └─────────┘          └────┬────┘
                            ▲                     │
                            │                     ▼
                      destroy              ┌─────────┐
                            │              │completed│ (正常结束)
                            │              └─────────┘
                            │                     │
                            │                     ▼
                      ┌─────────┐           ┌─────────┐
                      │ destroyed│ ◀────────│  error  │ (异常结束)
                      └─────────┘  destroy  └─────────┘
```

### 5.3 并发实现

- 线程池：`ThreadPoolExecutor(max_workers=10)`
- 并行聚合：`asyncio.gather()`
- 超时控制：可通过参数配置

## 6. 工具协议

### 6.1 创建 SubAgent

```python
create_sub_agent(
    name: str,
    description: str,
    task: str,
    role: str,  # researcher/builder/reviewer/verifier/general
    acceptance_criteria: Optional[str] = None,  # reviewer/verifier 必填
    output_format: Optional[str] = None,          # reviewer/verifier 必填
) -> Dict
```

**必填校验**：
- `reviewer` / `verifier` 必须附带 `acceptance_criteria` + `output_format`
- 缺失时返回错误

**返回格式**：
```json
{
  "success": true,
  "agent_id": "sub_<uuid>",
  "role": "researcher",
  "message": "SubAgent created successfully"
}
```

### 6.2 执行 SubAgent

```python
# 单体执行
run_sub_agent(agent_id: str, message: str) -> Dict

# 批量并行
run_sub_agents_parallel(tasks_json: str) -> List[Dict]
```

**tasks_json 格式**：
```json
[
  {
    "agent_id": "sub_xxx",
    "message": "执行任务描述"
  },
  {
    "agent_id": "sub_yyy",
    "message": "执行任务描述"
  }
]
```

**返回格式**：
```json
[
  {
    "agent_id": "sub_xxx",
    "success": true,
    "result": "执行结果",
    "start_time": "2024-01-01T10:00:00Z",
    "end_time": "2024-01-01T10:01:00Z",
    "duration_ms": 60000
  },
  {
    "agent_id": "sub_yyy",
    "success": false,
    "error": "错误信息",
    "start_time": "2024-01-01T10:00:00Z",
    "end_time": "2024-01-01T10:00:05Z",
    "duration_ms": 5000
  }
]
```

## 7. 协同事件

| 事件 | 说明 | 载荷 |
|------|------|------|
| `subagent_created` | SubAgent 创建 | agent_id, role, name |
| `subagent_started` | SubAgent 开始执行 | agent_id, role |
| `subagent_finished` | SubAgent 正常结束 | agent_id, role, duration_ms |
| `subagent_failed` | SubAgent 异常结束 | agent_id, role, error |

## 8. 与 InDepth 协议对齐

### 8.1 显式角色路由

- 禁止隐式 auto 角色推断
- 所有 SubAgent 必须显式指定 role

### 8.2 角色职责边界

| 角色 | 职责 |
|------|------|
| `reviewer` | 只审查与评审，不承担实现 |
| `verifier` | 只验证与测试，不承担实现 |
| `researcher` | 只调研与检索，不承担实现 |
| `builder` | 承担开发与实现 |

### 8.3 复杂任务拆分

```
复杂任务
    │
    ├──▶ 拆分为多个子任务
    │
    ├──▶ 并行创建 SubAgent 执行
    │
    └──▶ 主 Agent 汇总结果
```

## 9. 测试映射

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_main_agent.py` | BaseAgent 初始化、工具注册 |
| `tests/test_sub_agent_tool.py` | 创建、执行、并行、销毁 |
| `tests/test_sub_agent_role_tools.py` | 角色工具隔离 |
| `tests/test_sub_agent_manager.py` | 实例管理、状态机 |
| `tests/test_role_routing.py` | 角色路由算法 |
