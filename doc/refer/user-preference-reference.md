# InDepth 用户偏好记忆参考

更新时间：2026-04-16

## 1. 定位

`UserPreferenceStore` 提供单层、单文件的 Markdown 格式用户偏好存储，用于持久化记录用户的显式声明和 LLM 提取的偏好信息。

与 System Memory 的区别：
- **UserPreferenceStore**：用户个人偏好（兴趣、角色、习惯等）
- **SystemMemoryStore**：任务经验、知识卡片、最佳实践

相关代码：
- `app/core/memory/user_preference_store.py` - 偏好存储实现
- `memory/preferences/user-preferences.md` - 默认存储文件

## 2. 架构图

### 2.1 模块架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        用户偏好记忆架构                                   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    UserPreferenceStore                            │   │
│  │                                                                  │   │
│  │  ┌───────────────────┐  ┌───────────────────┐                   │   │
│  │  │   _read_data()    │  │  _write_data()    │                   │   │
│  │  │   - 解析 Markdown │  │  - 渲染 Markdown  │                   │   │
│  │  │   - 提取元数据    │  │  - 原子写入       │                   │   │
│  │  └───────────────────┘  └───────────────────┘                   │   │
│  │                                                                  │   │
│  │  ┌───────────────────┐  ┌───────────────────┐                   │   │
│  │  │ upsert_preference │  │ list_preferences  │                   │   │
│  │  │                   │  │                   │                   │   │
│  │  │ 插入/更新偏好项   │  │ 列出所有偏好      │                   │   │
│  │  └───────────────────┘  └───────────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │              memory/preferences/user-preferences.md              │   │
│  │                                                                  │   │
│  │  # User Preferences                                              │   │
│  │  meta:                                                           │   │
│  │  - version: 1                                                    │   │
│  │  - updated_at: 2026-04-16T...                                    │   │
│  │  - enabled: true                                                 │   │
│  │                                                                  │   │
│  │  ## preferences                                                  │   │
│  │  ### interest_topics                                             │   │
│  │  - value: [编程, AI]                                             │   │
│  │  - source: llm_extract_v1                                        │   │
│  │  - confidence: 0.96                                              │   │
│  │  ...                                                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## 3. 数据模型

### 3.1 文件结构

```markdown
# User Preferences

meta:
- version: 1
- updated_at: 2026-04-16T00:36:16+08:00
- enabled: true

## preferences

### preference_key_name
- value: [值可以是列表或字符串]
- source: explicit_user | llm_extract_v1
- confidence: 0.95
- updated_at: 2026-04-16T00:36:16+08:00
- note: 证据或说明
```

### 3.2 PreferenceRecord 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | str | 偏好项标识符（如 `interest_topics`） |
| `value` | str/List[str] | 偏好值（字符串或列表） |
| `source` | str | 来源：`explicit_user`（用户显式）/ `llm_extract_v1`（LLM提取） |
| `confidence` | float | 置信度（0.0 ~ 1.0） |
| `updated_at` | str | ISO 8601 时间戳 |
| `note` | str | 备注/证据 |

### 3.3 Meta 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | int | 数据格式版本（当前为 1） |
| `updated_at` | str | 最后更新时间 |
| `enabled` | bool | 是否启用偏好记忆功能 |

## 4. API 详解

### 4.1 初始化

```python
from app.core.memory.user_preference_store import UserPreferenceStore

# 使用默认路径
store = UserPreferenceStore()

# 自定义路径
store = UserPreferenceStore(file_path="custom/path/preferences.md")
```

### 4.2 核心方法

#### `is_enabled() -> bool`
检查偏好记忆功能是否启用。

#### `set_enabled(enabled: bool) -> None`
启用或禁用偏好记忆功能。

#### `list_preferences() -> Dict[str, Dict[str, Any]]`
获取所有偏好项。

```python
prefs = store.list_preferences()
# 返回:
# {
#     "interest_topics": {
#         "value": ["编程", "AI"],
#         "source": "llm_extract_v1",
#         "confidence": 0.96,
#         "updated_at": "2026-04-16T00:36:16+08:00",
#         "note": "evidence=用户提到喜欢编程"
#     }
# }
```

#### `upsert_preference(key, value, source, confidence, note) -> None`
插入或更新偏好项。

```python
store.upsert_preference(
    key="job_role",
    value="程序员",
    source="explicit_user",  # 或 "llm_extract_v1"
    confidence=0.98,
    note="用户自我介绍"
)
```

#### `get_preference(key) -> Optional[Dict[str, Any]]`
获取单个偏好项。

```python
pref = store.get_preference("interest_topics")
```

#### `delete_preference(key) -> bool`
删除偏好项。

```python
store.delete_preference("old_preference")
```

## 5. 值类型处理

### 5.1 列表值

存储格式：`[item1, item2, item3]`

```python
# 写入列表
store.upsert_preference(
    key="interest_topics",
    value=["编程", "AI", "阅读"]
)

# 读取时自动解析为 Python list
```

### 5.2 字符串值

```python
store.upsert_preference(
    key="preferred_language",
    value="中文"
)
```

## 6. 使用场景

### 6.1 LLM 提取用户偏好

```python
# 在对话中检测到用户偏好时
store.upsert_preference(
    key="interest_topics",
    value=["编程"],
    source="llm_extract_v1",
    confidence=0.96,
    note="evidence=我很喜欢编程"
)
```

### 6.2 用户显式设置

```python
# 用户直接声明偏好
store.upsert_preference(
    key="job_role",
    value="程序员",
    source="explicit_user",
    confidence=1.0,
    note="用户自我介绍"
)
```

### 6.3 在 Agent 中使用

```python
# 在 BaseAgent 中集成
class BaseAgent:
    def __init__(self, ...):
        self.preference_store = UserPreferenceStore()
        
    def get_user_context(self) -> str:
        """获取用户偏好上下文用于注入提示词"""
        prefs = self.preference_store.list_preferences()
        if not prefs or not self.preference_store.is_enabled():
            return ""
        
        context_lines = ["## 用户偏好"]
        for key, record in prefs.items():
            value = record.get("value", "")
            if isinstance(value, list):
                value_str = ", ".join(value)
            else:
                value_str = str(value)
            context_lines.append(f"- {key}: {value_str}")
        
        return "\n".join(context_lines)
```

## 7. 文件存储特性

### 7.1 原子写入

使用 `write_text_atomic` 模式：
1. 写入临时文件 `.tmp`
2. 使用 `os.replace` 原子替换

避免写入过程中文件损坏。

### 7.2 自动初始化

文件不存在时自动创建：
- 创建父目录
- 写入默认结构（version=1, enabled=true, 空 preferences）

### 7.3 容错解析

解析失败时返回安全默认值：
- 空 preferences
- enabled=true
- version=1

## 8. 与 System Memory 的对比

| 维度 | UserPreferenceStore | SystemMemoryStore |
|------|---------------------|-------------------|
| **存储内容** | 用户个人偏好 | 任务经验、知识卡片 |
| **存储格式** | Markdown 单文件 | SQLite 数据库 |
| **数据来源** | 用户声明/LLM提取 | 任务执行沉淀 |
| **使用场景** | 个性化提示词注入 | 跨任务经验检索 |
| **生命周期** | 长期用户画像 | 任务级经验 |
| **置信度** | 有 | 无 |
| **来源追踪** | 有（source字段） | 无 |

## 9. 最佳实践

1. **偏好键命名**：使用 snake_case，如 `preferred_language`、`coding_style`
2. **置信度设置**：
   - 用户显式声明：`confidence=1.0`
   - LLM 提取：`confidence=0.7~0.95`（根据证据强度）
3. **note 字段**：记录证据原文，便于后续验证
4. **定期清理**：低置信度（<0.5）且长期未更新的偏好可考虑清理
5. **隐私注意**：敏感信息（如真实姓名、地址）应谨慎存储

## 10. 代码与测试映射

实现：
- `app/core/memory/user_preference_store.py`

测试：
- `tests/test_user_preference_store.py`
- `tests/test_user_preference_runtime.py`
