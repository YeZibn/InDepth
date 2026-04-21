# InDepth 参考文档总索引

更新时间：2026-04-21

`doc/refer/` 只描述当前实现事实，不再复述已经下线的失败恢复机制。

如果想先抓主线，可以按下面这条理解当前系统：
1. Runtime 恢复当前 task 上下文，并在首轮模型请求前执行 `prepare phase`
2. prepare 根据当前用户请求和 active todo 现状，决定是否启用 todo，并自动落 `plan_task`
3. executing 阶段围绕普通工具调用、todo 绑定和 subtask 状态流转推进
4. finalizing 阶段统一产出 final answer、verification handoff、评估结果、记忆与 postmortem

当前需要记住的关键节点：
- `prepare phase`
- `current state scan`
- `plan_task`
- `todo -> active subtask` 绑定
- `update_task_status`
- `update_subtask`
- `reopen_subtask`
- `finalization / task_finished / task_judged`

## 1. 文档清单

- `architecture-reference.md`：系统整体架构、核心模块职责与交互流程。
- `runtime-reference.md`：`AgentRuntime` 主循环、prepare/executing/finalizing 三阶段与收尾。
- `prompt-reference.md`：Prompt 组装、运行时注入顺序、主/子 Agent 提示词来源。
- `memory-reference.md`：记忆系统总览，说明 Runtime / System / User Preference 三条链路。
- `runtime-memory-reference.md`：当前 task 的会话记忆、上下文压缩、step token ledger 与预算语义。
- `system-memory-reference.md`：跨任务经验卡、召回链路、finalize 沉淀与 recall 注入。
- `user-preference-reference.md`：用户偏好存储、提取、写回与 recall 注入。
- `tools-reference.md`：工具声明/注册/校验/调用链与当前默认工具集。
- `todo-reference.md`：Todo 编排、subtask 设计、依赖流转、active todo/current state scan 与 SubAgent 协作边界。
- `subtask-status-reference.md`：Subtask 状态集合、状态迁移、`get_next_task` 选择逻辑与基础更新动作。
- `search-guard-reference.md`：检索门禁会话模型、预算控制、自动扩容与状态诊断。
- `skills-reference.md`：技能加载、`<skills_system>` 注入、技能访问工具与 Agent 默认差异。
- `eval-reference.md`：任务评估模型、verifier 链路、判定标准。
- `observability-reference.md`：事件模型、JSONL/SQLite 落盘、postmortem 生成。
- `agent-collaboration-reference.md`：主从 Agent 协同、角色路由、SubAgent 生命周期。
- `config-reference.md`：模型与压缩配置、环境变量与默认值。

## 2. 推荐阅读顺序

1. `architecture-reference.md`
2. `runtime-reference.md`
3. `prompt-reference.md`
4. `tools-reference.md`
5. `todo-reference.md`
6. `subtask-status-reference.md`
7. `search-guard-reference.md`
8. `skills-reference.md`
9. `memory-reference.md`
10. `runtime-memory-reference.md`
11. `system-memory-reference.md`
12. `user-preference-reference.md`
13. `eval-reference.md`
14. `observability-reference.md`
15. `agent-collaboration-reference.md`
16. `config-reference.md`

## 3. 代码主映射

- 架构核心：`app/core/runtime/agent_runtime.py` + `app/core/*`
- 工具体系：`app/core/tools/*` + `app/tool/*`
- 记忆体系：`app/core/memory/*`
- 评估体系：`app/eval/*`
- 可观测性：`app/observability/*`
- 主/子代理：`app/agent/*` + `app/tool/sub_agent_tool/*`
- Runtime 会话记忆：`app/core/memory/sqlite_memory_store.py` + `app/core/runtime/task_token_store.py`
- System 经验记忆：`app/core/memory/system_memory_store.py` + `app/core/runtime/system_memory_lifecycle.py`
- 用户偏好：`app/core/memory/user_preference_store.py` + `app/core/runtime/user_preference_lifecycle.py`
