# InDepth Memory 总览

更新时间：2026-04-19

## 1. 这份文档的定位

这份文档只回答一件事：

当前 InDepth 的记忆系统到底分成哪几块，以及它们各自负责什么。

具体实现细节不再全部堆在这里，而是拆到三个独立 refer：

- [Runtime 会话记忆](./runtime-memory-reference.md)
- [System 经验记忆](./system-memory-reference.md)
- [User Preference 记忆](./user-preference-reference.md)

## 2. 三个记忆模块

| 模块 | 核心目标 | 存储 | 生命周期 | 典型内容 |
|------|----------|------|----------|----------|
| Runtime 会话记忆 | 管理当前 task 的上下文 | SQLite | task / run 内 | messages、summary、step 压缩事实 |
| System 经验记忆 | 沉淀跨任务可复用经验 | SQLite | 跨 task 长期存在 | memory card、recall_hint、经验卡片 |
| User Preference 记忆 | 记录用户个人偏好 | Markdown 单文件 | 跨 task 长期存在 | 语言偏好、回答风格、工具栈、兴趣 |

## 3. 边界划分

### 3.1 Runtime 会话记忆

属于“当前任务上下文管理”。

它解决的问题是：
- 当前 task 的历史消息怎么存
- 历史太长时怎么压缩
- 压缩时保留哪些 step
- 当前上下文预算怎么控制

它不负责：
- 跨任务经验复用
- 用户长期偏好沉淀

详情见：
- [Runtime 会话记忆](./runtime-memory-reference.md)

### 3.2 System 经验记忆

属于“跨任务经验卡片库”。

它解决的问题是：
- 某个任务结束后，是否值得沉淀成经验卡
- 新任务开始时，是否能召回过去经验
- 经验卡如何检索、如何轻量注入 prompt

它不负责：
- 保存完整会话历史
- 记录用户个人偏好

详情见：
- [System 经验记忆](./system-memory-reference.md)

### 3.3 User Preference 记忆

属于“用户画像 / 个人偏好层”。

它解决的问题是：
- 用户偏好什么语言、风格、表达方式
- 哪些偏好是显式声明，哪些来自 LLM 提取
- 偏好如何在新 task 开始时再次注入

它不负责：
- 保存任务经验卡
- 保存当前 task 的长对话历史

详情见：
- [User Preference 记忆](./user-preference-reference.md)

## 4. 三者如何协同

### 4.1 运行开始时

`AgentRuntime.run()` 会先组装当前 prompt：

1. 从 Runtime 会话记忆取最近消息与已有 summary
2. 注入 User Preference recall block
3. 注入 System Memory recall block
4. 再进入当前 step 的模型请求

### 4.2 运行过程中

Runtime 会话记忆持续写入：

- `user`
- `assistant`
- `tool`
- `tool_calls`
- `run_id / step_id`

同时根据预算触发压缩。

### 4.3 运行结束后

结束阶段会走两条长期链路：

1. System Memory finalize
   - 生成或更新经验卡
2. User Preference capture
   - 从当前用户输入里抽取明确偏好并写回

## 5. 现在推荐怎么理解

可以把三者理解成三个层次：

1. Runtime 会话记忆
   - 面向“当前 task 还能不能继续跑”
2. System 经验记忆
   - 面向“未来类似 task 能不能少走弯路”
3. User Preference 记忆
   - 面向“以后和这个用户协作时能不能更贴合”

## 6. 关键代码入口

总入口主要在：

- `app/core/runtime/agent_runtime.py`

三条链路各自的核心文件：

- Runtime 会话记忆
  - `app/core/memory/sqlite_memory_store.py`
  - `app/core/memory/context_compressor.py`
  - `app/core/memory/llm_context_compressor.py`
  - `app/core/runtime/runtime_compaction_policy.py`
  - `app/core/runtime/task_token_store.py`
- System 经验记忆
  - `app/core/memory/system_memory_store.py`
  - `app/core/runtime/system_memory_lifecycle.py`
  - `app/core/memory/recall_service.py`
  - `app/core/memory/memory_metadata_service.py`
- User Preference 记忆
  - `app/core/memory/user_preference_store.py`
  - `app/core/runtime/user_preference_lifecycle.py`

## 7. 阅读顺序建议

如果你想快速建立正确模型，建议按这个顺序看：

1. [Runtime 会话记忆](./runtime-memory-reference.md)
2. [System 经验记忆](./system-memory-reference.md)
3. [User Preference 记忆](./user-preference-reference.md)
