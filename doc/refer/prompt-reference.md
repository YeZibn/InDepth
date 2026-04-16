# Prompt 参考（实现事实）

更新时间：2026-04-16

本文档只描述当前代码中的 Prompt 组装与注入事实，不讨论抽象设计目标。

## 1. 总览

InDepth 的主链路 Prompt 由 `BaseAgent -> AgentRuntime` 共同完成：

1. `BaseAgent` 负责提供业务指令（`instructions`）与技能提示（`skill_prompt`）。
2. `AgentRuntime` 负责拼装最终 system prompt，并在运行时注入偏好/系统记忆召回块。
3. 模型实际收到的是 `messages` 列表，不是单一 prompt 字符串。

关键代码：
- `app/agent/agent.py`
- `app/core/runtime/agent_runtime.py`
- `app/agent/sub_agent.py`

## 2. 主 Agent Prompt 组装

### 2.1 BaseAgent 侧输入

`BaseAgent` 在初始化时会构造两类输入：

1. `instructions`
   - 当 `load_memory_knowledge=True` 时：`InDepth.md + 用户传入 instructions`
   - 否则仅使用用户传入 `instructions`
2. `skill_prompt`
   - 来自 `build_skills_manager(...).get_system_prompt_snippet()`

代码位置：
- `app/agent/agent.py`

### 2.2 Runtime 侧 system prompt

`AgentRuntime._build_system_prompt()` 的拼接顺序固定为：

1. `RUNTIME_SYSTEM_PROMPT`（运行时基础约束）
2. `self.system_prompt`（来自 BaseAgent 的 instructions）
3. `self.skill_prompt`（技能系统片段）

代码位置：
- `app/core/runtime/agent_runtime.py`（`RUNTIME_SYSTEM_PROMPT` 与 `_build_system_prompt`）

## 3. 运行时消息注入顺序

在每次 `run()` 开始时，`messages` 初始顺序是：

1. `system`: `_build_system_prompt()`
2. `history`: 最近历史消息（若启用 memory store）
3. `user`: 本轮用户输入

随后执行两步运行时注入：

1. `_inject_user_preference_recall(...)`
   - 若命中，会在第一条 `user` 消息前插入一条 `system` 偏好召回块
2. `_inject_system_memory_recall(...)`
   - 若命中，会追加系统记忆召回提示块（`system`）

因此，偏好不是直接写在 `BaseAgent.instructions` 内，而是运行时动态插入 `messages`。

代码位置：
- `app/core/runtime/agent_runtime.py`（`run`、`_inject_user_preference_recall`）

## 4. 用户偏好注入机制

用户偏好来源与开关：

1. 默认文件：`memory/preferences/user-preferences.md`
2. 默认开关：`ENABLE_USER_PREFERENCE_MEMORY=True`
3. 默认常驻 key：`language_preference,response_style`
4. 注入长度限制：`USER_PREFERENCE_MAX_INJECT_CHARS`（默认 240）

注入文本格式示例（由 `UserPreferenceStore.render_recall_block` 生成）：
- `用户偏好召回： language_preference=中文；response_style=简洁、结论先行。`

代码位置：
- `app/config/runtime_config.py`（`load_runtime_user_preference_config`）
- `app/core/memory/user_preference_store.py`（`render_recall_block`）

## 5. 子 Agent Prompt 组装

`SubAgent` 使用角色模板构造 system prompt：

1. 读取 `app/agent/prompts/sub_agent_roles/{role}.md`
2. 注入 `{role}`、`{task}`、`{extra_instructions}`
3. 作为 `AgentRuntime(system_prompt=...)` 输入
4. 额外挂载技能 `skill_prompt`

代码位置：
- `app/agent/sub_agent.py`

## 6. 运行时辅助 Prompt（非主 system prompt）

以下 Prompt 在运行时用于特定子流程，不等同于主对话 system prompt：

1. 澄清判定 Prompt
   - `CLARIFICATION_JUDGE_SYSTEM_PROMPT`
   - `CLARIFICATION_JUDGE_USER_PROMPT_TEMPLATE`
2. 偏好抽取 Prompt
   - `USER_PREFERENCE_EXTRACT_SYSTEM_PROMPT`
   - `USER_PREFERENCE_EXTRACT_USER_PROMPT_TEMPLATE`

代码位置：
- `app/core/runtime/agent_runtime.py`

## 7. 一页结论

1. `BaseAgent` 负责“提供素材”（instructions/skills），不直接做偏好动态注入。
2. `AgentRuntime` 负责“最终组装 + 运行时注入”。
3. 用户偏好注入发生在 `run()` 的 `messages` 级别，并位于当前 `user` 消息前。
4. 子 Agent 使用独立角色模板，与主 Agent 共用同一 Runtime 注入机制。
