# S13 Planner / Solver / Reflexion / Re-plan 运行框架对齐（T1-T5）

更新时间：2026-04-28  
状态：Draft

## 1. 目标

本设计稿用于收口 `S13-T1 ~ S13-T5`：

1. `Planner / Solver / Reflexion / Re-plan` 与 `prepare / execute / finalize / verification` 的映射关系
2. `Solver` 的内部结构与 node 内循环边界
3. `Reflexion` 的触发条件、写入位置与最小语义
4. `Re-plan` 的判定条件、判定结果与回流流程
5. 相关旧设计稿中的框架表述与编号引用修正

## 2. 正式结论摘要

当前正式结论如下：

1. `Planner = PreparePhase`
2. `Solver = ExecutePhase`
3. `Verification = FinalizePhase` 内的最终守门链路
4. `Reflexion` 不单独成为 phase，而是 `Solver` 内部的轻量纠偏机制
5. `Re-plan` 不单独成为固定 phase，而是 runtime 外层的 run 级重规划判定动作
6. 真正的重规划由 `PreparePhase` 执行，而不是由 `Re-plan` 直接执行

## 3. 映射关系

当前正式映射关系如下：

1. `Planner` 负责初始 planning 与重规划后的 planning 收口
2. `Solver` 负责单个 active node 的局部求解与 node 状态推进
3. `Verification` 负责最终结果守门，不参与执行中纠偏
4. `Reflexion` 服务执行中纠偏，不承担最终验证职责
5. `Re-plan` 只负责判断是否需要回到 `PreparePhase` 进行重规划

## 4. Solver 的正式位置

`Solver` 的正式位置是 `ExecutePhase`。

它负责：

1. 围绕当前 `active node` 求解
2. 管理单个 node 内的多轮 step
3. 决定 node 的 `continue / completed / blocked / failed`
4. 在需要时触发 `Completion Evaluator` 与 `Reflexion`

它不负责：

1. 最终结果守门
2. 全局 graph 级重规划
3. 替代 `PreparePhase` 做 planning

## 5. Solver 的内部结构

第一版不把 `Actor / Completion Evaluator / Reflexion` 提升为独立顶层组件。

它们先只作为 `Solver` 内部逻辑环节存在。

### 5.1 Actor

`Actor` 负责当前 node 内的一轮完整 step 推进。

其工作方式如下：

1. 内部可采用 `ReAct`
2. 读取当前 node、上下文与 runtime memory
3. 完成本轮观察、行动、工具调用与结果整理
4. 产出抽象的 `StepResult`

### 5.2 Completion Evaluator

`Completion Evaluator` 只在当前 node 准备进入 `completed` 时触发。

它只回答一件事：

1. 当前 node 是否已经足够完成

它不负责：

1. 判断 `blocked`
2. 判断 `failed`
3. 代替 `Solver` 做一般循环控制

### 5.3 Reflexion

`Reflexion` 当前不单独成为 execute 外的大链路，而是 `Solver` 内部的轻量纠偏步骤。

它的触发时机包括：

1. `Completion Evaluator` 判定当前 node 还不能 completed
2. `Solver` 判定当前 node 进入 `blocked`
3. `Solver` 判定当前 node 进入 `failed`

它的作用如下：

1. 为后续 solve 留下短期纠偏记忆
2. 为更高层 `Re-plan` 提供失败归因输入
3. 不直接作为 task graph 的主存储

## 6. Node 内部循环

当前正式 node 内循环如下：

1. `Actor` 在当前 node 内做一轮 step
2. `Solver` 读取本轮 `StepResult`
3. 若当前结果表明 node 可以尝试收口
4. 则触发 `Completion Evaluator`
5. 若通过：
   - `Solver` 决定 node 进入 `completed`
6. 若不通过：
   - 触发 `Reflexion`
   - `Solver` 决定继续当前 node 的下一轮 step
7. 若当前结果表明仍可继续：
   - `Solver` 决定继续当前 node
8. 若当前结果表明缺少外部条件且无法局部解除：
   - `Solver` 决定 node 进入 `blocked`
   - 触发 `Reflexion`
9. 若当前结果表明当前路径已不可继续：
   - `Solver` 决定 node 进入 `failed`
   - 触发 `Reflexion`

## 7. Reflexion 的正式边界

`Reflexion` 的主落点是 `runtime memory`。

当前结论如下：

1. `Reflexion` 作为运行期短期记忆进入 runtime memory
2. 它不以 task graph 作为主存储
3. 它不是正式验证结果
4. 它不是最终 node 状态
5. 它的内容保持精简结构化
6. 它可输出 `replan_signal`
7. `replan_signal` 当前只作为建议信号，不构成强制触发

## 8. Re-plan 的正式位置

`Re-plan` 不是一个固定 phase，也不是一个直接执行重规划的组件。

它的正式位置是：

1. runtime 外层的 run 级重规划判定动作

它负责：

1. 判断当前 run 是否需要回到 `PreparePhase`
2. 为重规划提供回流原因与输入上下文

它不负责：

1. 直接生成新 task graph
2. 直接执行新 node
3. 替代 `Planner`

## 9. Re-plan 的触发条件与流程

当前正式流程如下：

1. `Solver` 或 `FinalizePhase` 产出升级信号
2. 满足以下任一条件时，允许进入 `Re-plan` 判定：
   - `node_failed`
   - `persistent_blocked`
   - `repeated_completion_fail`
   - `final_verification_fail`
3. runtime 外层结合 node 状态、graph 状态、失败历史、runtime memory 与 verification 结果决定是否进入 `Re-plan`
4. `Re-plan` 输出最小判定结果：
   - `no_replan`
   - `need_replan`
5. 当结果为 `need_replan` 时，附带 `reason` 与重规划输入上下文
6. 随后回到 `PreparePhase`
7. `PreparePhase` 基于已有目标、graph、结果与记忆重新执行 planning
8. 产出新的 planning 结果后，再继续后续 `ExecutePhase`

## 10. Verification 的正式边界

`Verification` 仍然属于 `FinalizePhase` 内部的最终守门器。

它负责：

1. 最终结果守门
2. 最终 handoff 验证

它不负责：

1. node 内部纠偏
2. 运行中的 reflexion
3. 替代 solver 做中途判断

因此当前明确：

1. `verification` 不等于 `Reflexion`
2. `Reflexion` 属于 solve 侧
3. `verification` 属于 finalize 侧

## 11. 当前未展开部分

本模块当前明确不进入：

1. `StepResult` 详细结构定稿
2. runtime memory 中 reflexion 的详细 schema
3. `PreparePhase` 在重规划场景下的具体输入输出 contract
4. solver 内部 prompt 注入的具体模板
