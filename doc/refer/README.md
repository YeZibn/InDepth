# InDepth 参考文档总索引

更新时间：2026-04-12

`doc/refer/` 目标：把"实现事实"沉淀为可查、可维护、可验证的工程参考，而不是概念说明。

## 1. 文档清单

- `architecture-reference.md`：系统整体架构图、核心模块设计、技术选型依据、组件交互流程。
- `runtime-reference.md`：`AgentRuntime` 主循环、收敛逻辑、评估与记忆收尾。
- `memory-reference.md`：运行时记忆压缩、结构化摘要、系统记忆卡与事件闭环。
- `tools-reference.md`：工具声明/注册/校验/调用链与默认工具全集。
- `eval-reference.md`：任务评估模型、verifier 链路、判定标准。
- `observability-reference.md`：事件模型、JSONL/SQLite 落盘、postmortem 生成。
- `agent-collaboration-reference.md`：主从 Agent 协同、角色路由、SubAgent 生命周期。
- `config-reference.md`：模型与压缩配置、环境变量与默认值。

## 2. 推荐阅读顺序

1. `architecture-reference.md`（概览）
2. `runtime-reference.md`
3. `tools-reference.md`
4. `memory-reference.md`
5. `eval-reference.md`
6. `observability-reference.md`
7. `agent-collaboration-reference.md`
8. `config-reference.md`

## 3. 代码主映射

- 架构核心：`app/core/runtime/agent_runtime.py` + `app/core/*`
- 工具体系：`app/core/tools/*` + `app/tool/*`
- 记忆体系：`app/core/memory/*`
- 评估体系：`app/eval/*`
- 可观测性：`app/observability/*`
- 主/子代理：`app/agent/agent.py` + `app/agent/sub_agent.py` + `app/tool/sub_agent_tool/sub_agent_tool.py`
