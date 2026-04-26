# runtime-v2 当前架构与设计要点

更新时间：2026-04-21
目的：为下一版 runtime 重建提供“现状地图”，帮助先拆清边界，再决定哪些能力保留、重写或下沉。

## 1. 先给结论

当前实现已经不是单体脚本，但仍然带有明显的“运行时总控吃掉过多职责”的特征。

现状大致可以概括为：

1. `BaseAgent` / CLI 负责创建 runtime，并把任务输入送入 `AgentRuntime.run(...)`。
2. `AgentRuntime` 是真实主控，负责 prepare、执行循环、tool calling、收尾、验证、memory 沉淀、todo 上下文推进。
3. `ToolRegistry` + `app/tool/*` 提供执行能力，但不少 runtime 语义仍直接穿透到工具域。
4. `SQLiteMemoryStore`、system memory、user preference 形成了三套不同层级的记忆系统。
5. `EvalOrchestrator` 和 `observability` 已经具备独立子系统雏形，但仍由 runtime 在结束阶段强耦合触发。

因此，当前架构的问题不是“没有分层”，而是“已经开始分层，但 orchestration、policy、domain、infra 还没有完全切开”。

## 2. 当前代码里的真实分层

### 2.1 入口层

主要文件：

- `app/agent/runtime_agent.py`
- `app/agent/agent.py`
- `app/core/bootstrap.py`

职责：

1. 组装模型、工具注册表、skills、memory store、token store。
2. 创建 `AgentRuntime`。
3. 提供 CLI 命令与 task 生命周期入口。

现状判断：

1. 入口层相对清楚，主要问题不在这里。
2. `BaseAgent` 对 runtime 的封装偏薄，更多是“传参与状态记忆壳”。
3. 后续重建时，这层可以保留“装配器”角色，不必承担流程逻辑。

### 2.2 Runtime 编排层

主要文件：

- `app/core/runtime/agent_runtime.py`
- `app/core/runtime/runtime_stop_policy.py`
- `app/core/runtime/runtime_compaction_policy.py`
- `app/core/runtime/runtime_finalization.py`
- `app/core/runtime/tool_execution.py`
- `app/core/runtime/todo_session.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/core/runtime/system_memory_lifecycle.py`
- `app/core/runtime/user_preference_lifecycle.py`

职责：

1. 构造一次 run 的上下文。
2. 执行 prepare phase。
3. 驱动模型 step loop。
4. 接住 tool calls 并回写消息与事件。
5. 判定 stop reason / runtime state。
6. 执行 finalizing、verification、memory finalize。

现状判断：

1. 这是当前系统的心脏，也是最杂糅的地方。
2. 尽管已经拆出多个 lifecycle / policy 文件，但 `AgentRuntime` 仍然同时持有：
   - phase 状态机
   - message orchestration
   - todo 编排推进
   - prepare 自动建 todo
   - verification handoff 提取
   - runtime 结束后的并行 finalizer 调度
3. 也就是说，拆分已经发生，但主控类仍然是“上帝对象”。

### 2.3 Tool 能力层

主要文件：

- `app/core/tools/registry.py`
- `app/core/tools/adapters.py`
- `app/core/tools/validator.py`
- `app/tool/*`

职责：

1. 描述 tool schema。
2. 注册 tool handler。
3. 校验参数。
4. 执行工具并返回统一 `success/error/result` 结构。

现状判断：

1. 这一层已经比较像标准能力层。
2. 但默认工具集合中同时混入了：
   - 基础 IO / shell 工具
   - todo 编排工具
   - subagent 工具
   - search guard 工具
   - memory 查询工具
3. 这说明“能力注册”是统一的，但“能力域”还没有进一步模块化。

### 2.4 Todo 领域层

主要文件：

- `app/core/todo/models.py`
- `app/core/todo/service.py`
- `app/core/runtime/todo_session.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/tool/todo_tool/todo_tool.py`

职责：

1. 表达 todo 上下文、subtask 状态与执行阶段。
2. 从工具执行结果反推 active todo context。
3. 让 runtime 在 prepare / execute / resume 期间知道当前绑定的是哪个 todo、哪个 subtask。

现状判断：

1. Todo 已经是一个独立领域，但还没有完全摆脱 runtime。
2. 目前存在两层混合：
   - 领域层：`TodoContext`、`TodoService`
   - 运行时层：`TodoSession`、prepare-phase 自动应用 plan、binding warning
3. 说明 todo 既是业务对象，又被当成 runtime 驱动机制使用。

### 2.5 Memory 层

主要文件：

- `app/core/memory/sqlite_memory_store.py`
- `app/core/memory/system_memory_store.py`
- `app/core/memory/user_preference_store.py`
- `app/core/memory/context_compressor.py`
- `app/core/memory/recall_service.py`
- `app/core/runtime/system_memory_lifecycle.py`
- `app/core/runtime/user_preference_lifecycle.py`

职责：

1. Runtime Memory：保存消息、摘要、压缩结果。
2. System Memory：保存经验卡，并支持召回。
3. User Preference：保存长期偏好。

现状判断：

1. 三层记忆的意图是清楚的。
2. 真正杂糅的点在于“触发时机”和“领域归属”：
   - recall / capture 的触发时机写在 runtime lifecycle
   - 存储细节写在 memory 层
   - 注入方式直接改写 messages
3. 这导致 memory 既像基础设施，又像 prompt policy。

### 2.6 验证与观测层

主要文件：

- `app/eval/orchestrator.py`
- `app/eval/verifiers/*`
- `app/observability/events.py`
- `app/observability/store.py`
- `app/observability/postmortem.py`

职责：

1. 基于最终结果做 deterministic verifier + LLM judge。
2. 记录运行事件。
3. 生成 postmortem。

现状判断：

1. 这一层边界相对健康。
2. 问题主要不是模块内部，而是它们的触发权完全掌握在 runtime 手里。
3. 换句话说，它们是“独立子系统”，但不是“自治子系统”。

## 3. 当前主链路是怎么跑的

可简化为下面这条路径：

```text
CLI / BaseAgent
  -> build_agent_runtime_kwargs()
  -> AgentRuntime.run()
    -> 载入历史消息
    -> 恢复 active todo context
    -> 注入 user preference recall
    -> 注入 system memory recall
    -> prepare phase
      -> 扫描当前 todo 现状
      -> LLM 或规则生成准备结果
      -> 必要时自动调用 plan_task / update_task_status
    -> execute loop
      -> model generate
      -> tool_calls 则执行工具并回写消息
      -> stop / 非 stop finish_reason 收敛为 runtime_state
    -> finalizing pipeline
      -> 生成/提取 final handoff
      -> verification
      -> observability 终态事件
      -> system memory finalize
      -> user preference capture
      -> todo finalize
```

这里最重要的现实情况有两个：

1. prepare 已经不是“提示词前置说明”，而是一个实际会改状态、会自动调工具的阶段。
2. finalizing 也不是“拼一句总结”，而是 runtime 统一触发验证、记忆沉淀、收尾事件的总出口。

这两个阶段都已经变成一等流程节点，因此新版本应该明确建模，而不是继续藏在 `run()` 里。

## 4. 当前设计里真正值得保留的点

### 4.1 三阶段意识是对的

当前系统实际上已经在走：

1. `preparing`
2. `executing`
3. `finalizing`

这个方向是对的，因为它把“先建立执行入口”“中间执行”“最后交接验收”拆开了。下一版建议保留，而且进一步显式化成 phase engine。

### 4.2 Stop policy 独立出来是对的

`runtime_stop_policy.py` 的价值不只是代码拆小，而是把：

1. `finish_reason`
2. clarification 判定
3. runtime_state
4. stop_reason
5. final_answer fallback

统一收敛到了策略层。这个抽象值得保留。

### 4.3 Todo 作为执行骨架是对的

当前 todo 不只是一个“给用户看的列表”，它实际上承担了：

1. 任务拆分
2. 执行定位
3. 恢复挂起
4. subagent 编排落点
5. 任务状态可观测性

也就是说，todo 已经是 runtime 的 execution graph 雏形。下一版不一定还叫 todo，但一定要保留“显式执行骨架”这个能力。

### 4.4 验证与执行分离是对的

`EvalOrchestrator` 独立存在，这件事非常重要。因为“模型说完成了”和“系统判定完成了”本来就不应是同一件事。下一版建议继续保持。

### 4.5 事件流先于复盘是对的

当前 `emit_event(...)` 会在关键节点落盘，并触发 postmortem 生成。这给后续 debug、回放、评估提供了真实证据。这个能力不要丢。

## 5. 当前设计里最容易继续失控的点

### 5.1 Runtime 同时扮演了四种角色

`AgentRuntime` 当前同时是：

1. 会话编排器
2. phase 状态机
3. policy router
4. 部分领域服务的直接调用者

这会导致任何新功能都优先加到 runtime，而不是加到边界明确的域里。

### 5.2 Prepare phase 既做规划又做副作用

现在 prepare 会：

1. 分析任务是否需要 todo
2. 读取 active todo 状态
3. 自动废弃旧 subtasks
4. 自动调用 `plan_task`

这意味着 prepare 已经不是纯 planning，而是 planning + mutation。下一版要明确：

1. prepare 只产出 plan proposal
2. 还是 prepare 本身就允许 state transition

不能继续半显式半隐式。

### 5.3 Message 既是上下文，又是状态载体

当前很多信息是通过改写 messages 注入进去的，例如：

1. prepare message
2. system memory recall block
3. user preference recall block
4. tool execution transcript

这很灵活，但也意味着 runtime state 很多时候隐式编码在 prompt/message 中。下一版建议把“对模型可见的上下文”和“系统内部状态”分开。

### 5.4 Tool execution 与 runtime policy 仍然互相知道太多

例如 todo binding、plan_task guard、prepare auto-apply，本质上都说明 runtime 不只是调用工具，而是在理解工具语义。说明当前 tool 还不是纯 capability，而是带 workflow 语义的接口。

### 5.5 Memory trigger 仍然缺少统一总线

现在 system memory recall、user preference recall、capture 都已拆成模块，但触发时机仍是 runtime 手写。下一版建议把这些统一到 hook / event bus，而不是每种记忆都在 runtime 里串一次。

## 6. 适合重建版的建议边界

下面这个边界划分，比较适合下一版从头重构。

### 6.1 Orchestrator 层

只负责：

1. phase 切换
2. step loop 调度
3. 调用各 domain service / policy / infra adapter
4. 汇总终态

不要再直接承载具体策略。

### 6.2 Phase 层

建议拆成显式对象：

1. `PreparePhase`
2. `ExecutePhase`
3. `FinalizePhase`

每个 phase 只做自己的输入输出协议，不共享隐式局部状态。

### 6.3 Domain 层

至少拆清三个域：

1. `TaskGraphDomain`
   当前 todo/subtask/active binding 可以整体迁入这里。
2. `MemoryDomain`
   管理 recall、capture、preference、system memory policy。
3. `VerificationDomain`
   管理 run outcome、verifier chain、judgement。

### 6.4 Infra 层

包括：

1. model provider
2. tool registry / tool adapter
3. sqlite stores
4. vector index
5. event store

这一层只管能力，不表达业务策略。

## 7. 推荐的新版本设计原则

### 7.1 显式状态优先于隐式 prompt

像下面这些值，应该有正式状态结构，而不是只通过 message 注入表达：

1. 当前 phase
2. active task graph node
3. 当前暂停原因
4. recall decisions
5. verification handoff

### 7.2 Hook 优先于 if/else 拼接

当前 runtime 中很多生命周期能力是“这里插一段、那里插一段”。新版本更适合改成：

1. `before_prepare`
2. `after_prepare`
3. `before_model_call`
4. `after_tool_batch`
5. `before_finalize`
6. `after_verification`

这样 memory、observability、preference、recovery 都可以挂钩，而不是继续把主循环堆胖。

### 7.3 Task graph 优先于 todo 文件语义

现有 todo 文件可以继续作为落盘形式，但 runtime 内部模型建议升级成 task graph / execution graph。这样后面接：

1. subagent
2. 并行步骤
3. recover / retry
4. blocked / awaiting input

都会自然很多。

### 7.4 Handoff 是正式产物，不是附属文本

当前 finalizing 已经在逼近这个方向。新版本建议把 handoff 作为正式结构输出，供：

1. verifier
2. memory finalize
3. UI/CLI closeout
4. 后续 resume

共同消费。

## 8. 一份更适合 runtime-v2 的目标结构

```text
runtime-v2/
  README.md                      # 总览
  architecture/
    current-state.md             # 现状说明
    target-architecture.md       # 目标架构
    migration-boundaries.md      # 迁移边界
  orchestrator/
    runtime_orchestrator.py
    phase_engine.py
    run_context.py
  phases/
    prepare_phase.py
    execute_phase.py
    finalize_phase.py
  domains/
    task_graph/
    memory/
    verification/
  infra/
    model/
    tools/
    storage/
    observability/
```

不一定要完全照这个目录实现，但建议至少坚持两个原则：

1. “phase” 和 “domain” 不要混在一个文件里。
2. runtime 主类不要再直接依赖具体存储实现细节。

## 9. 如果现在就开始重建，建议先做什么

推荐顺序：

1. 先定义新的 `RunContext`、`PhaseResult`、`TaskGraphState`。
2. 再把 prepare / execute / finalize 三段变成显式 phase。
3. 然后把 todo 语义抽象成 task graph。
4. 再把 memory recall / capture 改造成 hooks。
5. 最后才迁移具体 tool、eval、observability 接线。

原因：

1. 当前最乱的不是工具本身，而是状态流。
2. 只要状态流不先改，任何模块拆分最后都会重新缠回 `AgentRuntime`。

## 10. 对这版代码的最终判断

这套现有实现已经完成了从“聊天代理”到“任务型 runtime”的关键跨越，尤其是：

1. prepare/execute/finalize 的意识已经建立。
2. todo 已经从提示性列表演变成执行骨架。
3. verification、observability、memory 已经成体系。

真正的问题不是“功能不够”，而是“这些能力都长出来了，但还共用一个总控脊柱”。  
所以下一版最重要的目标不是加更多功能，而是把状态机、领域语义和基础设施彻底解耦。

一句话总结：

当前版本适合作为“能力样本库”，不适合作为长期演进底座；`runtime-v2` 应该基于现有能力重建边界，而不是继续在 `AgentRuntime` 上叠逻辑。
