# InDepth 运行时执行协议（精简强化版）

目标：让执行可落地、可审计、可复用。

## 0. 规范约定

术语：
- MUST：强制，禁止违反。
- SHOULD：推荐，若不做需说明理由。
- MAY：按场景可选。

## 1. 执行主流程

复杂任务 MUST 按以下主流程推进：
1. 启动校验
2. 规划拆解
3. 执行推进
4. 汇总交付
5. 复盘沉淀

### 1.1 启动校验

任务开始前，Agent MUST 明确：
1. 任务目标
2. 时间基准（时区 + 截止时刻）
3. 执行范围
4. 约束条件
5. 交付标准
6. 验收口径

若边界不清、指标不明、上下文缺失，MUST 先澄清，再执行。

### 1.2 最小闭环检查

交付前 MUST 检查闭环是否完整：
1. 前置校验已完成
2. 任务拆解已完成
3. SubAgent 创建决策已记录
4. 执行状态已同步
5. 结果已汇总交付
6. 复盘已沉淀

任一步缺失，MUST 在交付前补齐或说明原因。

## 2. 任务编排（Todo + SubAgent + 协作 + 状态确认）

### 2.1 Todo 模块

触发条件（满足任一即 MUST 创建 todo）：
- 至少 3 个可识别步骤
- 涉及跨文件或跨组件修改
- 预计执行超过 5 分钟
- 存在依赖或并行机会

创建细则：
1. MUST 先创建 todo 主任务（`create_task`）再进入执行。
2. 主任务标题 MUST 包含目标对象与动作，MUST NOT 使用空泛标题。
3. 主任务描述 MUST 至少包含：范围边界、交付物、验收口径、时间基准（如有时效要求）。
4. 调用 `create_task` 时 MUST 提供顶层 `split_reason`（整体拆分理由），且写入 Context 区块。
5. 创建后 MUST 保存返回的 `todo_id`，后续状态更新与查询 MUST 统一复用该 `todo_id`。

子任务细则：
1. 每个子任务 MUST 是“单一可验证动作”，建议粒度为 5-30 分钟可完成。
2. 子任务描述 SHOULD 使用“动词 + 对象 + 产出”格式。
3. 子任务 MUST 标注完成判据（至少一项：产物路径、命令结果、结构化结论）。
4. 存在先后关系时 MUST 写清依赖顺序；可并行项 SHOULD 显式标记可并行。
5. 新建子任务默认状态 MUST 为 `pending`。

执行边界：
1. 后续动作 MUST 以子任务清单为执行依据。
2. 清单外动作 MUST 先补入子任务，再执行。
3. MUST NOT 跳过规划直接做未登记动作。

### 2.2 SubAgent 模块

角色职责：
- 主 Agent：调度、依赖管理、状态监控、汇总交付
- SubAgent：执行已分配子任务

创建决策：
1. 创建 todo 前，主 Agent MUST 先完成“是否创建 SubAgent”评估并记录。
2. 是否使用 SubAgent SHOULD 按下述 MUST/SHOULD/SHOULD NOT 条件判断，不应机械默认开启。

场景分层（优先按 MUST/SHOULD/SHOULD NOT 判定）：
1. MUST 使用 SubAgent：
   - 存在 2 条及以上可独立推进的并行子任务，且任一子任务预计 > 3 分钟
   - 需要“实现”和“独立验证”并行推进（如 builder + verifier）
   - 主 Agent 若同时承担调度与执行将导致关键状态无法及时同步
   - 子任务边界清晰，可独立输入/输出
   - 子任务资源密集（大量检索、批量文件处理、长链路命令）
   - 子任务需要专门工具或领域能力（researcher/reviewer/verifier 等）
3. SHOULD NOT 使用 SubAgent：
   - 任务可在 5 分钟内一次性完成
   - 子任务强耦合，频繁来回共享上下文，拆分成本高于收益
   - 关键工具或上下文仅主 Agent 可访问，分拆后无法闭环

不创建时 MUST 记录理由（任务很小、拆分成本高、关键工具仅主 Agent 可用、链路时延敏感）。

角色路由：
1. 调用 `create_sub_agent` 前 MUST 显式传入 `role`；MUST NOT 使用 `auto` 或隐式路由。
2. 允许角色：`researcher`、`builder`、`reviewer`、`verifier`、`general`。
3. `reviewer` 与 `verifier` SHOULD NOT 做实现改动。
4. 同一子任务 MUST NOT 重复分配给多个角色（交叉验证除外）。

快速示例：
1. SHOULD 用：一条线改代码，一条线补测试并跑验证，可并行且验收口径清晰。
2. SHOULD NOT 用：只改 1 个文件的文案与变量名，5 分钟内可完成。

### 2.3 Todo + SubAgent 协作模块

协作登记：
1. 拆解完成后，MUST 先把“创建/启动 SubAgent”写入 todo，再执行。
2. 并行流 SHOULD 拆成两步：创建 SubAgent 配置、启动 SubAgent 执行。
3. 若包含 SubAgent 动作，MUST 将“创建/启动/回收”分别作为独立子任务登记。
4. 与 Agent 有关的配置动作 MUST 显式入 todo（角色、工具、I/O 约束、验收口径、并发参数）。

协作同步：
1. 主 Agent MUST 在关键节点同步状态：启动、完成、阻塞、恢复。
2. 不创建 SubAgent 时 MUST 记录原因并回写 todo。
3. 并行执行时，MUST 为每条并行流绑定独立子任务编号，MUST NOT 多个执行流共享同一子任务状态位。

协作最小要求：
1. 若创建 SubAgent，SHOULD 将“创建/启动/回收”拆成可追踪的独立子任务。
2. 每条并行流 SHOULD 绑定独立子任务编号，并独立回写状态。
3. 若中途新增动作（如补一次回归测试），MUST 先新增子任务再执行，MUST NOT 直接做未登记动作。

### 2.4 状态确认模块

执行前后对齐：
1. 每一步执行前，MUST 明确“当前正在执行的 todo 子任务”。
2. 若发现当前动作不属于任何已登记子任务，MUST 先补充子任务，再执行动作。
3. 执行过程中切换子任务时，MUST 先回写原子状态变更，再激活新子任务。

Runtime 绑定现实：
1. Runtime 当前会维护 `todo_id`、`active_subtask_number`、`execution_phase`、`binding_required`。
2. 若 todo 已创建，但普通工具调用尚未绑定 active subtask，Runtime MAY 发出 warning，提示当前执行存在编排缺口。
3. 协议层仍要求 Agent 主动完成子任务绑定；Runtime warning 只是补充保护，不等于协议豁免。

状态机约束：
1. 初始状态：`pending`
2. 开始执行：`pending -> in-progress`
3. 执行完成：`in-progress -> completed`
4. 出现阻塞：`in-progress -> blocked`，并记录阻塞原因、影响范围、下一次重试条件
5. 部分完成但未闭环：`in-progress -> partial`，并记录已保留产物与剩余缺口
6. 等待用户或外部输入：`in-progress -> awaiting_input`，并记录所缺输入
7. 超出预算或步数：`in-progress -> timed_out`，并记录预算耗尽原因
8. 执行失败：`in-progress -> failed`，并记录失败原因与证据
9. 阻塞解除：`blocked/partial/awaiting_input/timed_out/failed -> in-progress`，并记录解除依据
10. 明确取消：`pending/in-progress/blocked/partial/awaiting_input/timed_out/failed -> abandoned`，并记录取消原因

状态写回要求：
1. 状态变化后 SHOULD 立即回写，不得在多个关键动作后批量补写。
2. 任何 `completed` 子任务 MUST 具备可核验证据（产物路径、命令结果、关键结论之一）。
3. 若执行结果与预期不一致，MUST 回写为 `blocked`、`failed`、`partial`、`awaiting_input`、`timed_out` 之一，MUST NOT 直接标记 `completed`。
4. 调用 Todo 工具时，MUST 传 `todo_id`（例如 `update_task_status(todo_id=..., ...)`）。

收尾一致性：
1. 交付前 MUST 扫描全部子任务状态，确认不存在“已完成交付但仍有关键子任务非 `completed/abandoned`”的冲突。
2. 对 `abandoned` 子任务，MUST 在最终说明中标注“取消原因 + 对结果影响”。
3. 对长期 `blocked/failed/partial/awaiting_input/timed_out` 子任务，MUST 输出移交信息：阻塞点、所需输入、建议下一步。

### 2.5 未完成任务兜底模块

目标：
1. 任务未完成时 MUST 先保留现场，再决定恢复动作。
2. 默认采用“偏主动恢复”策略：低风险恢复先自动推进，高风险恢复再升级决策层。
3. 恢复目标 SHOULD 优先保留已有有效产出，而不是机械追求形式上的“全完成”。

未完成分类：
1. `blocked`：依赖未满足或当前无法继续
2. `failed`：已执行但结果失败或工具报错
3. `partial`：已有部分有效产出但未完整闭环
4. `awaiting_input`：等待用户或外部输入
5. `timed_out`：达到预算上限、重试上限或步数上限
6. `abandoned`：明确止损并不再继续投入

失败后的强制顺序：
1. MUST 先记录结构化失败信息：`record_task_fallback`
2. MUST 再生成恢复决策：`plan_task_recovery`
3. 若恢复决策为低风险且 `decision_level=auto`，SHOULD 将恢复动作落成新的 follow-up subtasks：`append_followup_subtasks`
4. MUST NOT 在未记录 fallback 的情况下直接跳过失败点继续宣称完成
5. 若已存在 `todo_id` 但当前失败无法归属到具体 subtask，MUST 将其视为编排缺口；SHOULD 进入 `decision_handoff`，并先补齐 active subtask 绑定再继续执行

`record_task_fallback` 最小要求：
1. MUST 记录 `state`
2. MUST 记录 `reason_code`
3. MUST 记录 `reason_detail`
4. SHOULD 记录 `impact_scope`
5. SHOULD 记录 `required_input`
6. SHOULD 记录 `evidence`
7. SHOULD 记录 `suggested_next_action`

恢复动作集：
1. `retry`：原路径小范围重试
2. `retry_with_fix`：先修正参数/上下文/依赖，再重试
3. `split`：拆出更小的诊断/修复动作
4. `execution_handoff`：换执行者，目标不变
5. `decision_handoff`：把下一步判断权上交给主 Agent 或用户
6. `pause`：等待依赖或输入
7. `degrade`：接受部分交付
8. `abandon`：明确放弃

恢复决策分级：
1. `auto`：低风险、局部、可逆恢复，可自动执行
2. `agent_decide`：涉及策略取舍，由主 Agent 判断
3. `user_confirm`：涉及目标、范围、成本、质量承诺或放弃时，MUST 由用户确认

主动恢复硬边界：
1. MUST NOT 擅自改变用户目标
2. MUST NOT 显著扩大工作范围
3. MUST NOT 覆盖已有有效产物
4. MUST NOT 无限重试
5. `degrade/abandon` MUST NOT 默认自动执行

恢复动作与子任务关系：
1. 除 `pause` 与预算内一次 `retry` 外，多数恢复动作 SHOULD 落成新的 subtask
2. 失败原因不明时，SHOULD 先拆出 `diagnose` 子任务，再进入 `repair/retry/verify`
3. 恢复后的新子任务 MUST 写清 owner、依赖、验收口径

交付要求：
1. 若存在未完成子任务，最终说明 MUST 包含：
   - 未完成类型
   - 影响范围
   - 已保留产出
   - 推荐下一步
2. 用户可见输出 SHOULD 提供简短恢复摘要，至少说明：
   - todo
   - subtask（若已绑定）
   - failure
   - next action
3. 评估与 postmortem SHOULD 携带恢复信息，便于后续复盘与接续。

执行依据：`app/tool/todo_tool/todo_tool.py`

## 3. 时效检索协议

凡包含“最新/近期/动态/趋势/新闻”等语义，检索前 MUST 通过四项门禁：
1. 时间基准已定义
2. 问题清单已定义（3-5 个核心问题）
3. 检索预算已定义（轮次或时长）
4. 停止阈值已定义（何时信息足够）

任一缺失：MUST NOT 启动检索。

输出 MUST 标注时间基准；MUST NOT 主观臆测“最新”。

### 3.1 预算与止损

1. 检索前 MUST 先写问题清单，禁止无目标泛搜。
2. 检索前 MUST 设预算。默认预算 SHOULD 由运行时配置或检索门禁策略统一控制。
3. 每轮 MUST 优先核心来源，再补充次级来源。
4. 每个结论点 SHOULD 控制在 2-3 个高质量来源。
5. 每轮结束 MUST 去重与裁剪，只保留与问题直接相关的信息。
6. 核心问题覆盖且结论稳定时 MUST 立即停止扩搜。
7. 超预算仍不充分时 MUST 输出：当前结论 + 信息缺口 + 后续建议。
8. MUST NOT 因“可能还有更多信息”无限追加轮次。
9. 若要突破预算，MUST 先记录：突破理由、追加预算、预期收益。

### 3.2 收敛输出格式

检索结果 MUST 统一为：
1. 核心结论
2. 关键证据
3. 信息缺口
4. 下一步建议

禁止无结构堆叠。

## 4. 记忆

本章将记忆复用拆成两个并列模块：
1. 系统经验记忆：解决“过去类似任务有什么可复用经验”
2. 运行时历史回溯：解决“当前任务某一步到底发生了什么”

### 4.1 系统经验记忆（Memory / Knowledge）

最小目标：可检索、可触发、可评估。禁止文档堆积。

存储与入口：
1. 统一载体：`memory_card`
2. 存储：`db/system_memory.db`（主表 `memory_card`）
3. 运行时会话记忆 MUST 按 Agent 类型聚合落盘，并与系统经验记忆分离管理。
4. 录入/查询统一入口：`memory_card_cli.py`（`upsert-json/search/due`）

触发与注入：
1. Runtime 在任务开始时 SHOULD 尝试系统记忆高精度召回（最多 5 条）并摘要化注入 prompt
2. 启动召回 MUST 遵循“精确率优先、未命中不阻塞”
3. 运行中可在 `pull_request/pre_release/postmortem` 阶段调用 `capture_runtime_memory_candidate`
4. `task_finished` 后，框架 MUST 强制沉淀一次 `postmortem` 记忆
5. 运行中 capture 当前保持 tool 显式调用，不做 Runtime 隐式自动写卡
6. 当问题本质是“类似任务以前怎么做过/踩过什么坑/有哪些可复用经验”时，SHOULD 优先做经验搜索，而不是直接回看当前任务历史。

观测与治理：
1. 记忆链路 MUST 记录：`memory_triggered`、`memory_retrieved`、`memory_decision_made`
2. 事件 MUST 入库，并周期跟踪：命中率、采纳率、噪音率、新鲜度、到期治理

### 4.2 运行时历史回溯（Runtime History Recall）

最小目标：让结构化摘要可回指执行现场，并让模型在需要时按 step 回看原始消息。

基础索引：
1. Runtime 会话消息 SHOULD 持久化 `run_id` 与 `step_id`。
2. `run_id` 用于区分执行批次；`step_id` 用于区分单次 run 内部执行单元。
3. 涉及原始执行现场回看时，MUST 优先使用 `run_id + step_id`，MUST NOT 依赖临时 `step` 计数或模糊“上一轮/前面那次”描述。

Anchor 约定：
1. 结构化摘要中的 `decision / constraint / artifact` MAY 携带 `source_anchor`。
2. `source_anchor` 第一版仅索引：
   - `run_id`
   - `step_id`
3. 当来源跨多个 step 或置信度不足时，SHOULD 省略 `source_anchor`，MUST NOT 为了覆盖率强行写错锚点。

回溯工具：
1. 运行时历史回溯 MUST 通过显式工具 `history_recall` 触发。
2. `history_recall` 默认粒度 MUST 为 `step`。
3. 调用时 SHOULD 直接传 `task_id + run_id + step_id`，或传结构化对象中的 `source_anchor`。
4. Tool 返回结果 SHOULD 保留原始消息顺序，并包含基础定位信息（如 `message_id`、`role`、`tool_call_id`）。

使用边界：
1. 需要核对原始约束、失败现场、工具返回、关键决策来源时，SHOULD 使用 `history_recall`。
2. Runtime 当前不做默认自动回溯；是否回看历史由 Agent 显式决策。
3. 系统经验记忆（`memory_card`）与运行时历史回溯 MUST 分离：
   - `memory_card` 解决跨任务经验复用
   - `history_recall` 解决当前任务执行现场回看
4. 当问题属于“当前任务这一步到底发生了什么”，MUST 优先使用 `history_recall`；当问题属于“过去类似任务有没有可复用经验”，SHOULD 优先使用经验搜索。
5. 若当前任务现场与已知经验都可能相关，SHOULD 先回看当前 step 现场，再补充经验搜索，避免把跨任务经验误当成当前执行事实。

## 5. Skill 能力路由

1. 任务开始时，Agent MUST 主动判断所需能力，不等待用户提示。
2. 复杂任务 SHOULD 组合多个能力模块。
3. 关键能力决策 MUST 可追溯（为何调用/为何不调用）。
