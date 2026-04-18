# InDepth 参考文档总索引

更新时间：2026-04-18

`doc/refer/` 目标：把"实现事实"沉淀为可查、可维护、可验证的工程参考，而不是概念说明。

如果从整体运行逻辑理解这组参考文档，当前系统可以先抓一条主线：
1. Runtime 建立当前 task 的执行循环
2. 首轮模型请求前，Runtime 先执行 prepare phase，并按结果自动完成 `plan_task` 落盘
3. 工具调用推动业务执行、todo 绑定和状态流转
4. 若进入失败出口，Runtime 自动补齐 fallback，并触发单次 `LLM recovery assessment` 后再落地 recovery
5. 恢复优先围绕原 subtask 展开，必要时才派生 recovery subtasks
6. 结束时恢复信息继续外溢到 handoff、评估、观测和 postmortem

因此，阅读 `doc/refer/` 时可以把几个关键节点记住：
- `prepare phase`
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
- `memory-reference.md`：运行时记忆压缩、结构化摘要、系统记忆卡与事件闭环。
- **`user-preference-reference.md`：用户偏好记忆存储、API 与使用场景（新增）。**
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
9. **`user-preference-reference.md`（新增）**
10. `eval-reference.md`
11. `observability-reference.md`
12. `agent-collaboration-reference.md`
13. `config-reference.md`

## 3. 代码主映射

- 架构核心：`app/core/runtime/agent_runtime.py` + `app/core/*`
- 工具体系：`app/core/tools/*` + `app/tool/*`
- 记忆体系：`app/core/memory/*`（含 SQLiteMemoryStore、SystemMemoryStore、**UserPreferenceStore**）
- 评估体系：`app/eval/*`
- 可观测性：`app/observability/*`
- 主/子代理：`app/agent/agent.py` + `app/agent/sub_agent.py` + `app/tool/sub_agent_tool/sub_agent_tool.py`
- 用户偏好：`app/core/memory/user_preference_store.py` + `memory/preferences/user-preferences.md`
