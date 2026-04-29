# S1-T2 Prompt 分层结构定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S1-T2`

## 1. 目标

本任务用于正式定义 `runtime-v2` 的 prompt 分层结构。

目标是：

1. 明确不同 prompt 资产的层级和职责
2. 避免基础协议、阶段约束、动态注入、辅助判定 prompt 继续混在一起
3. 为后续 `RuntimeOrchestrator`、`RunContext`、memory、verification、subagent 接入提供统一 prompt 挂载模型

## 2. 正式结论

`runtime-v2` 第一版 prompt 体系统一分成 5 层：

1. `base prompt`
2. `phase prompt`
3. `dynamic injection`
4. `auxiliary prompts`
5. `subagent prompts`

这是 v2 的正式 prompt 分层结构。

## 3. 分层定义

## 3.1 Base Prompt

`base prompt` 用于承载稳定的主 Agent 协议和长期约束。

当前归入本层的内容：

1. `InDepth.md`
2. agent-level stable instructions

本层职责：

1. 定义主 Agent 的基础行为协议
2. 提供跨 phase 稳定存在的运行约束
3. 不承载本轮运行时的临时状态

本层边界：

1. 不放 phase 特定约束
2. 不放动态 recall 内容
3. 不放辅助判定器 prompt

## 3.2 Phase Prompt

`phase prompt` 用于承载当前 phase 的行为约束。

当前归入本层的内容：

1. prepare phase prompt
2. execute phase prompt
3. finalize phase prompt

本层职责：

1. 约束当前阶段允许做什么
2. 约束当前阶段禁止做什么
3. 规定当前阶段输出格式或行为模式

特别结论：

1. 不再单独保留“prepare planner prompt”作为独立层
2. prepare planner 的能力直接并入 prepare phase prompt

这意味着：

1. prepare 阶段既负责阶段约束，也负责准备产物约束
2. planner contract 属于 prepare phase 内部能力，而不是独立 prompt 层

## 3.3 Dynamic Injection

`dynamic injection` 用于承载运行时动态注入到主执行上下文中的 prompt 片段。

当前归入本层的内容：

1. prepare result injection
2. system memory recall injection
3. user preference recall injection
4. skill metadata injection

其中 `prepare result injection` 在当前第一版开发口径下，不再预设为长段 planning summary，而是以 `PreparePhase` 的正式产物为准，主要围绕：

1. 当前 `goal`
2. 必要的 graph planning 结果摘要

本层职责：

1. 把当前 run 的动态上下文补充给主 Agent
2. 允许 system prompt 主体保持相对稳定
3. 把运行期数据以受控方式注入消息链

本层边界：

1. 它是运行期上下文，不是基础协议
2. 它是主执行上下文的一部分，不是辅助模型 prompt

## 3.4 Auxiliary Prompts

`auxiliary prompts` 用于承载不属于主执行上下文、但服务于辅助判断、抽取、评估的 prompt。

当前归入本层的内容：

1. verifier prompt
2. clarification judge prompt
3. user preference extract prompt

本层职责：

1. 驱动辅助模型完成判断、评估、抽取等单独任务
2. 与主 Agent 执行上下文分离
3. 为 verification、clarification、preference capture 等能力服务

本层边界：

1. 不直接进入主 Agent 的 run message
2. 不与 phase prompt 混合
3. 不与 subagent role prompt 混合

## 3.5 SubAgent Prompts

`subagent prompts` 用于承载独立子代理的角色约束与输出要求。

当前归入本层的内容：

1. general
2. builder
3. researcher
4. reviewer
5. verifier

本层职责：

1. 定义不同子代理的职责边界
2. 约束子代理输出结构
3. 形成独立于主 Agent 的角色化 prompt 体系

特别结论：

1. subagent prompt 体系单独成层
2. 不与 auxiliary prompts 合并

原因是：

1. subagent 是独立代理角色，不是单次判断器
2. 它承担的是“协作执行”职责，而不是“局部判定”职责

## 4. 当前资产到新分层的映射

| 资产类别 | 新分层 |
|---|---|
| `InDepth.md` | `base prompt` |
| agent instructions | `base prompt` |
| prepare / execute / finalize | `phase prompt` |
| prepare planner contract | `phase prompt`（并入 prepare） |
| prepare result injection | `dynamic injection` |
| memory recall block | `dynamic injection` |
| preference recall block | `dynamic injection` |
| skill metadata snippet | `dynamic injection` |
| verifier prompt | `auxiliary prompts` |
| clarification judge prompt | `auxiliary prompts` |
| preference extract prompt | `auxiliary prompts` |
| subagent role prompts | `subagent prompts` |

## 5. 第一版边界约束

为了避免后续继续混层，第一版明确 5 条规则：

1. `base prompt` 不承载运行期动态信息
2. `phase prompt` 不单独再拆 planner prompt 层
3. `dynamic injection` 只服务主执行上下文
4. `auxiliary prompts` 不进入主 Agent 主消息链
5. `subagent prompts` 独立成层，不与辅助判定类 prompt 合并

## 6. 对其他任务的直接输入

`S1-T2` 将直接服务：

1. `S1-T3` structured handoff prompt 协议
2. `S1-T4` prompt 与状态模型边界规则
3. `S1-T5` prompt assembly 机制
4. `S3-T3` phase engine 接口
5. `S8` 记忆系统挂载点设计
6. `S10` subagent 模型定义
7. `S11` verification prompt 边界

## 7. 本任务结论摘要

本任务的最终结论可以压缩成 5 句话：

1. v2 prompt 体系正式分成 5 层
2. `InDepth.md` 属于 `base prompt`
3. prepare planner 不再独立成层，而并入 `phase prompt`
4. verifier / judge / extract 类 prompt 统一放入 `auxiliary prompts`
5. subagent prompt 单独成层，不与其他辅助 prompt 混合
