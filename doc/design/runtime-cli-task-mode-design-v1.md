# InDepth Runtime CLI Task 模式改造设计 V1

## 1. 背景与问题

当前 `runtime_agent` 已对齐到底层 `BaseAgent`，但 CLI 交互仍偏“纯聊天流”，缺少显式的任务会话控制能力。

核心问题：
1. 用户无法在 CLI 中明确“结束当前任务并开启新任务”。
2. `task_id` 虽已具备实例级唯一性，但缺少面向用户的模式化入口。
3. 在复杂任务场景下，`chat` 与 `task` 两种使用意图未分层，导致上下文管理不直观。

## 2. 目标

本次仅改造 CLI 层，不改 Runtime 主循环协议。

目标：
1. 引入 `chat/task` 双模式。
2. 在 `task` 模式下，支持显式开启新任务，并结束之前任务上下文归属。
3. 保持底层统一走 `BaseAgent`，避免再次分叉独立 Runtime 实现。

## 3. 非目标

1. 不改 `AgentRuntime` 的 tool-calling 主循环。
2. 不在本次引入自动任务分类器（仅命令驱动切换）。
3. 不在本次增加 GUI 或 Web 控制面板。

## 4. 方案总览

### 4.1 技术基线

`runtime_agent.py` 继续作为 CLI 入口，但底层只负责：
1. 创建 `BaseAgent`（全量默认工具开启）。
2. 解析 slash 命令。
3. 将普通输入转发到 `agent.chat(...)`。

### 4.2 模式定义

1. `chat` 模式：默认模式，多轮自由对话。
2. `task` 模式：任务导向模式，允许显式切换任务边界。

### 4.3 命令定义（V1）

1. `/help`：显示命令列表。
2. `/mode chat`：切回聊天模式。
3. `/mode task [label]`：进入任务模式，并自动：
   - 结束当前任务（逻辑上停止继续复用旧 task_id）
   - 调用 `start_new_task(label or "task")` 开启新任务
4. `/task <label>`：仅在 task 模式可用，结束当前任务并开启下一任务。
5. `/newtask <label>`：`/task` 别名。
6. `/status`：显示当前模式与 `task_id`。
7. `/exit`：退出 CLI。

## 5. BaseAgent 对齐要求

依赖能力：
1. `BaseAgent.current_task_id`：读取当前任务 ID。
2. `BaseAgent.start_new_task(label)`：生成新 task_id，并重置澄清恢复态。

约束：
1. CLI 不直接操作 Runtime 内部状态。
2. 任务边界切换统一通过 `BaseAgent` 对外方法完成。

## 6. 当前实现状态

已完成：
1. `runtime_agent` 已改为底层复用 `BaseAgent`。
2. `BaseAgent` 增加唯一 task_id 生成策略。
3. `BaseAgent` 增加 `start_new_task(...)` 与 `current_task_id`。
4. CLI 已加入模式命令与任务切换逻辑。
5. CLI 命令单测已补齐（命令解析、模式切换、任务切换）。
6. README 已同步 CLI 命令说明。
7. 已增加 `/newtask` 作为 `/task` 别名。

## 7. 验收标准

功能验收：
1. 进入 `/mode task` 时，输出旧 task_id 与新 task_id。
2. 在 task 模式执行 `/task A` 后，`task_id` 必须变化。
3. 在 chat 模式执行 `/task A`，应提示先进入 task 模式。
4. 普通输入不受影响，仍可调用 `agent.chat(...)`。

回归验收：
1. `tests/test_main_agent.py` 全通过。
2. `runtime_agent` 相关测试全通过。

## 8. 风险与缓解

风险：
1. 用户误把命令当普通文本输入。
2. 模式切换后用户不清楚当前 task 边界。

缓解：
1. 未识别命令时返回明确提示并引导 `/help`。
2. 每次任务切换输出“已结束任务 + 新任务”。
3. `/status` 提供随时可查的当前状态。

## 9. 下一步建议

1. 后续可加“任务模板命令”，如 `/taskplan` 自动触发 todo 初始化。
2. 可增加 `/taskswitch <label>` 作为更语义化命令。
3. 可增加 `task` 模式下的 todo 自动初始化开关（可配置）。
