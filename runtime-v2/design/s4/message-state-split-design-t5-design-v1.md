# S4-T5 消息与状态解耦规则（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S4-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 state、message、event、handoff、tool result 之间的正式边界。

本任务的核心目标只有一个：

避免继续让消息、事件、交接材料或工具原始结果承载主链路控制语义。

## 2. 正式结论

第一版正式结论如下：

1. `state`、`message`、`event`、`handoff` 必须分开建模
2. `message` 不承载正式主链路控制语义
3. `event` 不承载正式主链路控制语义
4. `handoff` 不承载 execute 主链路控制语义
5. 原始 `tool result` 默认不进入正式 state
6. 只有经 `step` 提炼后的结论，才允许进入正式 state

## 3. 四类对象的正式定位

### 3.1 `state`

`state` 是正式运行事实源。

第一版中，正式控制状态只允许进入：

1. `RunContext`
2. `TaskGraphState`

它回答的问题是：

1. 当前 run 处于什么状态
2. 当前 graph 处于什么状态
3. 当前 active node 是谁
4. 当前主链路下一步如何推进

### 3.2 `message`

`message` 是模型对话材料。

它的作用是：

1. 参与 prompt 输入
2. 构成历史对话材料
3. 提供语言层上下文

但它不是正式控制状态。

### 3.3 `event`

`event` 是运行过程记录。

它的作用是：

1. observability
2. replay
3. postmortem
4. 工程排障

但它不是正式控制状态。

### 3.4 `handoff`

`handoff` 是 closeout 交接材料。

它的作用是：

1. 给 finalize 使用
2. 给 verification 使用
3. 给 closeout / memory write 使用

它不是 execute 主链路状态。

## 4. 正式禁止越界规则

第一版明确规定以下 6 条规则。

### 4.1 `message` 不得承载正式控制语义

例如，不允许靠 message 正式判断：

1. 当前 `active_node_id`
2. 当前 `graph_status`
3. 当前 `current_phase`
4. 是否进入 `finalize`

### 4.2 `event` 不得承载正式控制语义

event 只记录发生过什么，不决定当前执行事实。

### 4.3 `handoff` 不得承载 execute 主链路控制语义

`handoff` 只属于 closeout 链路。

第一版唯一正式例外是：

1. `finalize_return_input`

它是从 finalize fail 回灌 execute 的正式输入，不等于 handoff 重新进入主状态。

### 4.4 正式控制状态只能进入 state

第一版中，真正控制主链路推进的正式信息，只能进入：

1. `RunContext`
2. `TaskGraphState`

### 4.5 message / event / handoff 可以引用 state，但不能替代 state

例如它们可以携带：

1. `run_id`
2. `graph_id`
3. `node_id`

但它们引用了这些 id，并不意味着它们自动成为正式事实源。

### 4.6 需要长期影响后续 step 的事实，必须先入 state

如果某个结论会影响后续 step 判断，它必须先进入正式 state，而不能只停留在：

1. message 摘要
2. event payload
3. handoff 文本

## 5. Tool Result 的正式定位

第一版明确规定：

1. 原始 `tool result` 默认不是正式 state

它的正式定位是：

1. evidence source
2. artifact source
3. event payload source

而不是：

1. `RunContext` 正式字段
2. `TaskGraphState` 正式字段

## 6. 为什么原始 Tool Result 不直接入 State

原因如下：

1. 原始工具返回通常体积大、噪声多
2. 它尚未经过 step 判断
3. 它可能包含临时性或不稳定材料
4. 若直接入 state，会污染正式控制层

## 7. Tool Result 如何进入正式沉淀

第一版采用两段式规则。

### 7.1 原始结果阶段

原始 `tool result` 先作为执行材料存在。

它可以：

1. 进入 event payload
2. 形成 artifact ref
3. 被挂为 node evidence source

### 7.2 Step 提炼阶段

由 `step` 对原始 tool result 做正式提炼。

提炼后允许进入正式沉淀的只有：

1. 状态变化
2. `evidence`
3. `artifacts`
4. `notes`

也就是说：

1. tool result 是输入材料
2. patch / evidence / artifact 才是正式沉淀

## 8. 对后续设计的直接约束

本任务对后续设计施加以下约束：

1. `S3` step loop 不能从 message 中反推正式控制状态
2. `S5` task graph 不能把原始 tool result 当成 node 主状态
3. `S11` handoff 不得反向充当 execute 主链路事实源
4. `S12` event 系统只做记录，不做控制

## 9. 对后续任务的直接输入

`S4-T5` 直接服务：

1. `S4-T6` 状态库 skeleton
2. `S3-T5/T6` orchestrator / runtime skeleton
3. `S11` handoff / closeout 结构
4. `S12` 事件模型与 replay 结构

## 10. 本任务结论摘要

可以压缩成 6 句话：

1. `state`、`message`、`event`、`handoff` 必须分开
2. `message` 不负责控制
3. `event` 不负责控制
4. `handoff` 不负责 execute 主链路控制
5. 原始 `tool result` 默认不进 state
6. 只有经 `step` 提炼后的结论，才允许进入正式 state
