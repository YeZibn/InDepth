# InDepth Tools 参考

更新时间：2026-04-12

## 1. 模块范围

工具体系负责将原子能力封装为 Agent 可调用的函数，是 Agent 与外部世界交互的桥梁。

相关代码：
- `app/core/tools/decorator.py` - 声明层
- `app/core/tools/registry.py` - 注册层
- `app/core/tools/validator.py` - 校验层
- `app/core/tools/adapters.py` - 组装层
- `app/tool/*` - 实现层

## 2. 架构图

### 2.1 工具框架分层

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          工具框架分层架构                                  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        声明层 (@tool)                              │   │
│  │                                                                  │   │
│  │  @tool(                                                          │   │
│  │      name="xxx",                                                 │   │
│  │      description="...",                                          │   │
│  │      parameters={...}                                            │   │
│  │  )                                                               │   │
│  │      def xxx(...):                                               │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    ToolFunction 对象                             │   │
│  │  - name                                                          │   │
│  │  - description                                                   │   │
│  │  - entrypoint (实际函数)                                          │   │
│  │  - parameters (JSON Schema)                                       │   │
│  │  - stop_after_tool_call                                          │   │
│  │  - requires_confirmation                                         │   │
│  │  - cache_results                                                 │   │
│  │  - strict                                                        │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    注册层 (ToolRegistry)                          │   │
│  │                                                                  │   │
│  │  register_tool_functions([tool_func, ...])                        │   │
│  │         │                                                        │   │
│  │         ▼                                                        │   │
│  │  invoke(name, args) ──▶ ToolResult {success, result/error}       │   │
│  │         │                                                        │   │
│  │         ▼                                                        │   │
│  │  list_tool_schemas() ──▶ [schema, ...]                           │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    校验层 (validate_args)                        │   │
│  │                                                                  │   │
│  │  支持:                                                           │   │
│  │  - 基础类型: string/integer/number/boolean/object/array            │   │
│  │  - required/minimum/maximum/enum                                 │   │
│  │  - anyOf (object 分支)                                           │   │
│  │  - array items                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 工具调用流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                       工具调用完整流程                                  │
│                                                                      │
│  1. 模型返回 tool_calls                                              │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────┐                                                │
│  │ emit_event      │                                                │
│  │ (tool_called)   │                                                │
│  └────────┬────────┘                                                │
│           │                                                         │
│           ▼                                                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  ToolRegistry.invoke(name, args)                              │    │
│  │                                                              │    │
│  │  Step 1: 查找工具                                             │    │
│  │     └── 未找到 ──▶ return {success: false, error: "Unknown"} │    │
│  │                                                              │    │
│  │  Step 2: 参数校验 validate_args(schema, args)               │    │
│  │     └── 失败 ──▶ return {success: false, error: "validation"}│    │
│  │                                                              │    │
│  │  Step 3: 执行 handler(args)                                   │    │
│  │     ├── 正常 ──▶ 继续                                        │    │
│  │     └── 异常 ──▶ return {success: false, error: <exception>}│    │
│  │                                                              │    │
│  │  Step 4: 结果判定                                            │    │
│  │     ├── "Error:" 开头 ──▶ 视为失败                           │    │
│  │     ├── JSON {success:false} ──▶ 视为失败                    │    │
│  │     └── 其他 ──▶ return {success: true, result: <output>}    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│           │                                                         │
│           ▼                                                         │
│  ┌─────────────────┐                                                │
│  │ emit_event      │                                                │
│  │ (tool_succeeded │                                                │
│  │  or tool_failed)│                                                │
│  └────────┬────────┘                                                │
│           │                                                         │
│           ▼                                                         │
│  回写 messages:                                                     │
│  - role="tool"                                                      │
│  - content=json.dumps(result)                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 默认工具生态

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      默认工具生态 (build_default_registry)               │
│                                                                         │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌────────────┐ │
│  │   Bash Tool   │  │    Time      │  │   Read File  │  │Write File │ │
│  │               │  │   Tool       │  │    Tool      │  │   Tool    │ │
│  │ execute bash  │  │get_current_  │  │  read_file   │  │write_file │ │
│  │ commands      │  │time          │  │              │  │            │ │
│  └───────────────┘  └───────────────┘  └───────────────┘  └────────────┘ │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      Search Guard 工具组                         │   │
│  │                                                                  │   │
│  │  init_search_guard ──▶ guarded_ddg_search ──▶ update_search_    │   │
│  │       │                                    progress              │   │
│  │       │                                        │                │   │
│  │       ▼                                        ▼                │   │
│  │  get_search_guard_status          build_search_conclusion       │   │
│  │                                                                  │   │
│  │  request_search_budget_override                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      SubAgent 工具组                              │   │
│  │                                                                  │   │
│  │  create_sub_agent ──▶ run_sub_agent / run_sub_agents_parallel    │   │
│  │       │                                      │                  │   │
│  │       ▼                                      ▼                  │   │
│  │  list_sub_agents ──▶ get_sub_agent_info ──▶ destroy_sub_agent  │   │
│  │                                                                  │   │
│  │  destroy_all_sub_agents                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                       Todo 工具组                                 │   │
│  │                                                                  │   │
│  │  create_task ──▶ update_task_status                               │   │
│  │       │                     │                                    │   │
│  │       ▼                     ▼                                    │   │
│  │  list_tasks ──▶ get_next_task_item                               │   │
│  │       │                     │                                    │   │
│  │       ▼                     ▼                                    │   │
│  │  get_task_progress ──▶ generate_task_report                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      Memory 工具组                                │   │
│  │                                                                  │   │
│  │  capture_runtime_memory_candidate                                 │   │
│  │  search_memory_cards                                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## 3. 声明层详解

### 3.1 @tool 装饰器

`ToolFunction` 是工具的核心元数据结构：

```python
@dataclass
class ToolFunction:
    name: str                           # 工具唯一标识
    description: str                     # 工具描述（用于模型理解）
    entrypoint: Callable[..., Any]       # 实际执行的函数
    parameters: Optional[Dict[str, Any]] # JSON Schema 参数定义
    stop_after_tool_call: bool = False   # 执行后是否停止
    requires_confirmation: bool = False  # 是否需要确认
    cache_results: bool = False          # 是否缓存结果
    strict: bool = False                 # 严格模式
```

### 3.2 参数 Schema 示例

```python
@tool(name="read_file", description="读取文件内容")
def read_file(
    file_path: str,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> str:
    """读取文件内容，支持分页"""
    with open(file_path, "r") as f:
        if offset:
            f.seek(offset)
        if limit:
            return f.read(limit)
        return f.read()
```

自动生成的 parameters schema：
```json
{
  "type": "object",
  "properties": {
    "file_path": {"type": "string"},
    "limit": {"type": "integer"},
    "offset": {"type": "integer"}
  },
  "required": ["file_path"]
}
```

## 4. 注册层详解

### 4.1 ToolRegistry

```python
class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolFunction] = {}

    def register(self, tool_functions: List[ToolFunction]) -> None:
        """批量注册工具"""

    def invoke(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具并返回标准化结果"""

    def list_tool_schemas(self) -> List[Dict[str, Any]]:
        """列出所有工具的 JSON Schema（用于模型调用）"""
```

### 4.2 invoke 结果约定

| 条件 | 返回 |
|------|------|
| 工具未注册 | `{success: false, error: "Unknown tool"}` |
| 参数校验失败 | `{success: false, error: "Tool args validation failed", details: [...]}` |
| handler 抛异常 | `{success: false, error: <exception>}` |
| 返回 "Error:" 开头 | `{success: false, error: <内容>}` |
| 返回 JSON 字符串 `{success:false}` | `{success: false, error: <内容>}` |
| 返回 dict `{success:false}` | `{success: false, error: <内容>}` |
| 正常返回 | `{success: true, result: <output>}` |

## 5. 校验层详解

### 5.1 支持的校验规则

| 规则 | 说明 | 示例 |
|------|------|------|
| `type` | 基础类型 | `string/integer/number/boolean/object/array` |
| `required` | 必填字段 | `["name", "path"]` |
| `minimum` | 数值最小值 | `{"minimum": 0}` |
| `maximum` | 数值最大值 | `{"maximum": 100}` |
| `enum` | 枚举值 | `{"enum": ["a", "b", "c"]}` |
| `anyOf` | 联合类型 | 分支 object schema |

### 5.2 校验失败返回

```json
{
  "success": false,
  "error": "Tool args validation failed",
  "details": [
    {"field": "path", "message": "required field missing"},
    {"field": "limit", "message": "must be >= 0"}
  ]
}
```

## 6. 默认工具详解

### 6.1 Bash Tool

```python
@tool(name="bash", description="执行 Bash 命令")
def bash(command: str, cwd: Optional[str] = None, timeout: int = 60) -> str:
    """在指定目录执行命令，返回输出"""
```

**特性**：
- 支持自定义工作目录
- 支持超时控制
- 返回 stdout/stderr 合并结果

### 6.2 File Tools

```python
@tool(name="read_file", description="读取文件内容")
def read_file(
    file_path: str,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> str

@tool(name="write_file", description="写入文件内容")
def write_file(
    file_path: str,
    content: str,
    mode: str = "w"  # w:覆盖, a:追加
) -> Dict
```

### 6.3 Search Guard 工具组

Search Guard 是检索类任务的门禁系统，确保时效性信息检索的质量：

```python
# 初始化门禁
init_search_guard(
    time_basis: str,          # 时间基准: "UTC+8, 2024-12-25 23:59"
    questions_json: str,       # 待回答的核心问题 (3-5个)
    stop_threshold: str,       # 停止阈值定义
    max_rounds: int = 3,       # 最大检索轮次
    max_seconds: int = 600     # 最大检索时间
)

# 执行检索 (需先 init)
guarded_ddg_search(query: str, num_results: int = 10) -> List[Dict]

# 更新进度
update_search_progress(round: int, found: int, coverage: str)

# 获取状态
get_search_guard_status() -> Dict

# 请求追加预算
request_search_budget_override(reason: str, additional_rounds: int) -> Dict

# 生成结论
build_search_conclusion(conclusions: List[Dict], gaps: List[str]) -> Dict
```

**门禁流程**：
```
init_search_guard() ──▶ 检查门禁状态
         │
         ▼
guarded_ddg_search() ──▶ 检查预算
         │
         ├─── 预算耗尽 ──▶ 返回阻断错误
         │
         ▼
update_search_progress() ──▶ 检查停止阈值
         │
         ├─── 满足阈值 ──▶ 可提前停止
         │
         ▼
build_search_conclusion() ──▶ 生成结构化结论
```

### 6.4 SubAgent 工具组

详见 [agent-collaboration-reference.md](agent-collaboration-reference.md)

### 6.5 Todo 工具组

```python
# 创建任务
create_task(
    task_name: str,
    context: str,
    split_reason: str,  # 顶层拆分理由，必填
    subtasks: List[Dict[str, Any]]  # [{name, description, split_reason?, dependencies?, priority?}] 必填
) -> Dict

# 更新状态
update_task_status(
    todo_id: str,
    subtask_number: int,
    status: str  # pending/in-progress/completed
) -> Dict

# 查询任务
list_tasks() -> List[Dict]
get_next_task_item(todo_id: str) -> Dict
get_task_progress(todo_id: str) -> Dict

# 生成报告
generate_task_report(todo_id: str) -> str
```

**文件结构**：`todo/<timestamp>_<sanitized_name>.md`
**标识规范**：
- Todo 领域统一使用 `todo_id`
- `create_task` 返回 `todo_id`
- `list_tasks` 返回项包含 `todo_id`

**状态机**：
```
pending ──▶ in-progress ──▶ completed
    │            │
    │<───────────┘ (依赖未满足时禁止推进)
```

### 6.6 Memory 工具组

```python
# 捕获候选记忆
capture_runtime_memory_candidate(
    task_id: str,
    run_id: str,
    title: str,
    observation: str,
    stage: Optional[str] = "lifecycle",
    tags: Optional[List[str]] = None,
) -> Dict

# 查询记忆
search_memory_cards(
    query: str,
    stage: Optional[str] = None,
    limit: int = 5,
) -> Dict
```

## 7. 角色工具隔离

SubAgent 按角色挂载不同工具集：

| 角色 | 可用工具 |
|------|---------|
| `researcher` | 时间、读文件、记忆检索、search guard |
| `builder` | bash、时间、读写文件 |
| `reviewer` | 时间、读文件、记忆检索 |
| `verifier` | bash、时间、读文件、记忆检索 |
| `general` | bash、search guard、读写文件、时间 |

## 8. 工具相关事件

| 事件 | 说明 | 载荷 |
|------|------|------|
| `tool_called` | 工具被调用 | name, arguments |
| `tool_succeeded` | 工具成功 | name, result |
| `tool_failed` | 工具失败 | name, error |
| `search_guard_initialized` | 检索门禁初始化 | config |
| `search_round_started` | 检索轮次开始 | round |
| `search_round_finished` | 检索轮次结束 | round, found |
| `search_stopped` | 检索停止 | reason |

## 9. 测试映射

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_main_agent.py` | 主 Agent 工具注册 |
| `tests/test_sub_agent_role_tools.py` | 角色工具隔离 |
| `tests/test_sub_agent_tool.py` | reviewer/verifier 创建门禁 |
| `tests/test_tool_registry.py` | 注册与调用 |
| `tests/test_tool_validation.py` | 参数校验 |
