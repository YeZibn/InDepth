# runtime-v2 全量讨论板块整理（V1）

更新时间：2026-04-21  
状态：Draft

## 1. 目的

这份文档用于整理当前项目在重建 `runtime-v2` 时需要讨论的完整板块，避免后续讨论只盯着 `AgentRuntime` 本体，而漏掉 prompt、tools、memory、subagent、verification、observability 等实际会反向影响主架构的部分。

这不是最终架构方案，而是一张“全项目讨论地图”。

为了方便后续正式落地，本文中的子任务统一按“可交付产物”来定义。默认每个子任务都应至少产出以下其中之一：

1. 一份设计决策文档。
2. 一组稳定的数据结构或接口定义。
3. 一份迁移方案或兼容策略。
4. 一组实现任务的拆分边界。

## 2. 板块总览

建议将当前项目拆成以下 12 个板块来讨论：

1. Prompt 编排层
2. 入口与宿主层
3. Runtime 主编排层
4. 状态模型层
5. 任务编排与执行图层
6. Tool 系统层
7. 模型与推理接入层
8. 记忆系统层
9. Skills 与扩展能力层
10. SubAgent 协作层
11. 验证、判定与收尾层
12. 观测、复盘与工程化层

## 3. 各板块说明

### 3.1 Prompt 编排层

这一层是系统的行为入口定义层，决定模型在不同阶段看到什么、如何被约束、以及结构化输出协议如何形成。

当前主要对应：

- `InDepth.md`
- runtime 内部 system prompt
- prepare / execute / finalize phase prompt
- structured handoff 协议
- subagent role prompts

这一板块需要讨论：

1. v2 中 prompt 还是不是 runtime 的一等控制面。
2. prepare / execute / finalize 是否继续通过 prompt 显式驱动。
3. handoff 是否仍要求模型生成结构化协议。
4. prompt 编排与运行时状态机之间如何解耦。
5. skill prompt、memory recall prompt、preference prompt 如何进入上下文。

落地子任务：

1. 输出一份 prompt 资产清单，覆盖 system prompt、phase prompt、role prompt、memory 注入 prompt 的来源、用途和当前挂载位置。
2. 输出一份 prompt 分层设计，明确 base prompt、phase prompt、dynamic injection、role prompt 的边界。
3. 明确 structured handoff 在 v2 中的保留策略，并沉淀成正式协议说明。
4. 定义 prompt 编排层与 runtime state 的边界规则，禁止继续通过消息文本隐式携带关键状态。
5. 产出一份 prompt 迁移方案，说明现有 prompt 如何迁移到 v2 结构。

### 3.2 入口与宿主层

这一层定义系统如何启动、如何持有 runtime、如何承接一个任务会话。

当前主要对应：

- `app/agent/agent.py`
- `app/agent/runtime_agent.py`
- `app/core/bootstrap.py`
- CLI 命令入口

这一板块需要讨论：

1. v2 的宿主对象是什么。
2. runtime core 和 agent shell 是否继续分离。
3. `task_id`、`run_id`、session 标识如何定义。
4. 新任务、恢复任务、澄清后续跑是否共用统一入口。
5. CLI 是否只是一个壳，还是仍然带部分流程语义。

落地子任务：

1. 输出一份入口层职责清单，明确 CLI、BaseAgent、bootstrap 当前分别承担什么。
2. 设计 v2 的 runtime host 接口，形成正式的宿主层接口草案。
3. 定义统一的任务标识模型，明确 `task_id`、`run_id`、`session_id` 的语义与生命周期。
4. 定义新任务启动、恢复执行、澄清恢复的统一入口协议。
5. 产出 CLI 保留/收缩方案，明确 CLI 在 v2 中是流程宿主还是纯壳层。

### 3.3 Runtime 主编排层

这一层是一次 run 的真实控制中心。

当前主要对应：

- `app/core/runtime/agent_runtime.py`
- `runtime_stop_policy.py`
- `runtime_compaction_policy.py`
- `runtime_finalization.py`
- `tool_execution.py`

这一板块需要讨论：

1. v2 的 runtime 核心对象是什么。
2. phase engine 是否独立成正式结构。
3. step loop 的最小职责是什么。
4. 哪些能力必须留在 orchestrator，哪些必须外移。
5. finalizing 是 runtime 的一部分，还是挂在外部 pipeline。

落地子任务：

1. 输出当前 `AgentRuntime` 职责拆解表，按 orchestration、policy、domain、infra 四类归档。
2. 定义 v2 主控对象及其职责边界，形成 runtime orchestrator 设计稿。
3. 定义 phase engine 的正式接口，明确 prepare / execute / finalize 的输入输出协议。
4. 定义 step loop 的最小职责集合，形成不可回流约束。
5. 产出 finalizing pipeline 与主循环的衔接设计。

### 3.4 状态模型层

这一层定义系统内部真正的状态对象，是重建时最应该先定的一层。

当前相关状态分散在：

- runtime state
- stop reason
- todo context
- active subtask
- pause / resume 状态
- verification handoff
- memory 注入状态

这一板块需要讨论：

1. v2 需要哪些显式状态对象。
2. 哪些状态是内部态，哪些可以对外暴露。
3. message 与 state 如何彻底分开。
4. 是否引入正式的 `RunContext`、`PhaseState`、`ExecutionState`。
5. clarification、paused、partial、completed 的状态语义如何统一。

落地子任务：

1. 输出当前状态字段总表，覆盖 runtime、todo、verification、memory、pause/resume 等状态。
2. 定义 v2 的核心状态对象集合，例如 `RunContext`、`PhaseState`、`TaskGraphState`。
3. 产出 runtime state、stop reason、phase state 的统一状态图。
4. 定义内部状态、外部暴露状态、事件态、handoff 态的分层规则。
5. 产出 message 与 state 解耦方案，明确哪些状态不允许再通过 prompt 文本编码。

### 3.5 任务编排与执行图层

这一层当前主要由 todo 语义承载，但本质上已经接近 execution graph。

当前主要对应：

- `app/core/todo/*`
- `app/core/runtime/todo_session.py`
- `app/core/runtime/todo_runtime_lifecycle.py`
- `app/tool/todo_tool/todo_tool.py`
- `todo/` 目录下的任务文件

这一板块需要讨论：

1. v2 是否继续沿用 todo 概念。
2. 最小执行单元是 task、subtask、node 还是 step。
3. 如何表达串行、并行、阻塞、等待用户输入、恢复执行。
4. plan / update / reopen / append 的模型是否保留。
5. subagent 是否直接挂在执行图上。

落地子任务：

1. 输出当前 todo 体系用途分析，区分用户可见语义与 runtime 内部执行语义。
2. 决定 v2 保留 todo 还是升级为 task graph / execution graph，并形成命名决策。
3. 定义最小执行单元的数据结构和状态集合。
4. 定义执行图如何表达串行、并行、blocked、awaiting_input、resume。
5. 明确 subagent、search、verification 等动作在执行图中的挂载方式。

### 3.6 Tool 系统层

这一层定义能力如何被声明、注册、校验、调用和回传。

当前主要对应：

- `app/core/tools/*`
- `app/tool/*`
- registry / validator / adapter

当前涉及的工具子域包括：

1. 基础执行工具
2. 搜索工具
3. todo 工具
4. subagent 工具
5. memory 工具

这一板块需要讨论：

1. tool 是纯 capability，还是允许带 workflow 语义。
2. tool 返回协议是否统一。
3. runtime 是否应该理解具体 tool 语义。
4. 默认工具集是否按域拆分。
5. tool 调用结果如何进入状态流与观测链路。

落地子任务：

1. 输出当前工具全量分类表，按 capability、workflow、orchestration 三类归档。
2. 定义 v2 的统一 tool request / tool result 协议。
3. 明确 runtime 与工具语义的耦合策略，形成感知白名单或完全解耦方案。
4. 定义工具分域结构，例如 execution、search、task-graph、memory、subagent。
5. 定义 tool call 进入状态流、事件流和证据链的标准路径。

### 3.7 模型与推理接入层

这一层是 runtime 与 LLM 的正式接缝。

当前主要对应：

- `app/core/model/*`
- `HttpChatModelProvider`
- `GenerationConfig`
- main model / mini model / planner model 的使用方式

这一板块需要讨论：

1. v2 是否将多模型协同作为正式能力。
2. planner、executor、judge 是否使用不同模型。
3. model provider 与 runtime policy 如何解耦。
4. thinking、max_tokens、model options 由谁管理。
5. token / context budget 由哪一层负责。

落地子任务：

1. 输出当前模型调用场景清单，明确 planner、executor、judge、compressor 等使用位置。
2. 定义 v2 的模型角色划分与调用边界。
3. 定义 model provider 的职责边界，只保留能力接入，不承载 runtime 策略。
4. 定义 generation config 的归属与覆盖规则。
5. 产出 token budget 与 context budget 的统一治理方案。

### 3.8 记忆系统层

这一层当前由三套系统组成：runtime memory、system memory、user preference。

当前主要对应：

- `app/core/memory/*`
- `app/core/runtime/system_memory_lifecycle.py`
- `app/core/runtime/user_preference_lifecycle.py`

#### Runtime Memory

当前包括：

- 消息持久化
- 历史摘要
- context compaction
- tool chain 摘要

需要讨论：

1. Runtime Memory 是消息中心还是上下文中心。
2. 压缩属于 store、runtime，还是独立组件职责。
3. 是否继续使用当前 SQLite 消息流模型。

落地子任务：

1. 输出 runtime memory 数据结构与读写链路清单。
2. 定义 v2 中 runtime memory 的角色，是 message log、context cache，还是组合结构。
3. 定义 compaction 的归属层，明确 store、runtime、context manager 各自职责。
4. 定义 resume / replay / recent history 的恢复接口。
5. 产出 runtime memory 存储迁移方案，说明 SQLite 消息流模型是否保留。

#### System Memory

当前包括：

- memory card
- vector recall
- finalize 后经验沉淀

需要讨论：

1. system memory 的定位是知识资产还是执行经验资产。
2. recall 是 phase 驱动还是 hook 驱动。
3. memory card 是否仍是主载体。

落地子任务：

1. 输出 system memory 的写入、召回和存储结构清单。
2. 定义 v2 中 system memory 的正式定位与目标。
3. 定义 recall 挂点和触发协议。
4. 决定 memory card 是否保留，并形成标准产物定义。
5. 定义 system memory 与 verification、postmortem 的关系。

#### User Preference

当前包括：

- 偏好抽取
- recall 注入
- markdown store

需要讨论：

1. 它属于记忆、配置还是 persona。
2. 是否继续由 LLM 抽取。
3. 是否应继续与 system memory 分离存储。

落地子任务：

1. 输出 user preference 的来源、存储和注入链路清单。
2. 定义 user preference 在 v2 中的正式定位。
3. 决定偏好抽取机制，并形成更新策略说明。
4. 定义 user preference 的读取、更新、审核流程。
5. 定义它与 system memory、skill selection、prompt personalization 的边界。

### 3.9 Skills 与扩展能力层

这一层是独立扩展体系，不应被视为附属能力。

当前主要对应：

- `app/core/skills/*`
- `app/skills/*`
- skill prompt 注入
- skill tools 注册

这一板块需要讨论：

1. skill 在 v2 中是 prompt 扩展、tool bundle，还是 capability package。
2. skill 生命周期如何管理。
3. skill 与 tool 的边界是什么。
4. skill 是否参与 prepare / plan 阶段。
5. skill 是否需要独立的状态或依赖声明。

落地子任务：

1. 输出当前 skill 系统的加载、注入、工具暴露链路清单。
2. 定义 v2 中 skill 的正式角色与边界。
3. 定义 skill manifest 结构，覆盖 prompt、tool、resource、dependency。
4. 决定 skill 是否参与 planning / prepare，并形成挂载方案。
5. 产出 skill 生命周期管理方案。

### 3.10 SubAgent 协作层

这一层当前已经是执行模型的一部分，而不是边角功能。

当前主要对应：

- `app/agent/sub_agent.py`
- `app/agent/sub_agent_runtime.py`
- `app/tool/sub_agent_tool/*`
- 各类 subagent role prompt

这一板块需要讨论：

1. subagent 是独立 runtime，还是主 runtime 管控下的 worker。
2. 角色系统是否保留。
3. subagent 结果如何汇入主任务。
4. 并行执行的状态、证据、产物如何落盘。
5. subagent 是否应该成为 execution graph node 的一种执行器。

落地子任务：

1. 输出当前 subagent 创建、执行、并行、回收链路清单。
2. 定义 v2 中 subagent 的运行模型。
3. 定义 subagent 与主任务图的关系。
4. 决定角色系统是否保留，并形成角色模型说明。
5. 定义 subagent 的证据回流、状态回流和失败处理机制。

### 3.11 验证、判定与收尾层

这一层是项目区别于普通聊天代理的关键。

当前主要对应：

- `app/eval/*`
- `runtime_finalization.py`
- verification handoff
- deterministic verifiers
- LLM judge

这一板块需要讨论：

1. v2 的完成判定链路是什么。
2. verifier 的输入是否仍然基于 handoff。
3. 自报完成、系统判定完成、用户感知完成如何区分。
4. `pass / partial / fail` 的语义是否保留。
5. finalizing 是 phase，还是独立判定管线。

落地子任务：

1. 输出当前 verification handoff、deterministic verifier、LLM judge 的输入输出关系图。
2. 定义 v2 的 run outcome 与 handoff 结构。
3. 定义自报完成、系统验证完成、用户确认完成三种完成语义。
4. 决定 `pass / partial / fail` 是否保留，并形成证据要求说明。
5. 定义 finalizing 与 verification 的边界与衔接流程。

### 3.12 观测、复盘与工程化层

这一层支撑系统长期演化，不应只在最后补。

当前主要对应：

- `app/observability/*`
- `observability-evals/`
- `tests/*`
- `doc/design/*`
- `doc/refactor/*`

它可以再拆成四个子域：

1. 事件观测
2. 复盘产物
3. 测试体系
4. 设计与迁移文档

这一板块需要讨论：

1. v2 是否先定义事件模型再实现 runtime。
2. 哪些日志是运行证据，哪些只是 debug 信息。
3. 测试应围绕状态机、协议还是模块行为组织。
4. 文档与实现如何保持同步。

落地子任务：

1. 输出 observability、postmortem、tests、design docs 的现状清单。
2. 定义 v2 的事件模型，区分稳定协议事件与调试事件。
3. 定义证据链模型，明确 verification、postmortem、resume 可复用的产物。
4. 产出围绕状态机和协议的测试分层方案。
5. 产出设计文档、迁移文档、实现代码之间的同步机制。

## 4. 建议优先级

如果从“项目所有涉及板块”的角度看，建议分成三层优先级。

### 第一优先级：必须先定主干

1. Prompt 编排层
2. Runtime 主编排层
3. 状态模型层
4. 任务编排与执行图层
5. Tool 系统层

原因：

1. 这五块共同决定系统主干。
2. 如果这几块没定，memory、subagent、verification 都没有稳定挂点。

### 第二优先级：主干稳定后接入

1. 模型与推理接入层
2. 记忆系统层
3. Skills 与扩展能力层
4. SubAgent 协作层
5. 验证、判定与收尾层

原因：

1. 这些能力都依赖主状态流与主编排边界。
2. 过早讨论会反复返工。

### 第三优先级：伴随式落地

1. 入口与宿主层
2. 观测、复盘与工程化层

原因：

1. 它们虽然重要，但更适合围绕主架构同步收敛。
2. 过早单独展开，容易陷入壳层细节或测试细节。

## 5. 推荐讨论顺序

建议采用以下顺序推进：

1. Prompt 编排层
2. Runtime 主编排层
3. 状态模型层
4. 任务编排与执行图层
5. Tool 系统层
6. 模型与推理接入层
7. 验证、判定与收尾层
8. 记忆系统层
9. SubAgent 协作层
10. Skills 与扩展能力层
11. 入口与宿主层
12. 观测、复盘与工程化层

这个顺序的核心原则是：

1. 先定系统行为约束与主状态流。
2. 再定执行骨架与能力接入。
3. 最后接上扩展系统、宿主与工程化外壳。

## 6. 结论

当前项目已经不是单一 runtime 文件的问题，而是一个由 prompt、runtime、todo、tools、memory、subagent、verification、observability 共同耦合形成的系统。

因此，`runtime-v2` 的讨论不应只围绕“怎么拆 `AgentRuntime`”，而应围绕“如何重建一套新的系统主干，并重新安放现有各板块”来进行。

后续如果要继续推进，可以直接基于本文档逐块展开，先从第一优先级板块开始收敛。
