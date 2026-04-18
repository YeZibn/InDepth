# InDepth Planning LLM + `plan_task` 单入口设计稿 V1

更新时间：2026-04-18  
状态：Superseded by runtime three-phase implementation

## 0. 当前落地状态

截至 2026-04-18，本稿中“单入口 `plan_task`”方向已基本落地，但 planning 形态已演进为 Runtime 三阶段中的 prepare phase。

1. `plan_task` 已成为唯一对外 todo 变更入口
2. `create_task/update_task` 已从工具注册中移除
3. Runtime 自动落盘路径已统一为只调用 `plan_task`
4. prepare 结果已收口为统一 plan envelope，并由 Runtime 自动衔接 `plan_task`
5. `plan_ready` / `recommended_update_task_args` / `recommended_mode` 已从实现链路中移除
6. active todo 全文已经输入到 prepare 规划链路
7. CLI 已增加可见的 `[Prepare]` 摘要输出

尚未完全落地的部分：

1. 本稿关于“独立无工具 Planning LLM 子模型”的设想未继续推进
2. 当前采用的是“同一主链路 LLM + phase overlay”，而不是独立 planning provider
3. 本稿后续阅读应以 `runtime-three-phase-state-machine-design-v1.md` 为准

## 1. 背景

当前 Todo 规划链路已经经历过一轮收口：

1. Runtime 起始阶段会先做前置 planning 判断
2. 若判断需要 todo，则后续进入 create / update 路径
3. create / update 已逐步从“模型自由选择”走向“运行时编排”

但当前实现仍存在三个结构性问题：

1. planning 阶段的职责还不够纯  
   它容易滑向本地探索、文件读取甚至早期执行，导致“思考”和“执行”重新混杂。

2. create / update 仍是独立工具  
   即使它们被标记为 hidden，本质上仍是 registry 中的可调用工具，协议口径与实现口径仍不完全一致。

3. planning 输入上下文不够稳定  
   如果只给摘要，容易丢失当前 todo 中最关键的任务主线、fallback record、recovery decision 和 follow-up subtask 关系。

因此，本稿提出进一步收口：

1. 以 prepare phase 承担 planning 入口
2. Runtime 统一自动调用 `plan_task`
3. `create/update` 全部下沉为 `plan_task` 内部函数
4. prepare 输入直接包含完整 todo 全文，而不是摘要

## 2. 目标

1. 让 prepare/planning 阶段只负责思考与定骨架，不直接落盘
2. 保留一个对外唯一 Todo 规划入口：`plan_task`
3. 让 create / update 只作为 `plan_task` 的内部实现细节存在
4. 让 planning 在已有 todo 场景下看到完整任务事实源，减少摘要丢失语义
5. 进一步降低模型误用工具、误判入口、重复建 todo 的概率

## 3. 非目标

1. 本稿不重做 todo markdown schema
2. 本稿不改变 recovery 状态机本身
3. 本稿不让 planning 阶段直接承担广泛执行职责
4. 本稿不让 Planning LLM 输出复杂状态集合

## 4. 核心判断

### 4.1 prepare 是 planning phase，而不是独立 tool

当前演进后的 planning 阶段本质是：

1. 判断这次是否需要 todo
2. 如果需要，产出一份完整 todo 计划
3. 不负责探索本地世界
4. 不负责执行任何落盘动作

如果给它无限制工具能力，它就很容易合理化为：

1. “我先看一下本地文件”
2. “我先验证一下环境”
3. “我先补一点事实再决定”

这样 planning 很快就会退化回 execution，阶段边界再次混乱。

当前实现中的收口原则是：

1. 由 Runtime 先收集已知事实
2. planning 主要通过 prompt contract 约束
3. 不再依赖 phase 工具硬白名单
4. 重点限制“不要扩张执行”，而不是完全禁止观察类能力

### 4.2 prepare 输入应包含完整 todo 全文

如果只给摘要，会丢失很多关键语义：

1. subtask 的原始表述
2. acceptance criteria
3. fallback record 细节
4. recovery decision 细节
5. follow-up subtasks 与原 subtask 的关系

当前 todo 不再只是简单清单，而是当前 task 周期内的事实源。

因此，在已有 active todo 时：

1. Runtime 不应只传摘要
2. 应直接读取当前 active todo 全文
3. 将 todo 全文作为 prepare 规划输入之一

注意：

1. 读取 todo 文件这件事由 Runtime 完成
2. prepare 规划器只消费 Runtime 已提供事实
3. 它是“被喂入完整 todo”，而不是“自己去读 todo”

### 4.3 对外只保留 `plan_task`

从协议心智看，真正稳定的约束应是：

1. Runtime 先做 planning judgement
2. 若需要 todo，则统一进入 `plan_task`
3. `plan_task` 内部决定到底是 create 还是 update

这比同时暴露：

1. `plan_task`
2. `create_task`
3. `update_task`

更干净，也更符合“单入口”原则。

## 5. 设计方案

## 5.1 总体链路

建议链路如下：

1. 用户输入进入 Runtime
2. Runtime 恢复当前 active todo context
3. 若存在 active todo，Runtime 读取当前 todo 全文
4. Runtime 调用无工具 Planning LLM
5. Planning LLM 输出：
   - `should_use_todo`
   - 若需要 todo，则输出完整 todo 计划
6. Runtime 分流：
   - `should_use_todo = false` -> 普通执行
   - `should_use_todo = true` -> 自动调用 `plan_task`
7. `plan_task` 内部决定 create/update
8. 进入正常执行 / recovery / finalization

## 5.2 Planning LLM 输入契约

Planning LLM 的输入建议固定为以下结构：

1. `user_input`
   - 当前这条用户请求原文

2. `active_todo_exists`
   - 当前是否已有 active todo

3. `active_todo_id`
   - 若存在 active todo，则传入 todo_id

4. `active_todo_full_text`
   - 若存在 active todo，则传入当前 todo 文件全文
   - 若不存在，则为空字符串

5. `active_subtask_number`
   - 当前 active subtask 编号，没有则为空

6. `execution_phase`
   - 当前执行阶段，例如 `planning / executing / recovering / closed`

7. `latest_recovery`
   - 最近一次 recovery 结构化事实
   - 没有则为空对象

8. 固定 Planning 指令
   - 无工具
   - 不能探索
   - 只能基于已知事实判断
   - 若采用 todo，则应一次性给出完整 todo 计划

### 5.2.1 不应输入的内容

以下内容不建议直接输入给 Planning LLM：

1. 任意 bash 输出全集
2. 工作区扫描结果全集
3. 无关文件正文
4. 整段历史消息
5. 与当前 task 主线无关的恢复噪音

原则是：

1. 给“任务事实”
2. 不给“执行噪音”

## 5.3 Planning LLM 输出契约

为保持简单，输出建议只保留：

1. `should_use_todo`
2. `task_name`
3. `context`
4. `split_reason`
5. `subtasks`
6. `notes`

语义约定：

1. 当 `should_use_todo = false`
   - 其余字段可为空

2. 当 `should_use_todo = true`
   - 必须一次性给出完整 todo 计划
   - 不再保留 `plan_ready`
   - 不再返回额外复杂 planning 状态

## 5.4 `plan_task` 的职责

`plan_task` 继续保留为唯一对外 Todo 落盘入口，但其内部职责进一步明确为：

1. 校验 Planning LLM 给出的完整 todo 计划
2. 根据当前 active todo context 决定 create/update
3. 调用内部函数执行真实落盘
4. 返回统一结果给 Runtime

也就是说：

1. Planning LLM 不直接落盘
2. Runtime 不直接 create/update
3. 只有 `plan_task` 真正改动 todo

## 5.5 create / update 下沉

建议将：

1. `create_task`
2. `update_task`

从 registry 工具层移除，改为 `todo_tool.py` 内部函数，例如：

1. `_create_todo_from_plan(...)`
2. `_update_todo_from_plan(...)`

### 5.5.1 下沉后的边界

对外工具：

1. `plan_task`
2. `update_task_status`
3. `update_subtask`
4. `record_task_fallback`
5. `plan_task_recovery`
6. `append_followup_subtasks`
7. 其他查询工具

内部函数：

1. `_create_todo_from_plan(...)`
2. `_update_todo_from_plan(...)`

这样：

1. 模型看不到 create/update
2. guard 只需要围绕 `plan_task`
3. 文档与协议口径彻底一致

## 5.6 Runtime 的职责

Runtime 在本方案下承担三件事：

1. 收集 planning 已知事实
   - 用户输入
   - active todo context
   - 完整 todo 全文
   - latest recovery

2. 调用无工具 Planning LLM

3. 当 `should_use_todo = true` 时，自动调用 `plan_task`

因此 Runtime 不再需要：

1. 自动调用 `update_task`
2. 自动 create/update 双分支编排

而只需要：

1. 自动 `plan_task`

## 6. 和当前实现相比的变化

当前实现：

1. Runtime 先做 prepare
2. create 路径自动 `plan_task`
3. update 路径自动 `update_task`

目标实现：

1. Runtime 先做无工具 Planning LLM judgement
2. 若 `should_use_todo = true`，统一自动 `plan_task`
3. `plan_task` 内部 create/update

因此变化核心是：

1. 取消 `plan_ready`
2. 取消 Runtime 侧 create/update 双分流
3. 取消对外 `create_task/update_task`
4. 把 planning 输入升级为“完整 todo 全文”

## 7. 风险与权衡

### 7.1 风险：Planning LLM 可能更保守

因为它没有工具，所以它不能主动补证据。

但这其实是有意设计：

1. planning 负责判断
2. execution 负责探索

这会让阶段更诚实，而不是更激进。

### 7.2 风险：完整 todo 输入会增加 token 开销

这是真实代价。

但在已有 active todo 的场景下，完整 todo 恰恰是最关键的任务事实源，通常值得优先保留。

后续可再考虑：

1. 超长 todo 的裁剪策略
2. 只保留当前活跃主线及 recovery 相关区块

但本稿先不提前优化。

## 8. 最小落地步骤

建议按以下顺序落地：

1. 新增 / 改造 Planning LLM 阶段
   - 无工具
   - 输入支持完整 todo 全文
   - 输出采用简化结构

2. `plan_task` 内部吸收 create/update 判定与执行

3. 将 `create_task/update_task` 下沉为内部函数

4. 从工具注册中移除 `create_task/update_task`

5. 收紧 Runtime guard
   - 只围绕 `plan_task`

6. 更新测试与参考文档

## 9. 验收口径

至少满足以下条件：

1. Planning LLM 无工具
2. 存在 active todo 时，Planning LLM 输入中包含完整 todo 全文
3. Runtime 不再自动直接调用 `update_task`
4. Runtime 在需要 todo 时统一自动调用 `plan_task`
5. `plan_task` 内部根据当前上下文执行 create/update
6. `create_task/update_task` 不再作为注册工具暴露给模型
7. 文档、设计稿、实现三层口径一致

## 10. 一句话总结

本稿的核心不是继续堆更多 planning 状态，而是把链路彻底收直：

1. Planning LLM 只思考
2. Runtime 只编排
3. `plan_task` 只负责唯一落盘入口
4. create/update 成为内部实现细节
5. planning 在已有 todo 场景下看到完整 todo 全文，而不是失真的摘要
