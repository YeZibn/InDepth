# runtime-v2 十三个重点框架结构实施计划（V1）

更新时间：2026-04-24  
状态：Draft

## 1. 目的

这份文档将 `runtime-v2` 的后续建设，直接按当前收敛的 13 个重点框架结构来组织。

这里的核心假设是：

1. 这 13 个部分不是讨论目录，而是后续真正要逐步实现的 13 个重点结构。
2. 每个重点结构都需要继续拆成可落地的子任务。
3. 各结构之间天然存在代码交叉，因此计划不能按瀑布式切分，只能按“结构分组 + 子任务交叉推进”的方式组织。

因此，本文不再按阶段拆一级目录，而是按 13 个重点结构拆分，并在每个结构下明确：

1. 结构目标
2. 落地子任务
3. 关键产物
4. 交叉依赖
5. 建议启动顺序

## 2. 总体实施原则

### 2.1 以结构为主，以阶段为辅

后续实现工作以这 13 个结构为主线组织；阶段只用于判断整体推进程度，不作为代码切分边界。

### 2.2 子任务允许跨结构并行推进

某个结构下的子任务，只要前置依赖满足，就可以提前启动，不要求所属结构整体完成。

### 2.3 每个子任务都必须有明确产物

每个子任务至少应产出以下之一：

1. 设计决策文档
2. 接口或数据结构定义
3. 迁移方案
4. 最小可运行实现
5. 测试或验证基线

### 2.4 优先建立主干结构

主干结构包括：

1. Prompt 编排层
2. Runtime 主编排层
3. 状态模型层
4. 任务编排与执行图层
5. Tool 系统层

其余结构在主干稳定后逐步接入，但相关子任务可以提前盘点、设计和预留接口。

### 2.5 子任务编号规则

本文采用统一任务编号：

1. 一级结构编号使用 `S1` 到 `S13`。
2. 每个结构下的落地子任务使用 `Sx-Ty`。
3. `Sx-Ty` 只表示任务归属，不表示严格串行顺序。
4. 真正的建议实现顺序以本文后面的“总实现顺序表”为准。

## 3. 十三个重点结构总表

| 编号 | 重点结构 | 核心作用 | 优先级 |
|---|---|---|---|
| S1 | Prompt 编排层 | 定义模型看到什么以及如何被约束 | P0 |
| S2 | 入口与宿主层 | 承载 runtime 的启动与会话宿主 | P1 |
| S3 | Runtime 主编排层 | 驱动一次 run 的主控制中心 | P0 |
| S4 | 状态模型层 | 定义系统内部正式状态对象 | P0 |
| S5 | 任务编排与执行图层 | 承载任务拆解、执行定位、恢复与协作 | P0 |
| S6 | Tool 系统层 | 提供统一能力接入与调用协议 | P0 |
| S7 | 模型与推理接入层 | 管理多模型角色与调用边界 | P1 |
| S8 | 记忆系统层 | 提供 runtime memory、system memory、user preference | P1 |
| S9 | Skills 与扩展能力层 | 提供可插拔能力包与知识包 | P2 |
| S10 | SubAgent 协作层 | 提供角色化协作和并行执行 | P1 |
| S11 | 验证、判定与收尾层 | 定义完成判定和结果收口 | P1 |
| S12 | 观测、复盘与工程化层 | 提供事件、测试、复盘、迁移基础设施 | P1 |
| S13 | Planner / Solver / Reflexion / Re-plan 运行框架层 | 收口规划、执行纠偏、重规划判定与主链映射 | P0 |

## 4. 分结构实施计划

## 4.1 S1 Prompt 编排层

结构目标：

1. 定义 v2 中 prompt 的正式分层。
2. 明确 prompt 与 runtime state 的边界。
3. 建立可持续演进的 prompt 资产体系。

落地子任务：

1. `S1-T1` 输出 prompt 资产清单。
   产物：`prompt-inventory` 文档。
2. `S1-T2` 定义 prompt 分层结构。
   产物：base prompt / phase prompt / dynamic injection / role prompt 的结构说明。
3. `S1-T3` 定义 structured handoff 的 prompt 协议。
   产物：handoff prompt contract。
4. `S1-T4` 定义 prompt 与状态模型的边界规则。
   产物：禁止通过消息隐式携带关键状态的规则文档。
5. `S1-T5` 建立 prompt assembly 机制。
   产物：v2 prompt assembler 的最小接口。
6. `S1-T6` 建立 prompt 迁移方案。
   产物：现有 prompt -> v2 的迁移清单。

交叉依赖：

1. 强依赖 S3 Runtime 主编排层。
2. 强依赖 S4 状态模型层。
3. 与 S8 记忆系统层交叉。
4. 与 S9 Skills 层交叉。
5. 与 S10 SubAgent 层交叉。

建议启动顺序：

1. 先完成资产清单与分层设计。
2. 再完成 handoff 协议与 assembler 接口。
3. 最后再做迁移。

## 4.2 S2 入口与宿主层

结构目标：

1. 定义 v2 的宿主模式。
2. 让 runtime core 与宿主壳层解耦。
3. 提供新任务、恢复任务、澄清恢复的统一入口。

落地子任务：

1. `S2-T1` 输出当前入口职责清单。
   产物：CLI / BaseAgent / bootstrap 职责拆解文档。
2. `S2-T2` 定义 runtime host 接口。
   产物：host interface 草案。
3. `S2-T3` 定义统一标识模型。
   产物：`task_id`、`run_id`、`session_id` 生命周期说明。
4. `S2-T4` 定义新任务启动协议。
   产物：start-run contract。
5. `S2-T5` 定义等待后重启协议。
   产物：post-wait restart contract。
6. `S2-T6` 定义 CLI 保留/收缩方案。
   产物：CLI migration note。

交叉依赖：

1. 强依赖 S3 Runtime 主编排层。
2. 强依赖 S4 状态模型层。
3. 与 S7 模型接入层交叉较弱。
4. 与 S12 工程化层交叉较强。

建议启动顺序：

1. 先定标识模型和 host 接口。
2. 再定 start/resume 协议。
3. 最后做 CLI 收缩和迁移。

## 4.3 S3 Runtime 主编排层

结构目标：

1. 成为 v2 的核心控制中心。
2. 只保留 orchestration 职责，不重新吞入 policy 和 domain 细节。
3. 形成 prepare / execute / finalize 的正式主链路。

落地子任务：

1. `S3-T1` 输出旧 `AgentRuntime` 职责拆解表。
   产物：orchestration / policy / domain / infra 四类职责表。
2. `S3-T2` 定义 v2 主控对象。
   产物：runtime orchestrator 设计稿。
3. `S3-T3` 定义 phase engine 接口。
   产物：prepare / execute / finalize contract。
4. `S3-T4` 定义 step loop 的最小职责集合。
   产物：step loop invariant 文档。
5. `S3-T5` 建立 runtime skeleton。
   产物：最小可运行 orchestrator 实现。
6. `S3-T6` 建立 finalizing pipeline 主干。
   产物：finalizing pipeline skeleton。

交叉依赖：

1. 强依赖 S4 状态模型层。
2. 强依赖 S1 Prompt 编排层。
3. 强依赖 S6 Tool 系统层。
4. 强依赖 S5 执行图层。
5. 与 S11 验证层交叉很强。

建议启动顺序：

1. 先完成职责拆解和主控对象定义。
2. 再完成 phase engine 与 step loop 约束。
3. 然后落最小 skeleton。

当前补充框架对齐结论：

1. `PreparePhase` 对应后续 `Planner`
2. `ExecutePhase` 对应后续 `Solver`
3. `Solver` 第一版在单个 node 内允许多轮 step
4. `Solver` 内部采用轻量三段逻辑：
   - `Actor` 负责 ReAct 求解
   - `Completion Evaluator` 只负责 node 进入 `completed` 前的完成判定
   - `Reflexion` 作为轻量纠偏步骤存在
5. `Reflexion` 当前不抬升为独立顶层 phase 或大组件

## 4.4 S4 状态模型层

结构目标：

1. 定义 v2 的正式状态系统。
2. 让消息、状态、事件、handoff 各自归位。
3. 成为其他结构共同依赖的基础层。

落地子任务：

1. `S4-T1` 输出当前状态字段总表。
   产物：state inventory。
2. `S4-T2` 定义核心状态对象集合。
   产物：`RunContext`、`PhaseState`、`TaskGraphState` 等结构定义。
3. `S4-T3` 输出统一状态图。
   产物：runtime state / stop reason / phase state 图。
4. `S4-T4` 定义状态分层规则。
   产物：内部态、外部态、事件态、handoff 态规则。
5. `S4-T5` 定义消息与状态解耦方案。
   产物：message/state split design。
6. `S4-T6` 建立最小状态库。
   产物：v2 state package skeleton。

交叉依赖：

1. 与 S3 Runtime 主编排层强耦合。
2. 与 S5 执行图层强耦合。
3. 与 S11 验证层强耦合。
4. 与 S12 观测层强耦合。

建议启动顺序：

1. 先做状态字段盘点。
2. 再定核心对象与状态图。
3. 之后推进状态库 skeleton。

## 4.5 S5 任务编排与执行图层

结构目标：

1. 用正式执行图替代当前隐式 todo/runtime 混合逻辑。
2. 承载任务拆分、执行定位、恢复、阻塞与并行协作。
3. 成为 runtime 驱动真实任务的执行骨架。

落地子任务：

1. `S5-T1` 输出 todo 体系用途分析。
   产物：todo purpose analysis。
2. `S5-T2` 做出 todo / task graph 命名决策。
   产物：命名与边界决策文档。
3. `S5-T3` 定义最小执行单元。
   产物：node / task / step 数据结构。
4. `S5-T4` 定义执行图关系模型。
   产物：串行、并行、blocked、awaiting_input、resume 结构说明。
5. `S5-T5` 定义执行图状态推进规则。
   产物：graph transition rules。
6. `S5-T6` 定义与 subagent、search、verification 的挂载方式。
   产物：cross-action graph binding 设计。
7. `S5-T7` 建立最小 task graph skeleton。
   产物：task graph state/store 接口。

交叉依赖：

1. 强依赖 S4 状态模型层。
2. 强依赖 S3 Runtime 主编排层。
3. 强依赖 S6 Tool 系统层。
4. 与 S10 SubAgent 层强交叉。
5. 与 S11 验证层中度交叉。

建议启动顺序：

1. 先做用途分析和命名决策。
2. 再定最小执行单元和关系模型。
3. 之后落 state/store skeleton。

## 4.6 S6 Tool 系统层

结构目标：

1. 为 v2 提供统一的能力调用协议。
2. 切开 capability、workflow、orchestration 三类工具语义。
3. 避免 runtime 再直接吞入具体工具细节。

落地子任务：

1. `S6-T1` 输出工具全量分类表。
   产物：tool inventory。
2. `S6-T2` 定义统一 tool request / tool result 协议。
   产物：tool protocol spec。
3. `S6-T3` 定义 runtime 与工具语义的耦合策略。
   产物：tool semantic coupling rules。
4. `S6-T4` 定义工具分域结构。
   产物：execution / search / task-graph / memory / subagent 分域方案。
5. `S6-T5` 定义 tool call 进入状态流、事件流、证据链的标准路径。
   产物：tool execution flow spec。
6. `S6-T6` 建立 v2 tool registry skeleton。
   产物：tool registry / adapter / validator skeleton。

交叉依赖：

1. 强依赖 S3 Runtime 层。
2. 强依赖 S4 状态模型层。
3. 与 S5 执行图层强交叉。
4. 与 S12 观测层强交叉。

建议启动顺序：

1. 先盘点和分类。
2. 再定协议和耦合规则。
3. 最后落 registry skeleton。

## 4.7 S7 模型与推理接入层

结构目标：

1. 为 v2 提供稳定的模型接入抽象。
2. 支持 planner、executor、judge、compressor 等多角色模型。
3. 把模型能力接入与 runtime 策略切开。

落地子任务：

1. `S7-T1` 输出模型调用场景清单。
   产物：model usage inventory。
2. `S7-T2` 定义模型角色划分。
   产物：planner / executor / judge / compressor role spec。
3. `S7-T3` 定义 model provider 边界。
   产物：provider responsibilities doc。
4. `S7-T4` 定义 generation config 归属与覆盖规则。
   产物：generation config policy。
5. `S7-T5` 定义 token budget / context budget 治理方案。
   产物：budget control design。
6. `S7-T6` 建立 v2 model adapter skeleton。
   产物：provider adapter skeleton。

交叉依赖：

1. 依赖 S3 Runtime 层。
2. 依赖 S1 Prompt 编排层。
3. 与 S8 Memory 层交叉。
4. 与 S11 验证层交叉。

建议启动顺序：

1. 先做场景盘点和角色划分。
2. 再定 provider 边界与 config 规则。
3. 然后落 adapter skeleton。

## 4.8 S8 记忆系统层

结构目标：

1. 重建 runtime memory、system memory、user preference 三套能力。
2. 让它们以统一挂点接入 v2，而不是重新散落在 runtime 里。

落地子任务：

1. `S8-T1` 输出 runtime memory 结构与链路清单。
   产物：runtime memory inventory。
2. `S8-T2` 定义 v2 runtime memory 模型。
   产物：message log / context cache / resume 接口说明。
3. `S8-T3` 输出 system memory 结构与链路清单。
   产物：system memory inventory。
4. `S8-T4` 定义 system memory 的正式定位和 recall 机制。
   产物：system memory design。
5. `S8-T5` 输出 user preference 结构与链路清单。
   产物：user preference inventory。
6. `S8-T6` 定义 user preference 的定位、更新机制和注入规则。
   产物：user preference design。
7. `S8-T7` 定义三套记忆系统的统一挂载点。
   产物：memory hook/injection design。
8. `S8-T8` 建立 v2 memory skeleton。
   产物：runtime/system/preference 三类接口骨架。

交叉依赖：

1. 强依赖 S1 Prompt 编排层。
2. 强依赖 S3 Runtime 层。
3. 强依赖 S4 状态模型层。
4. 与 S11 收尾层强交叉。
5. 与 S12 观测层中度交叉。

建议启动顺序：

1. 先分别做三套记忆清单。
2. 再定定位与挂载点。
3. 然后统一做 memory skeleton。

当前补充框架对齐结论：

1. `Reflexion` 的主落点是 runtime memory
2. 这类记忆属于运行期短期纠偏记忆
3. 它的作用是为后续 solve 或更高层 re-plan 提供失败归因和下一步策略
4. 当前不以 task graph 作为 reflexion 的主存储

## 4.9 S9 Skills 与扩展能力层

结构目标：

1. 为 v2 提供正式的可插拔扩展结构。
2. 让 skill 不只是 prompt 片段，而是可管理的能力包。

落地子任务：

1. `S9-T1` 输出当前 skill 链路清单。
   产物：skill inventory。
2. `S9-T2` 定义 v2 中 skill 的正式角色。
   产物：skill role design。
3. `S9-T3` 定义 skill manifest。
   产物：manifest schema。
4. `S9-T4` 定义 skill 与 prompt、tool、resource、dependency 的关系。
   产物：skill integration spec。
5. `S9-T5` 决定 skill 是否参与 planning / prepare。
   产物：skill planning policy。
6. `S9-T6` 建立 skill 生命周期管理方案。
   产物：discover/load/enable/disable/version 设计。

交叉依赖：

1. 依赖 S1 Prompt 层。
2. 依赖 S6 Tool 系统层。
3. 与 S8 Memory 层交叉。
4. 与 S10 SubAgent 层有中度交叉。

建议启动顺序：

1. 先做 inventory 和 role design。
2. 再定 manifest 与 integration spec。
3. 最后定 planning policy 与 lifecycle。

## 4.10 S10 SubAgent 协作层

结构目标：

1. 让 subagent 成为 v2 正式协作能力，而不是附属工具。
2. 让它能够被任务图和主 runtime 正式吸纳。

落地子任务：

1. `S10-T1` 输出当前 subagent 链路清单。
   产物：subagent inventory。
2. `S10-T2` 定义 subagent 运行模型。
   产物：independent runtime / controlled worker 决策文档。
3. `S10-T3` 定义 subagent 与主任务图的关系。
   产物：task graph binding design。
4. `S10-T4` 定义角色模型。
   产物：role system design。
5. `S10-T5` 定义 subagent 结果、证据、状态回流机制。
   产物：subagent feedback flow spec。
6. `S10-T6` 定义失败、超时、取消处理规则。
   产物：subagent failure policy。
7. `S10-T7` 建立 v2 subagent skeleton。
   产物：subagent runtime/adapter skeleton。

交叉依赖：

1. 强依赖 S5 执行图层。
2. 强依赖 S3 Runtime 层。
3. 与 S1 Prompt 层交叉。
4. 与 S12 观测层强交叉。

建议启动顺序：

1. 先做运行模型和任务图绑定。
2. 再定角色模型与回流机制。
3. 最后落 skeleton。

## 4.11 S11 验证、判定与收尾层

结构目标：

1. 保留并强化任务型 runtime 的完成判定能力。
2. 明确 run outcome、handoff、verification、finalizing 的正式关系。

落地子任务：

1. `S11-T1` 输出当前 verification 输入输出关系图。
   产物：verification IO map。
2. `S11-T2` 定义 v2 的 run outcome 结构。
   产物：run outcome schema。
3. `S11-T3` 定义 v2 的 handoff 结构。
   产物：handoff schema。
4. `S11-T4` 定义自报完成、系统验证完成、用户确认完成三种完成语义。
   产物：completion semantics spec。
5. `S11-T5` 决定 `pass / partial / fail` 是否保留及证据要求。
   产物：status + evidence policy。
6. `S11-T6` 定义 finalizing 与 verification 的衔接流程。
   产物：finalizing/verification pipeline design。
7. `S11-T7` 建立 v2 verification skeleton。
   产物：verifier chain skeleton。

交叉依赖：

1. 强依赖 S3 Runtime 层。
2. 强依赖 S4 状态模型层。
3. 强依赖 S1 Prompt 层。
4. 与 S8 Memory 层强交叉。
5. 与 S12 观测层强交叉。

建议启动顺序：

1. 先定 run outcome / handoff。
2. 再定完成语义和证据要求。
3. 然后落 verification skeleton。

当前补充框架对齐结论：

1. 当前 `verification` 仍然只服务 `FinalizePhase` 的最终守门
2. `verification` 不等于 `Reflexion`
3. `Reflexion` 属于 `Solver` 内部的执行中纠偏逻辑
4. 最终验证失败后的回退执行，仍属于 finalize pipeline 的外层控制问题，而不是 reflexion 本身

## 4.12 S12 观测、复盘与工程化层

结构目标：

1. 为 v2 提供正式事件模型、证据链、测试分层和迁移支撑。

落地子任务：

1. `S12-T1` 输出 observability / tests / docs / postmortem 现状清单。
   产物：engineering inventory。
2. `S12-T2` 定义 v2 正式事件模型。
   产物：event schema。
3. `S12-T3` 定义证据链模型。
   产物：artifact/evidence spec。
4. `S12-T4` 定义 postmortem 标准产物。
   产物：postmortem contract。
5. `S12-T5` 定义围绕状态机和协议的测试分层方案。
   产物：test strategy。
6. `S12-T6` 定义迁移文档和实现文档同步机制。
   产物：doc sync policy。
7. `S12-T7` 建立 v2 观测与测试 skeleton。
   产物：event store/test scaffolding skeleton。

交叉依赖：

1. 与 S3 Runtime 层强交叉。
2. 与 S4 状态模型层强交叉。
3. 与 S6 Tool 层强交叉。
4. 与 S11 收尾层强交叉。
5. 与 S8 记忆系统层有中度交叉。

建议启动顺序：

1. 先做 inventory 与事件模型。
2. 再定证据链和测试分层。
3. 最后落测试和观测 skeleton。

## 4.13 S13 Planner / Solver / Reflexion / Re-plan 运行框架层

结构目标：

1. 收口 `Planner / Solver / Reflexion / Re-plan` 在 runtime-v2 中的正式运行框架。
2. 对齐现有 `prepare / execute / finalize / verification` 与目标架构之间的映射关系。
3. 明确 node 内 solve、运行期纠偏、重规划动作与回流到 planning 的边界。

落地子任务：

1. `S13-T1` 对齐 `Planner / Solver / Reflexion / Re-plan` 与 `prepare / execute / finalize / verification` 的映射关系。
   产物：phase mapping spec。
2. `S13-T2` 定义 `Solver` 的内部结构与 node 内循环边界。
   产物：solver loop design。
3. `S13-T3` 定义 `Reflexion` 的触发条件、写入位置与最小语义。
   产物：reflexion runtime memory note。
4. `S13-T4` 定义 `request_replan` 的触发来源、回流流程与层级边界。
   产物：replan action flow design。
5. `S13-T5` 统一修正相关旧设计稿中的框架表述与编号引用。
   产物：design alignment patch。
6. `S13-T6` 定义 `StepResult` 的最小正式结构。
   产物：step result schema note。
7. `S13-T7` 定义统一 `runtime memory` 记录流与 `reflexion` entry 的最小正式结构。
   产物：runtime memory entry note。

交叉依赖：

1. 强依赖 S3 Runtime 主编排层。
2. 强依赖 S4 状态模型层。
3. 强依赖 S5 任务编排与执行图层。
4. 与 S8 记忆系统层强交叉。
5. 与 S11 验证、判定与收尾层强交叉。

建议启动顺序：

1. 先定 phase mapping 与 solver loop。
2. 再定 reflexion 与 re-plan 动作边界。
3. 然后补齐 `StepResult` 与统一 runtime memory 结构。
4. 最后统一修正文档与接口口径。

当前补充框架对齐结论：

1. `Planner = PreparePhase`
2. `Solver = ExecutePhase`
3. `Verification = FinalizePhase` 内的最终守门链路
4. `Reflexion` 不单独成为 phase，而是 `Solver` 内部的轻量纠偏机制
5. `Solver` 是 node 级求解器，单个 node 内允许多轮 step
6. 单轮 step 由 `Actor` 完成，`Actor` 内部可采用 `ReAct`
7. `Completion Evaluator` 只在 node 尝试进入 `completed` 前触发
8. `Reflexion` 只在 completion fail、node blocked、node failed 时触发
9. `Reflexion` 主落点是 runtime memory，内容保持精简结构化
10. `request_replan` 收敛为 `Reflexion` 可产出的统一动作
11. 外层独立 `Re-plan` 判定器当前取消
12. 真正的重规划由 `PreparePhase` 执行
13. node 级 `Reflexion` 可在执行链路中输出：
    - `request_replan`
14. final verification fail 也先进入 run 级 `Reflexion`
15. run 级 `Reflexion` 第一版只允许输出：
    - `request_replan`
    - `finish_failed`
16. 当动作为 `request_replan` 时，统一回到 `PreparePhase`
17. 当动作为 `finish_failed` 时，当前 run 直接失败结束
18. `request_replan` 当前只允许由两类 `Reflexion` 产出：
    - `node_reflexion`
    - `run_reflexion`
19. 第一版为 `request_replan` 保留一个轻量正式承载结构
20. 其最小字段当前收口为：
    - `source`
    - `node_id`
    - `reason`
    - `created_at`
21. `node_id` 在 `run_reflexion` 场景下允许为空
22. 第一版当前不在该结构中复制 graph / memory / verifier 原文 / step 全轨迹
23. 真正的重规划上下文仍统一来自当前 `RunContext`
24. `request_replan` 第一版当前不新开新的 `RunContext`
25. 回流时直接复用当前 run 内已有正式状态
26. 当 `request_replan` 被消费时，主链统一切回 `PreparePhase`
27. `PreparePhase` 在 replan 场景下读取：
    - 原 `user_input`
    - 当前 `goal`
    - 当前 graph
    - 全量 runtime memory
    - 当前 `request_replan`
28. 第一版当前不先清空 graph
29. graph 继续通过新的 `prepare_result.patch` 在当前 graph 基础上修改
30. 新 `prepare_result` 覆盖旧的正式 `prepare_result`
31. `request_replan` 作为一次性控制信息保留
32. 当 `PreparePhase` 成功消费后，应从正式状态中清空
33. `node_reflexion` 只归 `Solver / ExecutePhase` 使用
34. `node_reflexion` 第一版只处理：
    - completion evaluator fail
    - step blocked
    - step failed
35. `node_reflexion` 第一版动作固定为：
    - `retry_current_node`
    - `mark_blocked`
    - `mark_failed`
    - `request_replan`
36. `run_reflexion` 只归 `FinalizePhase` 中的 verification fail 使用
37. `run_reflexion` 第一版只处理：
    - `final_verification_fail`
38. `run_reflexion` 第一版动作固定为：
    - `request_replan`
    - `finish_failed`
39. `run_reflexion` 不允许输出 node 级动作
40. 两层当前都归入 `Reflexion` 语义族，但动作集合按层级分开
41. 第一版当前不扩展到更多 run 级失败类型
42. 第一版当前不展开 `abandoned` 与 `request_replan` 的共存语义
43. 第一版当前不做 `retry_finalize` 等额外 run 级动作
44. `Reflexion` 虽不作为独立 phase，但应接入主链统一 prompt 架构
45. `node_reflexion` 与 `run_reflexion` 的 prompt 都采用三段结构：
    - `base prompt`
    - `phase prompt`
    - `dynamic injection`
46. 两层 `Reflexion` 当前都应读取统一 runtime memory 上下文
47. `ReflexionInput` 继续保留，但作为 prompt 组装输入
48. 第一版允许为 `node_reflexion` 与 `run_reflexion` 分别定义独立 prompt input 结构
49. 第一版不新增独立 `RunPhase.REFLEXION`
17. `StepResult` 是 `Actor -> Solver` 的最小运行时结构化交接对象
18. `StepResult` 的最小字段当前收敛为：
    - `result_refs`
    - `status_signal`
    - `reason`
    - `patch`
19. `patch` 直接挂正式 `TaskGraphPatch`，并来自 tool 的结构化返回结果
20. 统一 `runtime memory` 采用单条记录流，不拆 `context` 与 `reflexion` 存储区
21. 统一 memory entry 通过 `entry_type` 区分 `context / reflexion`
22. 统一 memory entry 的最小锚点包括：
    - `role`
    - `run_id`
    - `step_id`
    - `node_id`
    - `created_at`
    - `related_result_refs`
    - `tool_name`
    - `tool_call_id`
23. 当 `entry_type = reflexion` 时，附加字段最小收敛为：
    - `trigger`
    - `reason`
    - `next_try_hint`
    - `action`
33. 当前 `PreparePhase / ExecutePhase / Finalize` 都读取全量 `runtime memory`
34. 当前阶段不引入按阶段裁剪的 `memory view`

## 4.14 S14 PreparePhase / Replan 正式策略补充

当前补充结论如下：

1. `PreparePhase` 第一版正式支持非空 graph 上的 `replan`
2. 第一版 `replan` 采用增量 planning，不做整图重写
3. 第一版增量 planning 只允许：
   - 新增 node
   - 修改现有 node 的 planning 属性
4. 第一版明确禁止删除旧 node
5. `PreparePhase` 在初始 planning 与 replan 下采用统一正式输入源：
   - `user_input`
   - `current_goal`
   - `task_graph_state`
   - `runtime_memory`
   - `tool / skill capability summary`
   - `finalize_return_input`
   - `request_replan`
6. 初始 planning 与 replan 的差异，通过输入状态差异表达，而不拆成两套独立 contract
7. `request_replan` 只作为 `PreparePhase` 的正式输入和 prompt 注入来源存在，不进入 planner 输出 contract
8. `finalize_return_input` 继续保留为 `PreparePhase` 的正式输入之一
9. `PrepareResult` 第一版继续保持极简正式结构：
   - `goal`
   - `patch`
10. `active node` 继续通过 `patch.active_node_id` 承载，不在 `PrepareResult` 中重复挂载
11. `replan` 场景下，planner 可同时产出：
   - 新增 node 草稿
   - 现有 node 更新草稿
12. 新增 node 使用临时 `ref`
13. 更新现有 node 必须引用正式 `node_id`
14. `prepare_result.patch` 第一版正式动作只保留：
   - `create`
   - `update`
15. 第一版不支持：
   - `delete`
   - `replace_node`
   - `replace_graph`
16. `update` 第一版只允许修改：
   - `name`
   - `description`
   - `owner`
   - `dependencies`
   - `node_status`
17. `update.node_status` 进一步收紧为只允许：
   - `pending`
   - `ready`
18. 新 node 可以依赖旧 node，也可以依赖本次新增 node
19. 非终态旧 node 可以更新 `dependencies` 并指向本次新增 node
20. 终态旧 node 第一版不允许被修改，且该规则在 prepare payload 的 normalize / 校验阶段直接拦截
21. replan 成功后，新 `prepare_result` 直接整体覆盖旧的 `runtime_state.prepare_result`
22. replan 成功后，`run_identity.goal` 由新的 `prepare_result.goal` 正式覆盖旧 goal
23. `request_replan` 不在进入 `PreparePhase` 前提前清空，而只在 prepare 成功完成后清空
24. replan 成功前旧 graph 不做预清理，只有新 patch 成功 apply 后 graph 才正式进入新状态
25. `PreparePhase` 第一版错误按 5 类收口：
   - `planner_model_error`
   - `planner_payload_parse_error`
   - `planner_contract_error`
   - `planner_graph_semantic_error`
   - `planner_noop_patch`
26. 只有 `planner_model_error` 在初始 planning 场景允许单节点 fallback
27. `replan` 场景第一版完全禁止 fallback
28. 以下情况全部按硬失败收口，不做 fallback：
   - payload 解析失败
   - contract 校验失败
   - graph 语义校验失败
   - no-op patch
29. prepare 失败第一版应保留轻量结构化错误类型，而不只抛裸异常

## 4.15 S15 Judge 型 Prompt 与结构化主张包补充

当前补充结论如下：

1. `Actor` 负责生成 `CompletionClaim`
2. `CompletionEvaluator` 只审 `CompletionClaim`
3. `Finalize generator` 负责生成 `Handoff`
4. `RuntimeVerifier` 只审 `Handoff`
5. judge 型组件不再直接读取：
   - `runtime_memory_text`
   - `capability_text`
6. judge 型组件只返回判断结果，不直接产出动作
7. `CompletionClaim` 第一版正式字段结构为：
   - `node_id`
   - `node_name`
   - `node_kind`
   - `node_description`
   - `completion_summary`
   - `completion_evidence`
   - `completion_notes`
   - `completion_reason`
8. `CompletionEvaluator` prompt 输出字段第一版固定为：
   - `result_status`
   - `summary`
   - `issues`
9. `CompletionEvaluator.result_status` 第一版只保留：
   - `pass`
   - `fail`
10. `Handoff` 第一版继续保持 4 个字段：
   - `user_input`
   - `goal`
   - `graph_summary`
   - `final_output`
11. `RuntimeVerifier` 输出字段第一版固定为：
   - `result_status`
   - `summary`
   - `issues`
12. `RuntimeVerifier.result_status` 第一版只保留：
   - `pass`
   - `fail`
25. replan 成功后：
   - `runtime_state.active_node_id` 以新 patch 的 `active_node_id` 为准重新同步
   - graph `active_node_id` 也以新 patch 的 `active_node_id` 为准重新同步
26. 以下情况都视为这次 replan 未成功消费：
   - planner 模型调用失败
   - planner payload 非法
   - patch 校验失败
   - patch 合法但没有任何实质修改
27. replan 失败时：
   - 旧 `prepare_result` 保留
   - 旧 graph 保留
   - `request_replan` 保留

## 5. 总实现顺序表

下表给出建议的总体实现顺序。这里的“顺序”采用批次波次而不是严格串行，表示同一批中的任务可以并行推进。

| 波次 | 目标 | 建议启动任务 | 主要前置依赖 |
|---|---|---|---|
| W1 | 主干现状盘点 | `S1-T1`, `S3-T1`, `S4-T1`, `S5-T1`, `S6-T1`, `S7-T1`, `S11-T1`, `S12-T1` | 无 |
| W2 | 主干抽象定型 | `S3-T2`, `S4-T2`, `S5-T2`, `S6-T2`, `S1-T2`, `S11-T2`, `S12-T2` | W1 |
| W3 | 主干规则定型 | `S3-T3`, `S3-T4`, `S4-T3`, `S4-T4`, `S5-T3`, `S5-T4`, `S6-T3`, `S6-T4`, `S1-T3`, `S1-T4`, `S7-T2`, `S7-T3`, `S11-T3`, `S11-T4` | W2 |
| W4 | 主干骨架落地 | `S3-T5`, `S4-T5`, `S4-T6`, `S5-T5`, `S5-T7`, `S6-T5`, `S6-T6`, `S1-T5`, `S2-T1`, `S2-T2`, `S7-T4`, `S7-T6`, `S12-T3` | W3 |
| W5 | 运行链路闭环 | `S3-T6`, `S2-T3`, `S2-T4`, `S2-T5`, `S7-T5`, `S11-T5`, `S11-T6`, `S12-T4`, `S12-T5`, `S12-T7` | W4 |
| W6 | 记忆系统接入 | `S8-T1`, `S8-T2`, `S8-T3`, `S8-T4`, `S8-T5`, `S8-T6`, `S8-T7`, `S8-T8`, `S1-T6` | W4-W5 |
| W7 | 协作与扩展接入 | `S10-T1`, `S10-T2`, `S10-T3`, `S10-T4`, `S10-T5`, `S10-T6`, `S10-T7`, `S9-T1`, `S9-T2`, `S9-T3`, `S9-T4`, `S9-T5`, `S9-T6` | W4-W6 |
| W8 | 收口与迁移 | `S11-T7`, `S12-T6`, `S2-T6`, `S5-T6` | W5-W7 |

说明：

1. `W1` 到 `W3` 主要是定义主干边界和核心抽象。
2. `W4` 到 `W5` 主要是把主干抽象接成最小可运行链路。
3. `W6` 到 `W7` 主要是接入增强能力。
4. `W8` 主要是做收口、迁移和补齐最后的关键挂点。

## 5.1 当前推进状态（2026-04-24）

截至目前，这份总计划文档已经落后于部分子任务设计稿。
按当前 `runtime-v2/design/` 目录实际文件情况重新对齐后，现状如下。

### 已完成对齐并已落文档的结构分布

1. `S1`：`T1-T6` 均已落文档。
2. `S2`：`T1-T4`、`T6` 已落文档；仅 `T5` 尚缺。
3. `S3`：`T1-T6` 均已落文档。
4. `S4`：`T1-T6` 均已落文档。
5. `S5`：`T1-T7` 均已落文档。
6. `S6`：`T1-T6` 均已落文档。
7. `S7`：`T1-T6` 均已落文档。
8. `S8`：`T1-T8` 均已落文档。
9. `S9`：`T1-T6` 均已落文档。
10. `S10`：`T1-T7` 均已落文档。
11. `S11`：`T1-T7` 均已落文档。
12. `S12`：`T1-T7` 均已落文档。

### 当前完成度

1. 总子任务数：`78`
2. 已完成并落文档：`78`
3. 仍未完成：`0`

### 当前仍未完成的子任务管理表

当前已无未完成子任务。

### 当前已经明确的新收敛方向

1. phase 第一版已收缩为 `prepare / execute / finalize`
2. `verification` 不再作为中途独立 phase
3. final verification 只发生在 `finalize` 内部
4. `handoff` 统一为一份正式结构，不再拆 `verification_handoff`
5. `step` 是唯一主判断中心
6. `orchestrator` 是控制器，只执行 `StepResult`
7. `RunContext` 已收缩为极简正式结构
8. `followup_nodes` 已升级为正式 graph 增量扩展入口
9. `handoff` 只属于 `finalize / verification / outcome` 链路
10. verification fail 通过 `finalize_return_input` 回灌 `execute`
11. 工具系统已按 `execution / task_graph / closeout / memory_search / subagent` 五域收敛
12. finalize closeout 后已预留 memory hooks，但暂不进入主判定链
13. `S8` 已重新收敛为运行期上下文、长期记忆、用户偏好三层正式主位
14. system memory 采用 `md + sqlite + 索引页`，user preference 采用 `md`
15. 长期记忆 recall 只在 run 开始发生一次，用户偏好整页注入
16. `handoff` 已预留 `memory_payload / preference_payload`
17. `RuntimeHost` 已成为正式宿主对象命名
18. `submit_user_input(...)` 已成为正式宿主执行入口命名
19. `awaiting_user_input / resume run` 已在第一版中正式收敛为“等待后重开新 run”
20. `task graph` 已补齐 `abandoned` 正式状态
21. `switch` 与 `abandon` 的语义边界已正式收口
22. `subagent` 必须绑定 node，生命周期动作走显式 node
23. `memory recall` 被正式收敛为启动注入，不属于 tool
24. `graph_status` 已收敛为 `active / blocked / completed / abandoned`
25. `state / message / event / handoff / tool result` 已正式分层
26. `skill` 已正式收敛为能力包，而不是单纯 prompt 片段
27. `skill prompt` 只承担轻量 `when to use` 角色，并由 `SKILL.md` frontmatter 派生
28. `skill` 可以提供 tool，但 tool 仍归统一 tool 系统治理
29. `subagent` 当前链路已明确分为 create / role prompt build / runtime init / run / info-destroy 五段
30. 总计划表与子设计稿的状态同步，已被正式纳入 `S12-T6`
31. `subagent` 在 v2 中已正式收敛为受主 runtime 控制的一次性 worker
32. `subagent` 与主 graph 的关系已收敛为 `node -> subagent_ref`，并引入 `owner` 执行归属字段
33. `subagent role` 已正式收敛为能力类型，不是单纯 prompt 标签
34. `subagent` 回流结果已收敛为 `execution_status / work_summary / result_summary / artifacts / evidence / notes / handoff_hint`
35. `subagent` 异常策略已收敛为 `failed / timed_out / cancelled` 三类异常终态，且异常默认只作用当前 node
36. `subagent skeleton` 已收敛为 `role registry / runtime facade / lifecycle controller / result collector / graph binding adapter` 五块骨架

### 当前仍未完成的子任务

当前已无未完成子任务。

说明：

1. 以上“已完成”表示设计对齐与文档落地已完成
2. 不代表对应代码 skeleton 已全部实现
3. `S2-T5` 已按“等待后重开新 run”方向正式落文档，不再保留独立 `resume-run contract`
4. 本节按实际文档文件重新对齐后，`S1-T5/T6`、整组 `S9`、整组 `S10`、`S12-T6` 均已从“未完成”转为“已落文档”
5. `S8-T2` 已有文档 `runtime-v2/design/s8/runtime-memory-model-t2-design-v1.md`，不再属于未完成项

### 建议的下一阶段主线

基于当前推进情况，下一阶段建议按以下顺序继续：

1. `S2 + S12`
   复核“等待后重开新 run”与宿主标识模型、事件模型、暂停/重启语义的对齐关系。
2. `S2`
   持续复核宿主协议文档与实现准备清单的一致性。
3. `实现前复核`
   在进入代码实现前，做一轮 `S2/S3/S4/S10` 的接口一致性复查。

原因是：

1. 十二结构第一版子任务设计稿已全部落文档
2. `S10` 已经整组完成，subagent 协作层的第一版结构已经收口
3. `S2-T5` 已将等待后继续推进统一收敛为“重开新 run”
4. 下一步重点已从补齐缺口转向口径统一与实现前复核

## 6. 建议的整体启动顺序

虽然实现组织按 13 个结构展开，但建议整体启动顺序如下：

### 第一批立即启动

1. S1 Prompt 编排层
2. S3 Runtime 主编排层
3. S4 状态模型层
4. S5 任务编排与执行图层
5. S6 Tool 系统层

### 第二批跟进启动

1. S7 模型与推理接入层
2. S11 验证、判定与收尾层
3. S12 观测、复盘与工程化层
4. S2 入口与宿主层
5. S13 Planner / Solver / Reflexion / Re-plan 运行框架层

### 第三批接入增强能力

1. S8 记忆系统层
2. S10 SubAgent 协作层
3. S9 Skills 与扩展能力层

这个顺序的含义不是后面的结构不能提前做，而是：

1. 第一批结构负责先把主干立住。
2. 第二批结构负责让主干可运行、可验证、可承载。
3. 第三批结构负责把扩展能力正式接入新底座。

## 7. 结构间交叉关系总览

| 结构 | 强交叉对象 |
|---|---|
| S1 Prompt 编排层 | S3、S4、S8、S10、S11 |
| S2 入口与宿主层 | S3、S4、S12 |
| S3 Runtime 主编排层 | S1、S4、S5、S6、S11、S12 |
| S4 状态模型层 | S3、S5、S11、S12 |
| S5 任务编排与执行图层 | S3、S4、S6、S10 |
| S6 Tool 系统层 | S3、S4、S5、S12 |
| S7 模型与推理接入层 | S1、S3、S8、S11 |
| S8 记忆系统层 | S1、S3、S4、S11、S12 |
| S9 Skills 与扩展能力层 | S1、S6、S8、S10 |
| S10 SubAgent 协作层 | S1、S3、S5、S12 |
| S11 验证、判定与收尾层 | S1、S3、S4、S8、S12 |
| S12 观测、复盘与工程化层 | S3、S4、S6、S8、S11 |
| S13 Planner / Solver / Reflexion / Re-plan 运行框架层 | S3、S4、S5、S8、S11 |

## 8. 当前建议优先推进的子任务集合

基于 2026-04-24 的文档对齐结果，如果现在继续推进设计，建议优先从下面这些子任务开始：

1. `S10-T2` 定义 subagent 运行模型。
2. `S10-T3` 定义 subagent 与主任务图的关系。
3. `S10-T4` 定义角色模型。
4. `S10-T5` 定义 subagent 结果、证据、状态回流机制。
5. `S10-T6` 定义失败、超时、取消处理规则。
6. `S2-T5` 定义等待后重启协议。
7. `S10-T7` 建立 v2 subagent skeleton。

这些子任务当前最值得优先推进，原因如下：

1. `S1 ~ S12` 第一版设计稿已经闭合，`S13` 正在补充收口。
2. `S2-T5` 已把等待后的继续推进统一收敛为宿主侧“重开新 run”。
3. 当前重点已经从补设计缺口转到统一口径与准备实现。
4. 后续推进更适合围绕接口对齐、状态一致性和实现顺序展开。

## 9. 结论

后续实现 `runtime-v2` 时，应当把这 13 个重点框架结构视为真正的实施主线。  
每个结构都不是“顺手补一下”的附属模块，而是需要单独建模、单独拆子任务、单独落地的核心部分。

因此，推荐的推进方式是：

1. 用这 13 个结构组织整体工作。
2. 用每个结构下的子任务组织具体实施。
3. 接受结构之间的天然交叉，并通过交叉依赖来安排推进顺序，而不是试图按瀑布式阶段强行隔离代码。
