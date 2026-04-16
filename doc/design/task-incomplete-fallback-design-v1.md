# InDepth 任务未完成兜底设计方案（Task Incomplete Fallback, V1）

更新时间：2026-04-16  
状态：Draft（讨论中，未实现）

## 1. 背景

当前 InDepth 已有 todo/subtask 编排能力，但对“任务没有完成时系统应该如何收口、如何恢复、如何挽救”还缺少一套完整设计。

现状问题主要有三类：
1. 协议层已经引入 `blocked/cancelled` 等语义，但工具层真实状态机仍只有 `pending/in-progress/completed`。
2. “没完成”目前更像一种口头说明，而不是结构化运行结果，导致主 Agent、SubAgent、Verifier、最终交付之间缺少统一表达。
3. 对失败后的下一步动作缺乏标准化处理，容易出现两种极端：
   - 过早放弃，主流程失去挽救机会
   - 机械重试，重复消耗预算但没有修复根因

因此，本设计稿关注的不是“如何标记失败”本身，而是：
- 如何识别未完成
- 如何保留足够上下文
- 如何决定下一步
- 如何最大化挽救当前失败

## 2. 目标

1. 为 todo/subtask 定义统一的“未完成”分类。
2. 为每个未完成项提供统一的兜底信息结构。
3. 为主 Agent 提供一套“失败后怎么挽救”的标准动作集。
4. 允许系统在部分失败时继续推进非关键路径，并在最终交付中诚实表达未完成项。
5. 为后续工具实现提供清晰的数据模型与流转规则。

## 3. 非目标

1. 本设计稿不直接修改 `todo_tool` 代码。
2. 本设计稿不在本轮落地数据库或 markdown 文件 schema。
3. 本设计稿不定义 UI 呈现细节。

## 4. 设计原则

1. 诚实优先：系统不能把“未完成”包装成“已完成”。
2. 可恢复优先：失败记录必须服务于下一步恢复，而不是只做归档。
3. 最小阻塞：非关键路径失败不应立刻拖死整个主流程。
4. 根因导向：优先修复导致失败的原因，而不是盲目重试。
5. 主流程可汇总：主 Agent 必须能把未完成项结构化解释给用户。
6. 主动恢复优先：系统默认先尝试低风险恢复，而不是第一时间停下来请求确认。
7. 保留价值优先：恢复目标首先是保留已有有效产出，其次才是追求形式上的“全完成”。
8. 边界清晰：主动恢复不得擅自改变用户目标、显著扩大范围、覆盖已有有效产物或无限重试。

## 5. 核心设计：未完成分类

### 5.1 为什么不能只用一个“失败”

“没完成”并不总是同一种情况：
- 有的是依赖没满足，还不能做
- 有的是做了但做错了
- 有的是只完成了一半
- 有的是主动止损，不再继续

如果把这些都压成一个 `failed`，后续系统就无法决定是该等待、重试、拆分、转交还是直接放弃。

### 5.2 建议分类

建议在协议层把未完成分成以下类型：

1. `blocked`
   当前无法继续执行，通常因为依赖未满足、外部资源不可用、上游结果缺失。

2. `failed`
   已经执行，但执行报错、输出不符合要求、或验证失败。

3. `partial`
   已有部分有效产出，但尚未满足完整完成条件。

4. `awaiting_input`
   明确在等待用户、调用方或外部系统补充信息。

5. `timed_out`
   达到预算上限、重试次数上限或超时阈值，被系统止损。

6. `abandoned`
   经评估后主动停止，不再继续投入。

这几个状态的核心差异是：
- `blocked` 强调“现在不能继续”
- `failed` 强调“已经尝试但未成功”
- `partial` 强调“结果可部分保留”
- `awaiting_input` 强调“等待输入”
- `timed_out` 强调“预算止损”
- `abandoned` 强调“明确放弃”

## 6. 兜底信息模型

仅有状态还不够；系统还需要一份统一的未完成描述。

建议为每个未完成 subtask 增加一段独立结构：`fallback_record`

建议最小字段：
1. `state`: `blocked | failed | partial | awaiting_input | timed_out | abandoned`
2. `reason_code`: 稳定枚举，用于程序判断
3. `reason_detail`: 面向人类的说明
4. `impact_scope`: 对整体任务的影响范围
5. `retryable`: 是否值得重试
6. `required_input`: 恢复执行还缺什么
7. `suggested_next_action`: 推荐下一步动作
8. `last_attempt_summary`: 最近一次尝试做了什么
9. `evidence`: 错误输出、验证结论、关键日志、产物路径
10. `owner`: 当前由谁负责后续处理（main/subagent/<role>/user）

可选字段：
1. `failure_stage`: `planning | execution | verification | handoff`
2. `retry_count`
3. `retry_budget_remaining`
4. `created_from_subtask`
5. `resume_condition`
6. `degraded_delivery_allowed`

### 6.1 `reason_code` 建议枚举

建议优先定义稳定原因码，避免全靠自然语言：
- `dependency_unmet`
- `tool_error`
- `validation_failed`
- `missing_context`
- `waiting_user_input`
- `waiting_external_system`
- `budget_exhausted`
- `subagent_empty_result`
- `subagent_execution_error`
- `output_not_verifiable`
- `requirement_changed`
- `deprioritized`

## 7. 触发条件

系统进入“未完成兜底”的触发条件建议包括：

1. 依赖校验失败
   例：前置 subtask 未 `completed`，当前任务不能推进。

2. 工具执行失败
   例：bash 命令失败、文件读写失败、搜索失败。

3. 验证未通过
   例：产物缺失、测试未通过、审查结论为不合格。

4. 预算耗尽
   例：达到时间上限、轮次上限、重试次数上限。

5. 等待外部输入
   例：需要用户澄清、需要 API 返回、需要他人交付。

6. 主 Agent 主动降级
   例：发现该 subtask 不影响主目标，可转为部分交付。

7. 需求变化
   例：用户更改方向，旧 subtask 失去继续价值。

## 8. 失败后的“挽救”设计

这一节是本方案最关键的部分。

### 8.1 挽救的定义

这里的“挽救”不是简单重试，而是：
- 先识别失败根因
- 再选择成本最低、成功率最高的恢复路径
- 尽量保留已产出的有效部分
- 避免把局部失败扩散成整体失败

所以“挽救”本质上是一套动作决策，而不是一个状态。

### 8.2 失败后的标准动作集

建议系统支持以下标准动作：

1. `retry`
   原路径重试。只适用于偶发性失败，且根因被判断为暂时性。

2. `retry_with_fix`
   先修正上下文、参数、依赖或环境，再按原路径重试。

3. `split`
   把当前 subtask 再拆细，缩小失败范围。

4. `fallback_path`
   切换到次优方案或降级方案完成目标。

5. `handoff`
   转交给其他角色、其他 SubAgent 或主 Agent。

6. `pause`
   暂停，等待外部输入或依赖满足后再恢复。

7. `degrade`
   放弃该 subtask 的完整达成，允许主任务以部分结果交付。

8. `abandon`
   明确放弃，记录原因并停止继续投入。

### 8.3 挽救不是默认重试

默认重试有很大风险：
- 如果失败根因是依赖缺失，重试没有意义
- 如果失败根因是任务过大，重试只会重复失败
- 如果失败根因是需求不清，重试只会扩大错误

因此，标准策略应该是：

1. 先判断失败类型
2. 再判断是否可修复
3. 再选择最小成本的挽救动作

### 8.4 失败后的挽救决策矩阵

建议采用如下决策逻辑：

1. `dependency_unmet`
   推荐动作：`pause` 或 `split`
   说明：不要重试当前动作，应等待依赖满足或拆出补前置子任务。

2. `tool_error`
   推荐动作：`retry_with_fix`
   说明：先定位错误来源，再决定是否重试。

3. `validation_failed`
   推荐动作：`split` 或 `handoff`
   说明：通常表示“执行结束但质量不过关”，更适合拆出修复项或交给 reviewer/verifier 协同。

4. `missing_context`
   推荐动作：`pause` 或 `awaiting_input`
   说明：先补信息，不宜盲做。

5. `budget_exhausted`
   推荐动作：`degrade`、`split` 或 `abandon`
   说明：应先止损，再决定是否保留部分结果或下轮继续。

6. `subagent_empty_result` / `subagent_execution_error`
   推荐动作：`handoff`、`retry_with_fix` 或 `split`
   说明：不要立刻主 Agent 原样重复做同一大任务，应先缩小范围或补充上下文。

### 8.5 挽救优先级

建议按以下优先级尝试：

1. 保留已完成部分
2. 修复根因
3. 缩小任务范围
4. 切换执行者
5. 切换路径
6. 允许降级交付
7. 最后才是明确放弃

换句话说，系统应优先挽救“价值”，而不是优先挽救“形式上的完整完成”。

### 8.6 `handoff` 的精确定义

本方案中的 `handoff` 指：
在不改变当前目标的前提下，把某个未完成 subtask 的后续处理责任转交给另一个更合适的处理者或处理层。

它强调的是“责任转移”，不是“任务放弃”，也不是“用户确认”本身。

建议把 `handoff` 细分为两类：

1. `execution_handoff`
   执行责任转移。
   含义：当前执行者不再继续直接处理，由另一个更合适的执行者接管该 subtask 或其后续子步骤。

2. `decision_handoff`
   决策责任转移。
   含义：当前执行者不再自行决定下一步，而是把“接下来怎么处理”交给更高层来判断。

### 8.6.1 `execution_handoff`

适用场景：
1. 当前执行者的角色不再匹配问题类型。
2. 当前问题更适合另一种工具或角色能力。
3. 当前 subtask 已从“执行问题”转变为“验证问题”或“诊断问题”。

典型例子：
1. `builder -> verifier`
   代码已改完，但验证不过，需要 verifier 接手定位失败点。

2. `researcher -> builder`
   调研已完成，后续进入实现阶段，责任从研究转到构建。

3. `SubAgent -> 主 Agent`
   子代理连续失败，需要主 Agent 重写上下文、重排计划或重新定义目标边界。

设计约束：
1. handoff 前后，原始目标原则上不变。
2. 若目标明显变化，则不应仅视为 handoff，而应升级为 `fallback_path` 或用户确认。
3. handoff 后必须生成新的明确负责人。

### 8.6.2 `decision_handoff`

适用场景：
1. 当前执行者无法安全判断下一步是否值得继续。
2. 下一步动作会影响范围、成本、质量标准或交付承诺。
3. 当前失败已不只是执行问题，而是策略问题。

典型例子：
1. `SubAgent -> 主 Agent`
   子代理发现两条修复路径都可行，但代价不同，需要主 Agent 选策略。

2. `主 Agent -> 用户`
   系统可以继续做，但会明显增加时间成本，或只能接受部分交付，需要用户拍板。

3. `builder -> 主 Agent`
   构建失败的根因不明，是否继续排查、是否降级交付，需要主 Agent 决定。

设计约束：
1. `decision_handoff` 的产物不是“直接完成”，而是“明确下一步决策”。
2. 若 decision handoff 指向用户，建议复用 `awaiting_user_input` 机制承接。
3. decision handoff 结束后，应产出新的恢复动作，而不是停留在“等待中”。

### 8.6.3 与其他动作的边界

为了避免语义重叠，建议明确：

1. `retry`
   同一执行者按原路径重试，不发生责任转移。

2. `split`
   任务被拆小，但责任可以不变；若拆小后交给别人，才与 handoff 组合出现。

3. `fallback_path`
   目标路径发生变化；如果只是换执行者但路径不变，不应算 fallback path。

4. `awaiting_input`
   是一种等待状态，不等同于 handoff；只有当“决定权”被交给用户时，才形成 `decision_handoff -> user`。

一句话区分：
- `retry` 是“还是我做”
- `split` 是“拆小再做”
- `handoff` 是“换人处理”
- `fallback_path` 是“换路处理”

## 9. 下一步如何挽救目前失败的方法

这是本方案对“下一步怎么做”的具体回答。

### 9.1 通用挽救流程

任何失败发生后，推荐统一走以下流程：

1. 记录失败
   写入 `fallback_record`，保留状态、原因、证据、影响。

2. 判断影响范围
   区分：
   - 是否阻塞关键路径
   - 是否可以部分交付
   - 是否已有可复用产出

3. 判断可恢复性
   核心问题：
   - 根因是否明确
   - 根因是否可修复
   - 修复成本是否在预算内

4. 选择挽救动作
   在 `retry / retry_with_fix / split / fallback_path / handoff / pause / degrade / abandon` 中做选择。

5. 显式生成下一步动作
   不要只记录“失败了”，必须形成下一步动作，例如：
   - 补充上下文
   - 新增前置子任务
   - 拆出独立修复 subtask
   - 切换给 verifier/reviewer
   - 进入等待输入

6. 更新主流程
   主 Agent 决定：
   - 继续推进其他 ready subtasks
   - 或暂停主流程等待恢复

### 9.2 “挽救目前失败”的具体方法论

当前最推荐的方法不是“重做一遍”，而是按下面顺序处理：

1. 先保留当前失败现场
   包括错误输出、失败命令、已有产物、最近一次尝试说明。

2. 识别失败属于哪一类
   是依赖问题、执行错误、验证不过、信息缺失、预算止损，还是 SubAgent 结果异常。

3. 把原失败任务改写成“可修复动作”
   例子：
   - 从“实现失败”改写成“定位构建失败根因”
   - 从“调研没做完”改写成“补齐缺失证据 A/B/C”
   - 从“SubAgent 没产出”改写成“缩小检索范围并重发子任务”

4. 如果根因不明，不直接重试
   应先新增一个诊断型 subtask，例如“收集失败日志并判断是否可重试”。

5. 如果部分结果可用，优先保留并降级交付
   不必为了追求完全完成而放弃已经有价值的部分结果。

6. 如果失败任务太大，优先拆小
   大任务失败最常见的挽救方式不是“再试一次”，而是“拆成两个更小的可验证动作”。

7. 如果当前执行者不合适，优先换角色
   例如：
   - builder 做完但验证不过，交给 reviewer/verifier
   - researcher 返回空结果，主 Agent 重写问题后再分派

8. 如果预算已经不值，允许明确止损
   明确标记为 `timed_out` 或 `abandoned`，并附上：
   - 当前可交付内容
   - 未完成部分
   - 继续推进所需输入
   - 建议下一步

### 9.3 一句话原则

下一步挽救失败的方法，不是“再试一次”，而是“先把失败转化成一个更小、更明确、可恢复的下一步动作”。

## 10. 与 todo/subtask 的关系

建议未来在 todo 体系中采用“两层模型”：

1. 状态层
   保持简洁，负责表达当前生命周期状态。

2. 兜底层
   通过 `fallback_record` 保存未完成原因、证据、恢复条件和建议动作。

这样可以避免把所有细节都塞进状态字段里。

## 10.1 恢复动作由谁执行

前面定义的恢复动作集，并不意味着所有动作都应无条件自动执行。

更合理的设计是：
1. 系统先根据 `fallback_record` 生成候选恢复动作。
2. 再根据动作风险、影响范围、是否涉及需求变更，决定由谁来触发执行。

建议分成三档：

1. 自动执行（Auto Recovery）
   风险低、路径明确、不会改变用户目标或破坏已有产物。

2. 主 Agent 决策后执行（Agent-mediated Recovery）
   需要结合上下文判断，但通常不需要额外打断用户。

3. 用户确认后执行（User-confirmed Recovery）
   会改变目标、交付范围、成本、时间或存在明显副作用，必须让用户拍板。

换句话说：
- 动作集定义“系统可以做什么”
- 执行级别定义“系统什么时候可以自己做”

## 10.2 自动执行的动作

建议以下动作默认允许系统自动执行：

1. `pause`
   当原因明确是等待依赖或等待外部输入时，系统可自动进入等待态。

2. `retry`
   仅限低风险、瞬时性、幂等失败，例如临时读失败、短暂空结果、可安全重试的一次性校验。

3. `retry_with_fix`
   仅当修复动作是局部、可逆、低风险时允许自动执行。
   例：
   - 补充缺失参数
   - 收窄搜索范围
   - 调整提示词约束
   - 切换到更小的验证命令

4. `split`
   仅限拆分为更小的诊断/修复 subtask，不改变最终目标。

5. `handoff`
   仅限角色内合理切换，且不扩大权限边界。
   例：
   - `builder` 失败后交给 `verifier` 检查
   - `researcher` 空结果后交给主 Agent 重写问题再重发

自动执行的前提条件建议是：
1. 不改变用户目标
2. 不扩大工作范围
3. 不引入明显额外成本
4. 不覆盖已有有效产物
5. 不涉及破坏性操作

## 10.3 需要主 Agent 决策的动作

建议以下动作由主 Agent 明确判断后再执行：

1. `retry_with_fix`
   当修复动作已不再是局部小修，而会影响方案或上下文时。

2. `split`
   当重新拆分后会显著改变执行计划或新增多条并行流时。

3. `fallback_path`
   当需要在多种替代方案中选一个时。

4. `handoff`
   当切换执行者会改变责任分工、工具能力或上下文边界时。

5. `degrade`
   当需要决定“接受部分结果”还是“继续追求完整完成”时。

主 Agent 决策层的职责是：
1. 判断该失败是否影响关键路径
2. 判断当前预算是否值得继续投入
3. 判断部分交付是否可接受
4. 判断替代路径是否仍符合用户目标

也就是说，主 Agent 应该像恢复编排器，而不是简单的动作转发器。

## 10.4 必须用户确认的动作

建议以下动作必须经过用户确认：

1. `degrade`
   当部分交付会明显降低预期结果时。

2. `abandon`
   当系统准备停止某个关键 subtask 或整体目标时。

3. `fallback_path`
   当替代路径会改变原始需求、结果口径、时间成本或资源消耗时。

4. 高成本 `retry_with_fix`
   当修复意味着明显追加时间、轮次、外部调用或大规模重构时。

5. 高风险 `handoff`
   当切换执行者可能导致结果风格、质量标准或权限边界变化时。

6. 任何带有“删除、覆盖、回滚、大规模修改”风险的恢复动作
   即使目标是恢复，也不能绕过用户确认。

### 10.4.1 判断标准

建议满足任一条件即要求用户确认：
1. 改变需求范围
2. 改变交付标准
3. 明显增加执行成本
4. 放弃已有路径或已有产物
5. 引入不可逆风险

### 10.4.2 与现有 `awaiting_user_input` 的关系

当前 Runtime 已有 `awaiting_user_input` 机制，适合作为这类恢复动作的挂起出口。

建议后续落地时复用这一思路：
1. 当恢复动作需要用户拍板时，不继续自动推进。
2. 进入等待态，并附带结构化恢复问题。
3. 用户补充后，再决定是否恢复执行。

这意味着“恢复流程”不必额外发明一套全新的暂停机制，可以沿用现有澄清挂起能力。

## 10.5 恢复动作分级矩阵

建议先给每个恢复动作定义默认执行级别：

1. `pause`
   默认：自动执行

2. `retry`
   默认：自动执行
   例外：超过重试预算时升级为主 Agent 决策

3. `retry_with_fix`
   默认：主 Agent 决策
   例外：局部、低风险修复可自动执行

4. `split`
   默认：主 Agent 决策
   例外：只拆成诊断子任务时可自动执行

5. `handoff`
   默认：主 Agent 决策
   例外：标准 builder->verifier / researcher->main 这类窄边界切换可自动执行

6. `fallback_path`
   默认：用户确认
   例外：已经在协议中定义好的次优路径可由主 Agent 决策

7. `degrade`
   默认：用户确认
   例外：协议中已声明“允许部分交付”的非关键 subtask，可由主 Agent 决策

8. `abandon`
   默认：用户确认
   例外：非关键、低价值、已被新需求替代的 subtask，可由主 Agent 决策

## 10.6 推荐执行顺序

为了避免系统过度激进，建议恢复动作执行顺序为：

1. 先尝试自动执行的低风险动作
2. 自动动作无效时，升级到主 Agent 决策
3. 涉及目标、范围、成本、放弃时，再升级到用户确认

一句话总结：
系统可以推荐动作，也可以在低风险场景直接执行动作；但只要恢复动作会改变任务边界或交付承诺，就必须上升到更高决策层。

## 10.7 默认恢复模式：偏主动（Active Recovery by Default）

本方案当前默认采用“偏主动恢复”路线。

这意味着：
1. 系统在检测到 subtask 未完成后，默认不立即停下来请求确认。
2. 系统应先自动尝试低风险恢复动作。
3. 只有当恢复动作涉及目标、范围、成本、质量承诺或放弃决策时，才升级到主 Agent 或用户。

### 10.7.1 主动恢复不等于激进恢复

“偏主动”不表示系统可以无边界地一直尝试，而是表示：
1. 先做安全恢复
2. 再逐级升级
3. 不把低风险恢复成本转嫁给用户

建议默认恢复链路为：

1. 自动保留当前有效产出
2. 自动识别失败类型
3. 自动生成候选恢复动作
4. 自动执行低风险恢复动作
5. 若自动恢复失败，再升级为主 Agent 决策
6. 若恢复动作会改变交付承诺，再升级为用户确认

### 10.7.2 主动恢复的硬边界

即使采用主动模式，系统也必须满足以下硬约束：

1. 不改变用户目标
2. 不显著扩大工作范围
3. 不覆盖已有有效产物
4. 不绕过关键风险确认
5. 不无限重试

建议后续实现时加入默认预算：
1. 每个 subtask 的自动恢复轮次上限：2
2. 同一失败路径的原样 `retry` 上限：1
3. 达到阈值后必须升级，不允许继续静默自动尝试

### 10.7.3 主动模式下的默认动作策略

在偏主动模式下，建议默认行为如下：

1. `pause`
   自动执行。

2. `retry`
   自动执行，但受次数预算约束。

3. `retry_with_fix`
   对局部、可逆、低风险修复允许自动执行；否则升级为主 Agent 决策。

4. `split`
   对诊断型拆分允许自动执行；对会显著改变计划的拆分升级为主 Agent 决策。

5. `execution_handoff`
   对窄边界、标准角色切换允许自动执行；复杂切换升级为主 Agent 决策。

6. `fallback_path`
   默认不自动执行，优先由主 Agent 决策；若涉及结果口径变化，则需用户确认。

7. `degrade`
   默认不自动执行。
   非关键 subtask 可由主 Agent 决策；关键 subtask 需用户确认。

8. `abandon`
   默认不自动执行。
   非关键、低价值、被替代 subtask 可由主 Agent 决策；关键项需用户确认。

### 10.7.4 主动模式的一句话定义

系统默认有责任先把失败转化成一个更小、更安全、可继续推进的动作，而不是第一时间把失败抛回给用户。

## 10.8 恢复决策器（Recovery Decision Engine）

为了让上述恢复策略真正可执行，建议在协议层引入一个轻量恢复决策器。

它不是新的“大规划器”，而是一个失败后的下一步路由器，负责三件事：
1. 读取失败现场与 subtask 上下文
2. 生成候选恢复动作并排序
3. 给出执行级别与下一步可执行动作草案

一句话定义：
恢复决策器的职责不是“解释为什么失败”，而是“把失败转化成一个安全、明确、可继续推进的下一步”。

### 10.8.1 设计边界

恢复决策器不负责：
1. 直接修改用户目标
2. 绕过主 Agent 的全局编排职责
3. 替代 verifier 做质量判定
4. 在高风险场景下越权决定 `degrade/abandon`

恢复决策器负责：
1. 给出结构化恢复建议
2. 标记动作执行级别
3. 把多数恢复动作转成新的可执行 subtask 草案

## 10.9 恢复决策器输入模型

我建议恢复决策器不要只读 `fallback_record`，而是同时读取失败事实与任务上下文。

建议最小输入结构：`recovery_input`

1. `todo_id`
2. `subtask_id`
3. `subtask_name`
4. `subtask_goal`
5. `subtask_description`
6. `current_status`
7. `fallback_record`
8. `dependencies`
9. `dependents`
10. `is_on_critical_path`
11. `has_partial_value`
12. `partial_artifacts`
13. `current_owner`
14. `available_roles`
15. `retry_count`
16. `retry_budget_remaining`
17. `time_budget_remaining`
18. `allowed_degraded_delivery`
19. `user_confirmation_required`
20. `affected_goal_scope`

### 10.9.1 关键字段说明

1. `is_on_critical_path`
   用来区分“该失败会不会阻塞整体交付”。

2. `has_partial_value`
   用来区分“是否已经有可保留成果”。这是主动恢复模式里最关键的字段之一。

3. `retry_budget_remaining`
   用来防止系统无限重试。

4. `allowed_degraded_delivery`
   用来约束系统是否可以考虑部分交付。

5. `available_roles`
   用来判断是否存在合理的 `execution_handoff` 目标。

### 10.9.2 输入来源建议

建议后续实现时按以下来源组装输入：
1. todo/subtask 元数据：名称、依赖、负责人、状态
2. `fallback_record`：失败原因、证据、建议动作
3. runtime 上下文：预算、当前 run 状态、工具失败情况
4. 主 Agent 编排上下文：关键路径、允许降级、可用角色

## 10.10 恢复决策器输出模型

恢复决策器不应只返回一句“建议 split”，而应输出结构化恢复结果：`recovery_decision`

建议最小输出字段：
1. `primary_action`
2. `recommended_actions`
3. `decision_level`
4. `rationale`
5. `preserve_artifacts`
6. `next_subtasks`
7. `resume_condition`
8. `escalation_reason`
9. `stop_auto_recovery`
10. `suggested_owner`

### 10.10.1 字段说明

1. `primary_action`
   当前最优恢复动作。

2. `recommended_actions`
   候选动作列表，按优先级排序。

3. `decision_level`
   `auto | agent_decide | user_confirm`

4. `rationale`
   为什么选这个动作，而不是其他动作。

5. `preserve_artifacts`
   要保留的已有结果、日志、产物。

6. `next_subtasks`
   新的可执行动作草案。这是主动恢复里最重要的产物之一。

7. `resume_condition`
   什么条件满足后，可恢复原主线或关闭当前失败态。

8. `escalation_reason`
   如果不能自动执行，明确说明为什么升级。

9. `stop_auto_recovery`
   布尔值。用于防止在预算耗尽或风险升高后继续自动恢复。

10. `suggested_owner`
   建议下一步由谁执行：`main / subagent:<role> / user`

### 10.10.2 `next_subtasks` 结构建议

建议每个恢复子任务草案至少包含：
1. `name`
2. `goal`
3. `description`
4. `kind`
5. `owner`
6. `depends_on`
7. `acceptance_criteria`

其中 `kind` 建议是以下之一：
1. `diagnose`
2. `repair`
3. `retry`
4. `verify`
5. `handoff`
6. `resume`
7. `report`

### 10.10.3 输出示例

```json
{
  "primary_action": "split",
  "recommended_actions": ["split", "retry_with_fix", "execution_handoff"],
  "decision_level": "auto",
  "rationale": "当前失败根因不明，直接重试收益低，优先拆成诊断与修复两步。",
  "preserve_artifacts": ["logs/build-error.txt", "work/partial-output.md"],
  "next_subtasks": [
    {
      "name": "定位构建失败根因",
      "goal": "确认失败是否来自依赖缺失、参数错误或实现缺陷",
      "description": "收集错误日志并判断后续应重试、修复还是转交验证",
      "kind": "diagnose",
      "owner": "main",
      "depends_on": [],
      "acceptance_criteria": ["输出根因结论", "给出后续推荐动作"]
    },
    {
      "name": "基于诊断结果执行修复",
      "goal": "按已确认根因修复失败点",
      "description": "仅在诊断子任务完成后执行修复动作",
      "kind": "repair",
      "owner": "subagent:builder",
      "depends_on": ["diagnose:定位构建失败根因"],
      "acceptance_criteria": ["修复产物存在", "验证通过或给出新失败结论"]
    }
  ],
  "resume_condition": "diagnose 子任务已完成且确认存在可修复路径",
  "escalation_reason": "",
  "stop_auto_recovery": false,
  "suggested_owner": "main"
}
```

## 10.11 恢复决策规则

### 10.11.1 决策原则

恢复决策不应只由 `reason_code` 单独决定，而应综合以下四个维度：
1. 失败类型
2. 影响范围
3. 恢复成本
4. 风险级别

建议用“先筛掉不安全动作，再在剩余动作中选最优动作”的策略，而不是直接做硬编码映射。

### 10.11.2 推荐规则顺序

建议决策顺序如下：

1. 先保留已有有效产出
2. 判断是否允许继续自动恢复
3. 判断是否存在明显低风险动作
4. 判断是否需要拆分
5. 判断是否需要 handoff
6. 判断是否允许降级交付
7. 最后才考虑 abandon

### 10.11.3 基础规则表

1. `dependency_unmet`
   默认：
   - `primary_action = pause`
   - 候选：`pause`, `split`
   - 若依赖缺失来自遗漏动作，则额外生成前置 `diagnose/repair` subtask

2. `tool_error`
   默认：
   - `primary_action = retry_with_fix`
   - 候选：`retry_with_fix`, `split`
   - 若 `retry_count` 已达上限，则升级为 `agent_decide`

3. `validation_failed`
   默认：
   - `primary_action = split`
   - 候选：`split`, `execution_handoff`
   - 优先生成 “定位失败原因” + “修复后复验” 两个子任务

4. `missing_context`
   默认：
   - `primary_action = pause`
   - 候选：`pause`, `decision_handoff`
   - 若缺的是用户确认，则 `decision_level = user_confirm`

5. `budget_exhausted`
   默认：
   - `primary_action = split` 或 `degrade`
   - 候选：`split`, `degrade`, `abandon`
   - 若无部分价值且不在关键路径，可考虑 `abandon`

6. `subagent_empty_result`
   默认：
   - `primary_action = split`
   - 候选：`split`, `retry_with_fix`, `execution_handoff`
   - 优先让主 Agent 重写上下文，再决定是否重新分派

7. `subagent_execution_error`
   默认：
   - `primary_action = execution_handoff`
   - 候选：`execution_handoff`, `retry_with_fix`, `split`
   - 若错误与执行者角色不匹配有关，优先换角色而非原样重试

### 10.11.4 升级规则

建议满足任一条件时，停止自动恢复并升级：
1. `retry_budget_remaining <= 0`
2. 连续两轮自动恢复没有缩小问题范围
3. 恢复动作开始影响关键路径交付承诺
4. 恢复动作需要放弃已有路径或已有产物
5. 恢复动作开始显著增加成本

升级目标建议为：
1. 普通复杂恢复：升级到 `agent_decide`
2. 影响范围/质量承诺/成本边界：升级到 `user_confirm`

## 10.12 恢复动作与 subtask 落地规则

我建议大多数恢复动作都沉淀成新的 subtask，而不是只停留在建议层。

### 10.12.1 哪些动作必须落成新的 subtask

建议以下动作默认转成新 subtask：
1. `retry_with_fix`
2. `split`
3. `execution_handoff`
4. `decision_handoff`
5. `fallback_path`
6. `degrade`
7. `report`

原因：
1. 可追踪
2. 可验证
3. 可复盘
4. 可避免“顺手修一下”吞掉执行链路

### 10.12.2 哪些动作可以不新建 subtask

建议以下动作可在原 subtask 内完成：
1. `pause`
2. 一次预算内的原样 `retry`

但即使不新建 subtask，也应写入：
1. 当前恢复尝试次数
2. 最近一次尝试摘要
3. 下次升级条件

### 10.12.3 推荐拆分模板

当失败原因不明时，建议统一拆成两步：

1. `diagnose`
   明确根因、判断是否可恢复。

2. `repair`
   基于诊断结果做修复。

若修复后仍需要质量确认，再追加：

3. `verify`
   确认修复是否真正闭环。

这套模板适合大多数：
1. 构建失败
2. 调研无结果
3. 验证不通过
4. SubAgent 空返回

### 10.12.4 与主流程的关系

新增恢复 subtask 后，主 Agent 应遵循：
1. 若不阻塞关键路径，优先继续推进其他 ready subtasks
2. 若阻塞关键路径，优先推进恢复链路
3. 恢复链路完成后，再决定是否恢复原主线

### 10.12.5 推荐实现策略

建议恢复决策器最终输出的不是“抽象建议”，而是“下一步可执行动作草案”。

也就是说，主 Agent 消费 `recovery_decision` 后，应能直接做以下事情之一：
1. 更新原 subtask 状态
2. 自动创建恢复 subtask
3. 指派新的 owner
4. 进入 `awaiting_user_input`

## 11. 推荐状态流转

建议协议层状态机升级为：

```text
pending -> in-progress -> completed
          \-> blocked
          \-> failed
          \-> partial
          \-> awaiting_input
          \-> timed_out

blocked -> in-progress | abandoned
failed -> retry_with_fix -> in-progress
partial -> in-progress | degraded_delivery
awaiting_input -> in-progress | abandoned
timed_out -> split | degrade | abandoned
```

说明：
1. `completed` 表示满足完成判据。
2. `partial` 表示已有有效产出，但未完整收口。
3. `abandoned` 表示明确终止。
4. `degraded_delivery` 可作为主任务层的交付结果，而不一定是 subtask 层的最终状态。

## 12. 最终交付要求

当主任务存在未完成 subtask 时，最终交付必须能回答：

1. 哪些 subtask 已完成
2. 哪些未完成
3. 每个未完成项属于哪种类型
4. 影响范围是什么
5. 是否还能恢复
6. 下一步建议是什么

如果系统只能说“有些没做完”，说明这套兜底设计仍然不够完整。

## 13. 分阶段落地建议

### Phase 1：协议与文档对齐

1. 明确未完成类型枚举
2. 明确 `fallback_record` 字段
3. 在文档中统一“失败后的挽救动作”术语

### Phase 2：工具层最小落地

1. `todo_tool` 支持 `blocked/failed/partial/awaiting_input/timed_out/abandoned`
2. `update_task_status` 支持附带原因与证据
3. `get_task_progress` 返回未完成细分信息
4. 为恢复 subtask 预留 `kind/owner/acceptance_criteria` 等字段

### Phase 3：主流程自动化

1. Runtime 在失败时自动生成最小 `fallback_record`
2. 主 Agent 集成恢复决策器，产出 `recovery_decision`
3. 多数恢复动作可自动转化成新的 follow-up subtask
4. SubAgent 失败能自动转换成“可恢复的 follow-up subtask”

### Phase 4：交付与评估联动

1. `verification_handoff` 纳入未完成项信息
2. 最终交付模板结构化展示未完成项与下一步建议
3. postmortem 统计失败类型与挽救效果
4. 观测恢复动作的成功率、升级率与止损率

## 14. 风险与讨论点

1. 状态分类过多可能导致使用门槛提升。
2. 如果 `fallback_record` 过重，调用成本会增加。
3. “部分交付”与“失败”边界需要进一步标准化。
4. 自动推荐挽救动作时，可能出现错误修复建议，需要规则回退。

## 15. 当前建议结论

当前最值得优先拍板的不是“要不要支持更多状态”，而是：

1. 是否接受未完成类型的细分模型。
2. 是否接受用独立 `fallback_record` 描述原因与恢复条件。
3. 是否接受“失败后的下一步必须转化成新的可执行动作”这一原则。
4. 是否接受“默认先做低风险主动恢复，再逐级升级”的恢复策略。
5. 是否接受 `degrade/abandon` 不默认自动执行。

如果这五点成立，后续无论落 markdown、SQLite、还是 runtime 事件模型，都会清晰很多。
