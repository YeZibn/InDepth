# InDepth Todo 编排参考

更新时间：2026-04-16

## 1. 目标

Todo 编排层负责把复杂任务拆成可执行、可验证、可审计的最小动作单元，并为主 Agent / SubAgent 协作提供统一状态面。

这份文档重点回答四个问题：
- 什么情况下必须创建 todo？
- subtask 应该如何设计，粒度多大才合适？
- subtask 没完成、被依赖阻塞、或需要交给 SubAgent 时，当前应该怎么处理？
- 当前执行协议与代码实现之间有哪些已经明确的差异？

相关代码：
- `InDepth.md`
- `app/tool/todo_tool/todo_tool.py`
- `app/tool/sub_agent_tool/sub_agent_tool.py`
- `doc/refer/agent-collaboration-reference.md`
- `doc/refer/tools-reference.md`

## 2. 设计定位

Todo 不是简单的待办清单，而是运行时编排层的事实源。

它承担三类职责：
- 规划职责：把复杂目标拆成有依赖关系的 subtask。
- 执行职责：给主 Agent 一个明确的“当前正在做什么”。
- 审计职责：把状态变化、依赖阻塞、完成进度沉淀为可回放记录。

在 InDepth 协议里，主 Agent 不能绕开 todo 直接做清单外动作；执行必须围绕 subtask 展开。

## 3. 何时必须创建 Todo

满足以下任一条件即必须创建 todo：
- 至少 3 个可识别步骤。
- 涉及跨文件或跨组件修改。
- 预计执行超过 5 分钟。
- 存在依赖关系或并行机会。

调用 `create_task` 时必须提供：
- `task_name`：主任务标题，必须体现“动作 + 对象”。
- `context`：范围、边界、交付物、验收口径、时间基准。
- `split_reason`：为什么需要拆分。
- `subtasks`：结构化子任务数组。

返回值中的 `todo_id` 是 todo 域唯一标识，后续状态更新、查询和报告生成都必须复用它。

## 4. Todo 数据模型

### 4.1 顶层结构

当前 `create_task` 会生成 `todo/<timestamp>_<sanitized_name>.md` 文件，主体结构包含：
- `Metadata`
- `Context`
- `Subtasks`
- `Dependencies`
- `Notes`

顶层元数据包括：
- `Todo ID`
- `Status`
- `Priority`
- `Created`
- `Updated`
- `Progress`

### 4.2 Subtask 结构

当前实现中，每个 subtask 会落为：
- `Task <n>: <name>`
- `Status`
- `Priority`
- `Dependencies`
- `Split Rationale`
- 复选描述项

`create_task` 支持的 subtask 输入字段：
- `name` 或 `title`
- `description`
- `priority`
- `dependencies`
- `split_rationale` / `split_reason` / `rationale` / `reason`

### 4.3 依赖派生信息

`todo_tool` 会根据依赖关系额外生成一段依赖摘要：
- `Blocked subtasks`
- `Ready subtasks`
- `Blocking subtasks`

这段内容不是独立输入，而是由 subtask 的完成状态和依赖列表推导出来的。

## 5. Subtask 设计准则

### 5.1 粒度要求

一个好的 subtask 应满足：
- 单一动作：只做一件可描述、可验收的事。
- 单一责任：不要把“实现 + 测试 + 汇总”混成一步。
- 可验证：完成后能用产物、命令结果或结构化结论证明。
- 可流转：能够自然进入 `pending -> in-progress -> completed`。

推荐粒度是 5 到 30 分钟可完成。

粒度过大时，常见问题是：
- 状态长期卡在 `in-progress`，无法反映真实进展。
- 阻塞原因只能写在自然语言里，无法拆出新的可执行动作。
- 无法判断该不该交给 SubAgent。

粒度过小时，常见问题是：
- 拆分和维护成本过高。
- 产生大量机械状态更新，干扰主流程推进。

### 5.2 推荐写法

推荐使用“动词 + 对象 + 产出”：
- 收集 `doc/refer` 中 todo 与 SubAgent 约束并形成差异清单
- 新增 `todo-reference.md` 并写入 subtask 生命周期说明
- 更新索引文档并补充阅读顺序

不推荐写法：
- 处理一下 todo
- 做文档
- 完善逻辑

### 5.3 完成判据

每个 subtask 至少应绑定一种完成判据：
- 产物路径：例如某个文档、代码文件、配置文件。
- 命令结果：例如测试通过、lint 通过、构建成功。
- 结构化结论：例如调研结论、风险列表、差异说明。

如果完成后无法明确回答“什么算做完”，这个 subtask 往往拆得还不够好。

## 6. Subtask 状态机

## 6.1 协议层状态机

`InDepth.md` 中的目标状态机是：

```text
pending -> in-progress -> completed
          \-> blocked -> in-progress
pending/in-progress/blocked -> cancelled
```

协议层额外要求：
- 出现阻塞时，必须记录阻塞原因、影响范围、重试条件。
- 阻塞解除后，必须记录解除依据。
- 若结果与预期不一致，不能直接标记 `completed`。
- 交付前要检查关键 subtask 不得处于未收口状态。

## 6.2 当前代码实现状态机

当前 `todo_tool` 真正接受的状态只有三种：
- `pending`
- `in-progress`
- `completed`

这意味着：
- 工具层还不支持把 subtask 显式写成 `blocked` 或 `cancelled`。
- “blocked” 在当前实现里是派生视图，不是可持久化状态。
- 一个 subtask 是否“被阻塞”，由其状态仍是 `pending` 且依赖未满足来推断。

因此，当前实践上需要区分两层语义：
- 协议语义：允许把“阻塞”和“取消”作为一等状态来思考和汇报。
- 工具语义：真正写回文件时，只能落 `pending/in-progress/completed`。

## 6.3 当前可执行处理办法

在当前实现下，subtask 没完成时应按下面的方式处理：

1. 依赖未满足
保持目标 subtask 为 `pending`，并通过依赖关系让它出现在 `blocked_tasks` 中。

2. 正在处理中但未完成
保持为 `in-progress`，不要提前写成 `completed`。

3. 遇到外部阻塞但工具无法写 `blocked`
继续把 subtask 保持在 `in-progress` 或回退为 `pending`，同时必须在上下文、交付说明、或后续新增 subtask 中明确写出阻塞原因和下一步。

4. 决定不再执行
协议上应视为 `cancelled`，但当前工具无法持久化该状态，只能通过新增说明或最终交付备注显式标注。

换句话说，当前 todo 工具可以表达“未开始、进行中、已完成”，但对“阻塞/取消”的表达仍然依赖上层执行纪律和最终报告。

## 7. Subtask 的标准处理流程

一个 subtask 的推荐执行流是：

1. 创建时写清名称、描述、依赖、拆分理由。
2. 真正开始执行前，把状态从 `pending` 更新为 `in-progress`。
3. 执行中如果发现动作不属于现有 subtask，先补一个新 subtask，再继续。
4. 结束后只有在结果可核验时才能更新为 `completed`。
5. 如果无法完成，不要伪装成完成；应保留未完成状态，并把原因写进输出。

最小闭环示意：

```text
create_task
  -> update_task_status(todo_id, n, "in-progress")
  -> 执行动作
  -> 验证结果
  -> update_task_status(todo_id, n, "completed")
```

## 8. Subtask 与依赖

### 8.1 依赖的含义

依赖表示“当前 subtask 的开始条件”，不是“相关就算依赖”。

应该写依赖的场景：
- 后一步必须使用前一步产物。
- 后一步的验收依赖前一步完成。
- 前一步失败时，后一步没有执行意义。

不应该滥写依赖的场景：
- 只是主题相关，但可以独立推进。
- 只是共享背景，不影响执行顺序。

### 8.2 `get_next_task_item` 的作用

当前工具会根据已完成的依赖，返回下一个可执行的 `pending` subtask：
- 有可执行任务时：`status=ready`
- 全部完成时：`status=all_completed`
- 没有可执行项时：`status=blocked`

这里的 `blocked` 是全局编排视角，含义是“当前没有任何满足依赖条件的 pending 任务”，并不等于某个运行中的 subtask 显式进入了 `blocked` 状态。

## 9. Subtask 与 SubAgent 的关系

### 9.1 主原则

SubAgent 不应该直接替代 todo；SubAgent 是执行者，subtask 才是编排单元。

所以正确关系是：
- 先有 subtask 设计。
- 再决定哪些 subtask 交给 SubAgent。
- 主 Agent 负责状态同步、依赖管理和最终汇总。

### 9.2 何时适合把 subtask 交给 SubAgent

适合交给 SubAgent 的 subtask 往往满足：
- 边界清晰，输入输出可以写清楚。
- 能独立推进，不需要频繁来回同步上下文。
- 耗时较长，适合并行。
- 角色能力明确，例如 researcher、builder、reviewer、verifier。

不适合交给 SubAgent 的 subtask：
- 只需几分钟的小改动。
- 需要主 Agent 持续持有全局上下文。
- 与其他步骤强耦合，拆分后沟通成本大于收益。

### 9.3 Todo 中如何登记 SubAgent 动作

根据 `InDepth.md`，与 SubAgent 相关的动作应显式写成 subtask，而不是在暗处执行。

建议至少拆成：
- 创建/配置某个 SubAgent
- 启动该 SubAgent 执行
- 主 Agent 汇总其结果

典型模板：
- `#1` 定义 researcher 子代理的检索范围与验收口径
- `#2` 启动 researcher 产出证据摘要
- `#3` 定义 builder 子代理的修改范围
- `#4` 启动 builder 实现并提交产物
- `#5` 主 Agent 汇总结果并完成最终验收

这样做的价值是：
- 可以精确知道卡在“创建”、“执行”还是“汇总”。
- 并行流不会共享一个模糊状态位。
- 后续复盘能看清拆分是否合理。

## 10. Subtask 未完成时的推荐处理策略

这一节是 todo 场景里最容易出错的部分。

### 10.1 非关键路径未完成

如果某个 subtask 尚未完成，但主流程还有其他不依赖它的动作：
- 不要原地等待。
- 先推进其他 ready subtask。
- 让未完成 subtask 保持原状态，并在汇总时说明影响范围。

这对应“编排优先于阻塞等待”的原则。

### 10.2 关键路径被卡住

如果后续动作都依赖该 subtask：
- 先判断是依赖问题、信息缺口、执行失败，还是拆分粒度不合理。
- 若只是任务过大，优先把它再拆细，而不是长期挂在一个大 subtask 上。
- 若确实是外部信息缺失，当前工具层只能保留未完成状态，并通过备注或新增 subtask 记录“等待什么”。

### 10.3 SubAgent 子任务未完成

如果某个交给 SubAgent 的 subtask 没完成，推荐做法是：

1. 主流程先继续做不依赖该结果的工作。
2. 只有在关键路径真正被它卡住时，才把主流程收束到等待该结果。
3. 不要立刻自己重复做同一个 subtask；先判断是不是任务定义不清、范围太大、或上下文不够。
4. 优先把问题转化成新的 todo 动作，例如“补充上下文”“缩小子任务范围”“重试验证”。
5. 如果最终决定放弃该子流，在交付说明里明确未完成项和后续建议。

### 10.4 什么时候要新增 subtask

出现以下情况时，应新增 subtask，而不是把原 subtask 描述无限膨胀：
- 发现新的独立动作。
- 需要补一次验证或回归。
- 需要单独做汇总、对账、清理、重试。
- 原步骤内部已经出现两个不同责任。

判断标准很简单：
- 如果这个动作完成后可以独立验收，就值得成为新的 subtask。

## 11. 当前实现与协议差异

这是实际使用时必须知道的边界。

### 11.1 已实现能力

当前 `todo_tool` 已实现：
- 创建带 `split_reason` 与 `split_rationale` 的 markdown todo。
- 子任务依赖校验。
- `pending/in-progress/completed` 三态流转。
- 进度百分比自动更新。
- ready / blocked / blocking 派生摘要。
- `get_task_progress` 和 `generate_task_report` 报告输出。
- 观测事件中的 `todo-id:` 前缀归一化。

### 11.2 未完全对齐项

当前仍未完全对齐 `InDepth.md` 的点：
- `blocked` 和 `cancelled` 还不是工具层可写状态。
- `update_task_status` 的公开文档仍是三态，没有阻塞原因、影响范围、解除依据等字段。
- todo 文件的 `Acceptance Criteria` 目前只是固定占位文本，并未强制结构化落盘。
- “与 SubAgent 有关的配置/启动/回收必须单独登记”属于执行协议要求，不是工具层硬校验。

### 11.3 使用建议

在工具能力升级前，推荐实践是：
- 用依赖系统表达“等待前置结果”的阻塞。
- 用 `in-progress` 表达正在做但尚未收敛。
- 用新增 subtask 表达重试、补充信息、回归验证等补充动作。
- 用最终交付说明补齐“阻塞原因、未完成项、影响范围、建议下一步”。

## 12. 推荐阅读顺序

如果要完整理解 todo 与 subtask：

1. `InDepth.md`：执行协议与强约束。
2. `doc/refer/tools-reference.md`：todo 工具签名与调用方式。
3. `doc/refer/agent-collaboration-reference.md`：SubAgent 生命周期与角色路由。
4. `app/tool/todo_tool/todo_tool.py`：真实可用状态机与 markdown 结构。

## 13. 一句话结论

Todo 的核心不是“列任务”，而是把复杂执行过程压缩成一组可验证的 subtask；而当前关于 subtask 的关键实践，是在协议上清楚表达阻塞与协作，在工具上诚实维护 `pending/in-progress/completed` 三态，并用新增 subtask 和最终报告把未完成部分说清楚。
