# S13 Planner / Solver / Reflexion / Re-plan 运行框架对齐（T1-T5）

更新时间：2026-04-28  
状态：Draft

## 1. 目标

本设计稿用于收口 `S13-T1 ~ S13-T5`：

1. `Planner / Solver / Reflexion / Re-plan` 与 `prepare / execute / finalize / verification` 的映射关系
2. `Solver` 的内部结构与 node 内循环边界
3. `Reflexion` 的触发条件、写入位置与最小语义
4. `Re-plan` 动作的触发来源、回流流程与层级边界
5. 相关旧设计稿中的框架表述与编号引用修正

## 2. 正式结论摘要

当前正式结论如下：

1. `Planner = PreparePhase`
2. `Solver = ExecutePhase`
3. `Verification = FinalizePhase` 内的最终守门链路
4. `Reflexion` 不单独成为 phase，而是 `Solver` 内部的轻量纠偏机制
5. 外层独立 `Re-plan` 判定器当前取消
6. `request_replan` 收敛为 `Reflexion` 可产出的统一动作
7. 真正的重规划由 `PreparePhase` 执行，而不是由 `Reflexion` 直接执行

## 3. 映射关系

当前正式映射关系如下：

1. `Planner` 负责初始 planning 与重规划后的 planning 收口
2. `Solver` 负责单个 active node 的局部求解与 node 状态推进
3. `Verification` 负责最终结果守门，不参与执行中纠偏
4. `Reflexion` 同时服务执行中纠偏与 final verification fail 后的动作决策
5. `request_replan` 只表示“回到 `PreparePhase` 重规划”的控制动作，不再单独抽成外层判定器

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
4. `FinalizePhase` 中 `verification fail`

它的作用如下：

1. 为后续 solve 留下短期纠偏记忆
2. 为后续动作决策提供失败归因输入
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
6. 它可输出动作
7. `request_replan` 是正式控制动作，不再只是建议信号

## 8. Re-plan 的正式位置

`Re-plan` 当前不是一个固定 phase，也不是一个独立判定组件。

它的正式位置是：

1. `Reflexion` 可产出的统一控制动作之一

它负责：

1. 表达当前 run 或当前 node 已需要回到 `PreparePhase`
2. 为后续 `PreparePhase` 重规划提供动作原因

它不负责：

1. 直接生成新 task graph
2. 直接执行新 node
3. 替代 `Planner`
4. 单独作为 runtime 外层 gate 做二次判定

## 9. Re-plan 的触发条件与流程

当前正式流程如下：

1. `Solver` 内部失败时，先进入 node 级 `Reflexion`
2. 若 node 级 `Reflexion.action = request_replan`
   - 则上抛重规划控制信号
   - 随后回到 `PreparePhase`
3. `FinalizePhase` 中若 `verification fail`
   - 先进入 run 级 `Reflexion`
4. run 级 `Reflexion` 第一版只允许输出：
   - `request_replan`
   - `finish_failed`
5. 若 run 级 `Reflexion.action = request_replan`
   - 则回到 `PreparePhase`
6. 若 run 级 `Reflexion.action = finish_failed`
   - 则当前 run 直接失败结束
7. `PreparePhase` 基于已有目标、graph、结果与统一 runtime memory 重新执行 planning
8. 产出新的 planning 结果后，再继续后续 `ExecutePhase`

当前第一版补充如下：

1. `request_replan` 当前只允许由两类 `Reflexion` 产出：
   - `node_reflexion`
   - `run_reflexion`
2. `node_reflexion` 指 `Solver` 内部在 node 级失败路径上产出的 `request_replan`
3. `run_reflexion` 指 final verification fail 后 run 级 `Reflexion` 产出的 `request_replan`
4. 第一版为 `request_replan` 保留一个轻量正式承载结构
5. 其最小字段收口为：
   - `source`
   - `node_id`
   - `reason`
   - `created_at`
6. 其中：
   - `source` 当前最小值集合为：
     - `node_reflexion`
     - `run_reflexion`
   - `node_id` 在 `run_reflexion` 场景下允许为空
7. 第一版当前不在该结构中复制：
   - graph snapshot
   - runtime memory snapshot
   - verifier 原始结果全文
   - step 全轨迹
8. 真正的重规划上下文仍统一来自当前 `RunContext`

当前第一版 `request_replan -> prepare` 回流规则补充如下：

1. `request_replan` 当前不新开新的 `RunContext`
2. 回流直接复用当前 run 内已有的正式状态
3. 当 `request_replan` 被消费时：
   - orchestrator 将 `current_phase` 切回 `PREPARE`
   - 然后重新执行一次 `run_prepare_phase(...)`
4. `PreparePhase` 在 replan 场景下读取：
   - 原 `user_input`
   - 当前 `goal`
   - 当前 graph
   - 全量 runtime memory
   - 当前 `request_replan`
5. 第一版当前不先清空 graph
6. graph 继续通过新的 `prepare_result.patch` 在当前 graph 基础上修改
7. 新的 `prepare_result` 会覆盖旧的正式 `prepare_result`
8. 正式回写规则仍为：
   - `prepare_result.goal -> run_identity.goal`
   - `prepare_result -> runtime_state.prepare_result`
   - `prepare_result.patch` 应用后写回 `domain_state.task_graph_state`
9. `request_replan` 作为一次性控制信息存在
10. 当 `PreparePhase` 成功消费后，应从正式状态中清空
11. 随后主链重新进入 `ExecutePhase`

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

当前补充第一版 finalize 边界如下：

1. `FinalizePhase` 第一版只在 graph 全部 `completed` 时进入
2. `finalize` 继续沿用统一 prompt 架构并读取统一上下文
3. `final_output` 由 `FinalizePhase` 基于上下文重新生成
4. verifier 只消费 `handoff`
5. verification `fail` 不再直接回退 `execute`
6. verification `fail` 会先进入 run 级 `Reflexion`
7. run 级 `Reflexion` 决定：
   - `request_replan`
   - `finish_failed`

## 11. Node 级与 Run 级 Reflexion 边界

当前第一版正式边界如下：

1. `node_reflexion` 只归 `Solver / ExecutePhase` 使用
2. `node_reflexion` 只处理以下触发场景：
   - completion evaluator fail
   - step blocked
   - step failed
3. `node_reflexion` 第一版动作固定为：
   - `retry_current_node`
   - `mark_blocked`
   - `mark_failed`
   - `request_replan`
4. `run_reflexion` 只归 `FinalizePhase` 中的 verification fail 使用
5. `run_reflexion` 第一版当前只处理：
   - `final_verification_fail`
6. `run_reflexion` 第一版动作固定为：
   - `request_replan`
   - `finish_failed`
7. `run_reflexion` 不允许输出：
   - `retry_current_node`
   - `mark_blocked`
   - `mark_failed`
8. 两层当前都归入 `Reflexion` 语义族，但动作集合按层级分开，不强行统一成单个动作枚举

## 12. 当前暂不实现范围

当前第一版明确不进入：

1. 通用多场景 run 级 `Reflexion`
2. node / run 两层统一成完全通用动作枚举
3. `abandoned` 与 `request_replan` 的共存语义
4. `request_replan` 的 memory 深度裁剪策略
5. `PreparePhase` 内部针对 `request_replan` 的特殊多轮机制
6. `retry_finalize`、`pause_run` 等额外 run 级动作

当前补充实现口径如下：

1. `Reflexion` 虽不作为独立 phase，但应接入主链统一 prompt 架构
2. `node_reflexion` 与 `run_reflexion` 的 prompt 都采用三段结构：
   - `base prompt`
   - `phase prompt`
   - `dynamic injection`
3. 两层 `Reflexion` 当前都应读取统一 runtime memory 上下文
4. `ReflexionInput` 继续保留，但作为 prompt 组装输入，而不是直接替代完整上下文
5. 第一版允许为 `node_reflexion` 与 `run_reflexion` 分别定义独立 prompt input 结构
6. 第一版不新增独立 `RunPhase.REFLEXION`

## 13. 当前未展开部分

本模块当前明确不进入：

1. `StepResult` 详细结构定稿
2. runtime memory 中 reflexion 的详细 schema
3. `PreparePhase` 在重规划场景下的具体输入输出 contract
4. solver 内部 prompt 注入的具体模板

## 14. PreparePhase 第一版落地边界补充

针对后续开发阶段，当前补充结论如下：

1. `PreparePhase` 第一版应当是一次真实 planning 调用，而不只是 phase 切换壳
2. 第一版主产物以 graph 层结果为主，而不是只停留在 planning summary
3. 在空图场景下，`PreparePhase` 允许直接产出首批节点
4. 第一版需要保留一个轻量正式 `prepare_result`，作为后续 `execute / replan / finalize` 的稳定消费口
5. `PreparePhase` 第一版输入面包括：
   - `run_identity.user_input`
   - `run_identity.goal` 作为可选旧值参考
   - 当前 graph 状态
   - task 级 `runtime memory`
   - capability 文本
   - `runtime_state.finalize_return_input` 作为预留输入
6. `PreparePhase` 第一版当前不展开：
   - `replan` 回流实现
   - prepare 内多轮循环
   - prepare 阶段主动大量调 tool
   - skill resource 直读
   - finalize / evaluator / reflexion 联动深化

## 15. PreparePhase 第一版最小输入输出 contract 补充

当前补充结论如下：

1. 这里的“输入”指的是 `PreparePhase` 合法依赖的正式信息源，而不是直接传给 LLM 的裸字段列表
2. 这些输入共同限定后续 prepare prompt 的合法素材来源
3. `goal` 不再依赖 host 预先提供，而由 `PreparePhase` 作为正式输出产出并回写
4. `PrepareResult` 第一版最小正式结构收口为：
   - `goal`
   - `patch`
5. 第一版不再保留：
   - `summary`
   - 独立 `active_node_id`
6. `active_node_id` 统一由 `TaskGraphPatch.active_node_id` 承载
7. 正式回写规则如下：
   - `prepare_result.goal -> run_identity.goal`
   - `prepare_result -> runtime_state.prepare_result`
   - `prepare_result.patch` 应用后写回 `domain_state.task_graph_state`
   - `runtime_state.active_node_id` 由 orchestrator 在 patch 应用后同步
8. 第一版追加一条轻量 prepare memory entry，只记录：
   - `goal`
   - `graph_change_summary`

## 16. PreparePhase Prompt 与 Planner 调用链补充

当前补充结论如下：

1. `PreparePhase` 继续沿用统一 prompt 架构：
   - `base prompt`
   - `phase prompt`
   - `dynamic injection`
2. `prepare` 不复用 execute 视角的 prompt input，而采用 prepare 专用输入视角
3. `prepare` 的动态注入以 `task / graph planning` 视角为主，而不是 `active node` 执行视角
4. `PreparePhase` 第一版不复用 `ReActStepRunner`
5. `PreparePhase` 第一版采用单次 planner model 调用，不带 tool call loop
6. planner 输出先采用 planning payload，而不是直接生成正式 `TaskGraphNode`
7. orchestrator 负责将 planner payload 转换为正式 `PrepareResult.patch`
8. `node_id / graph_id` 不由 LLM 直接生成，而由 orchestrator 在解析后补齐
9. `dependencies` 第一版允许先按草案引用表达，再由 orchestrator 做规范化映射
10. planner payload 中的节点草案第一版最小字段粒度为：
   - `name`
   - `kind`
   - `description`
   - `node_status`
   - `owner`
   - `dependencies`
   - `order`
11. 第一版新增节点状态只允许 `pending / ready`
12. 第一版 `owner` 默认使用 `main`

## 15. ExecutePhase / Solver 第一版 contract 补充

当前补充结论如下：

1. `Solver` 与 `ExecutePhase` 的边界需要切开：
   - `Solver` 只负责当前 node 的一次 solve 收口
   - `ExecutePhase` 负责 graph 级循环、下一 node 选择与 phase 退出
2. `Solver` 第一版正式输入收口为：
   - `RunContext`
   - 当前 `TaskGraphNode`
3. 第一版不单独引入更重的 `SolverContext`
4. 第一版需要新增单独的 `SolverResult`，不再让 execute 直接消费裸 `StepResult`
5. `SolverResult` 第一版最小正式结构收口为：
   - `final_step_result`
   - `final_node_status`
   - `step_count`
6. 第一版 `SolverResult` 不保留：
   - `active_node_id`
7. `active_node_id` 不属于 node solve 结果，而属于 graph 级调度结果，应由 `ExecutePhase` 在应用 solve 结果后重新决定
8. `final_step_result` 第一版保留，作为后续 memory / debug / solver 扩展的稳定消费口

## 16. ExecutePhase 第一版主循环与退出条件补充

当前补充结论如下：

1. `ExecutePhase` 第一版采用两层循环：
   - 外层为 graph 级循环
   - 内层为 `Solver` 管理的当前 node 多轮 step
2. `ExecutePhase` 每轮负责：
   - 选择当前可执行 node
   - 若存在 node，则调用一次 `Solver`
   - 应用 `SolverResult`
   - 回到 graph 层重新选择
   - 若不存在可执行 node，则判断 execute 是否退出
3. `Solver` 内部 node 收口规则第一版保持为：
   - `progressed` -> 继续当前 node 下一轮 step
   - `ready_for_completion` -> 当前 node 进入 `completed`
   - `blocked` -> 当前 node 进入 `blocked`
   - `failed` -> 当前 node 进入 `failed`
4. 当前 node 在 `completed / blocked / failed` 后，第一版都先回到 graph 层继续寻找其他可执行 node
5. 第一版 execute 的退出条件收口为：
   - graph 中已经没有任何可继续推进的 node
6. 第一版 graph 级退出收口规则：
   - 若所有 node 都已 `completed`，则 `graph_status = completed`
   - 若 graph 已无可继续主线但未完成，则统一先收口为 `graph_status = blocked`
7. 第一版当前不展开 `abandoned` 与 `replan` 的共存语义，该问题留待后续重点讨论

## 17. Solver 第一版落点与单 node 多轮 step 推进补充

当前补充结论如下：

1. `Solver` 正式单独落到：
   - `src/rtv2/solver/runtime_solver.py`
2. `ReActStepRunner` 继续只负责单轮 actor step
3. `RuntimeSolver` 负责当前 node 的多轮 solve 收口
4. 第一版 `pending -> ready` 仍由 `Solver` 做最小释放判断
5. 当 node 从 `pending -> ready` 后，本次 solve 先结束，交回 graph 层重新选择，而不继续同轮进入 ReAct
6. 第一版 `ready -> running` 后允许在同一次 solve 中继续进入后续 running step
7. 第一版需要加入 `max_steps_per_node` 保护
8. 当前第一版上限固定为：
   - `20`
9. 当单 node 步数达到上限仍未收口时，第一版先统一收为：
   - `blocked`
10. 第一版 `SolverResult` 不单独持有 `patch`
11. graph patch 继续通过：
    - `SolverResult.final_step_result.patch`
    承接正式 graph 修改
