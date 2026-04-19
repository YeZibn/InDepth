# InDepth 参考文档总索引

更新时间：2026-04-19

`doc/refer/` 目标：把"实现事实"沉淀为可查、可维护、可验证的工程参考，而不是概念说明。

如果从整体运行逻辑理解这组参考文档，当前系统可以先抓一条主线：
1. Runtime 建立当前 task 的执行循环
2. 首轮模型请求前，Runtime 先执行 prepare phase；若存在 active todo，会先补一层基础现状扫描
3. prepare 会产出候选计划，并按结果自动完成 `plan_task` 落盘（create/update 由 Runtime 统一决定）
4. 工具调用推动业务执行、todo 绑定和状态流转
5. 若进入失败出口，Runtime 自动补齐 fallback，并触发单次 `LLM recovery assessment` 后再落地 recovery
6. 恢复优先围绕原 subtask 展开，必要时才派生 recovery subtasks
7. 结束时恢复信息继续外溢到 handoff、评估、观测和 postmortem

其中有一个新的现实约束需要注意：
1. 若本轮是从 `awaiting_user_input` 恢复，且存在 active todo，Runtime 会先把旧计划中未完成的 subtasks 标记为 `abandoned`
2. 然后再在同一个 todo 下继续追加新的计划

因此，阅读 `doc/refer/` 时可以把几个关键节点记住：
- `prepare phase`
- `current state scan`
- `plan_task`
- `task -> todo` 绑定
- `todo -> active subtask` 绑定
- `record_task_fallback`
- `update_task_status`
- `plan_task_recovery`
- `reopen_subtask`
- `finalization / task_finished / task_judged`

后面的各份参考文档，基本都是围绕这条主线，从不同层次展开。

## 1. 文档清单

- `architecture-reference.md`：系统整体架构图、核心模块设计、技术选型依据、组件交互流程。
- `runtime-reference.md`：`AgentRuntime` 主循环、收敛逻辑、评估与记忆收尾（含 Runtime CLI 单一 task 模式说明）。
- `prompt-reference.md`：Prompt 组装、运行时注入顺序、主/子 Agent 提示词来源。
- `memory-reference.md`：记忆系统总览，说明 Runtime / System / User Preference 三条链路的边界与协同。
- `runtime-memory-reference.md`：当前 task 的会话记忆、上下文压缩、step token ledger 与预算语义。
- `system-memory-reference.md`：跨任务经验卡、召回链路、finalize 沉淀与 recall 注入。
- `user-preference-reference.md`：用户偏好存储、提取、写回与 recall 注入。
- `tools-reference.md`：工具声明/注册/校验/调用链与默认工具全集。
- `todo-reference.md`：Todo 编排、subtask 设计、依赖流转、与 SubAgent 协作边界。
- `search-guard-reference.md`：检索门禁会话模型、预算控制、自动扩容与状态诊断。
- `skills-reference.md`：技能加载、`<skills_system>` 注入、技能访问工具与 Agent 默认差异。
- `eval-reference.md`：任务评估模型、verifier 链路、判定标准。
- `observability-reference.md`：事件模型、JSONL/SQLite 落盘、postmortem 生成。
- `agent-collaboration-reference.md`：主从 Agent 协同、角色路由、SubAgent 生命周期。
- `config-reference.md`：模型与压缩配置、环境变量与默认值。

## 2. 推荐阅读顺序

1. `architecture-reference.md`（概览）
2. `runtime-reference.md`
3. `prompt-reference.md`
4. `tools-reference.md`
5. `todo-reference.md`
6. `search-guard-reference.md`
7. `skills-reference.md`
8. `memory-reference.md`
9. `runtime-memory-reference.md`
10. `system-memory-reference.md`
11. `user-preference-reference.md`
12. `eval-reference.md`
13. `observability-reference.md`
14. `agent-collaboration-reference.md`
15. `config-reference.md`

## 3. 代码主映射

- 架构核心：`app/core/runtime/agent_runtime.py` + `app/core/*`
- 工具体系：`app/core/tools/*` + `app/tool/*`
- 记忆体系：`app/core/memory/*`（含 SQLiteMemoryStore、SystemMemoryStore、UserPreferenceStore）
- 评估体系：`app/eval/*`
- 可观测性：`app/observability/*`
- 主/子代理：`app/agent/agent.py` + `app/agent/sub_agent.py` + `app/tool/sub_agent_tool/sub_agent_tool.py`
- Runtime 会话记忆：`app/core/memory/sqlite_memory_store.py` + `app/core/runtime/task_token_store.py`
- System 经验记忆：`app/core/memory/system_memory_store.py` + `app/core/runtime/system_memory_lifecycle.py`
- 用户偏好：`app/core/memory/user_preference_store.py` + `app/core/runtime/user_preference_lifecycle.py` + `memory/preferences/user-preferences.md`
