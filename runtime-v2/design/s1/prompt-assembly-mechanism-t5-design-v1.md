# S1-T5 Prompt Assembly 机制（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S1-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 prompt assembly 的正式机制。

本任务不再讨论：

1. prompt 有哪些资产
2. prompt 与状态边界的总规则
3. recall 的触发时机

这里只回答三件事：

1. prompt 在 runtime 中按哪些层组装
2. 各层分别放什么
3. assembler 最终输出什么

## 2. 正式结论

第一版 prompt assembly 采用固定六层结构：

1. `base layer`
2. `phase layer`
3. `task layer`
4. `capability layer`
5. `memory layer`
6. `context layer`

并明确规定：

1. `PromptAssembler` 内部可以保留分层结构
2. 最终交付给 agent / model call 的产物是文本

## 3. 六层结构

## 3.1 `base layer`

`base layer` 是稳定底座。

允许放：

1. 系统角色
2. runtime 总原则
3. 长期行为约束
4. 通用安全边界
5. 稳定写作/执行准则

不放：

1. 当前 phase
2. 当前 task
3. 当前 recall 结果
4. 当前 messages

## 3.2 `phase layer`

`phase layer` 是当前阶段专属规则层。

允许放：

1. `prepare / execute / finalize` 当前阶段规则
2. 当前阶段的输出格式要求
3. 当前阶段允许/禁止的动作
4. 当前阶段专属 contract

本任务明确规定：

1. output contract 不单独拉一层
2. phase 输出约束直接归入 `phase layer`

## 3.3 `task layer`

`task layer` 用于表达当前这次 run 正在推进什么。

允许放：

1. 当前 `user_input`
2. 当前 `goal`
3. task graph 摘要
4. active node 摘要
5. `finalize_return_input`
6. 当前必须面对的显式任务约束

不放：

1. 长期 preference
2. 历史 messages 轨迹
3. 原始 tool result 大块正文

## 3.4 `capability layer`

`capability layer` 用于表达当前这个 agent 已开启的能力面。

允许放：

1. 当前 agent 开启的 skills
2. 当前 agent 可用的 tools
3. 当前 agent 的能力边界说明

不放：

1. 当前 task 目标
2. 当前 messages 历史
3. recall 结果正文

## 3.5 `memory layer`

`memory layer` 用于放启动期召回进来的长期背景。

允许放：

1. system memory recall 摘要
2. user preference
3. 必要的长期经验/策略提醒

不放：

1. 执行期临时 fetch 的正文结果
2. 当前消息历史
3. 当前 step 的临时 tool result

## 3.6 `context layer`

`context layer` 用于放当前模型调用前已经积累出的上下文材料。

允许放：

1. messages
2. compression 之后的上下文内容
3. 必要的近期执行摘要
4. 执行期 fetch 到的记忆正文
5. 少量必要的近程材料整合结果

本任务明确规定：

1. `messages` 进入 prompt 定义
2. compression 内容属于 `context layer`

## 4. 层与层的关系

第一版采用固定顺序叠加：

1. `base`
2. `phase`
3. `task`
4. `capability`
5. `memory`
6. `context`

这表示：

1. 越往后越具体
2. 后层可以补充前层
3. 后层不能推翻前层正式规则

例如：

1. `context layer` 不能推翻 `phase layer`
2. `memory layer` 不能推翻 `task layer`
3. `capability layer` 不能推翻 `phase layer`
4. `task layer` 不能推翻 `base layer`

## 5. 必选层与可空层

第一版建议如下：

1. `base layer`：必选
2. `phase layer`：必选
3. `task layer`：必选
4. `capability layer`：必选
5. `memory layer`：可空
6. `context layer`：可空

补充说明：

1. `memory layer` 在没有 recall 结果时可以为空
2. `context layer` 在没有历史上下文时可以为空
3. execute / finalize 阶段通常会有 `context layer`

## 6. `PromptAssembler` 的定位

`PromptAssembler` 的职责不是自由拼 prompt，而是按固定六层顺序组装当前模型可见输入。

因此它负责：

1. 读取各层输入
2. 组装层级结构
3. 按固定顺序渲染为文本

它不负责：

1. 决定 recall 是否触发
2. 决定 graph 如何推进
3. 决定 tool 如何执行

## 7. 输出形态

第一版明确规定：

1. `PromptAssembler` 内部可使用分层结构对象
2. 对 agent / model call 的最终输出必须是文本

也就是说：

1. 内部先形成可检查的 layer sections
2. 最后再渲染成一份已排序 prompt 文本

## 8. 为什么这样设计

采用这套机制的原因如下：

1. 所有真正进入模型输入的内容都被纳入 prompt 定义
2. `messages` 与 compression 不再被割裂到 prompt 外
3. `skill / tool` 描述被正式收敛到独立 `capability layer`
4. output contract 不再悬空，而是跟 phase 绑定
5. 中间态仍然可检查、可调试
6. 对外接口仍然保持简单

## 9. 对后续任务的直接输入

`S1-T5` 直接服务：

1. `S1-T6` prompt 迁移方案
2. `S3-T6` runtime skeleton
3. `S8` recall / preference 注入挂点
4. `S11` finalize prompt 与 handoff 输出约束

## 10. 本任务结论摘要

可以压缩成 6 句话：

1. 第一版 prompt assembly 采用固定六层
2. 六层分别是 `base / phase / task / capability / memory / context`
3. `messages` 进入 prompt 定义
4. compression 内容属于 `context layer`
5. 当前 agent 开启的 `skills / tools` 进入 `capability layer`
6. assembler 内部分层，但最终输出文本
