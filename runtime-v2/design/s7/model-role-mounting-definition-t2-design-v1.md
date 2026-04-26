# S7-T2 模型调用挂载结构定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S7-T2`

## 1. 目标

本任务不再把 v2 的模型接入层定义成一组抽象“模型角色名”，而是改为定义：

1. 哪些模型调用挂在 prompt build
2. 哪些模型调用挂在主链路
3. 哪些能力在主链路结束后消费 `handoff`
4. 哪些能力根本不应再视为模型角色，而只是保存工具

## 2. 正式结论

本任务最终结论如下：

1. v2 按“挂载位置”而不是“抽象角色名”来定义模型调用结构
2. `memory recall` 和 `preference recall` 挂在 prompt build
3. `prepare`、`execute`、`finalize`、`compression` 挂在主链路
4. `verification` 挂在 post-chain，并直接消费 `handoff`
5. `preference extract` 不再视为模型角色，而视为消费 `handoff` 的保存工具
6. `system memory finalize/write` 同样不再视为模型角色，而视为消费 `handoff` 的保存工具
7. `clarification judge` 第一版先移除，不进入 v2 主设计

## 3. 第一版调用挂载结构

v2 第一版统一采用以下结构：

```text
prompt-build
  -> memory recall
  -> preference recall

main-chain
  -> prepare
  -> execute
  -> finalize
  -> compression

post-chain
  -> verification

save-tools
  -> preference extract/save
  -> system memory finalize/write

subagent-chain
  -> subagent execution
```

## 4. Prompt-Build Model Calls

这一层的特点是：

1. 发生在主链路开始前
2. 主要输入是 `user_input`
3. 主要输出是 prompt / context augmentation
4. 不依赖复杂的运行中 task graph 状态

第一版包括：

1. `memory recall`
2. `preference recall`

结论：

1. 这两类能力属于 prompt 构建
2. 不属于主链路推进动作

## 5. Main-Chain Model Calls

这一层是直接绑定主链路上下文的模型调用。

第一版包括：

1. `prepare`
2. `execute`
3. `finalize`
4. `compression`

这里的关键结论是：

1. `compression` 留在主链路内
2. 原因不是它推进业务任务，而是它直接保障主链路上下文持续可运行

因此，`compression` 在 v2 中是主链路内的运行保障步骤。

## 6. Post-Chain Model Calls

第一版 post-chain 只保留：

1. `verification`

它的特点是：

1. 发生在主链路收敛之后
2. 直接消费 `RunOutcome`
3. 特别直接消费 `RunOutcome.handoff`

结论：

1. `verification` 是正式的 post-chain 模型调用
2. 它不属于主链路本体

## 7. Save Tools

本任务特别明确一个重要调整：

以下能力不再作为模型角色来建模，而作为保存工具处理：

1. `preference extract`
2. `system memory finalize/write`

原因如下：

1. 它们都应消费 `handoff`
2. 它们不应再自己生成与主链路平行的另一套结果
3. 它们的职责是保存，而不是重新定义主链路输出

也就是说：

1. `handoff` 生成偏好或记忆种子
2. 保存工具拿到这些结果后执行持久化

这里的核心原则是：

`生成在主链路，保存在工具层。`

## 8. SubAgent Chain

`subagent execution` 仍保留为独立协作链路。

它的特点是：

1. 由主链路决定是否创建
2. 但具体执行不并入主链路模型调用结构
3. 后续单独在 `S10` 中继续展开

## 9. 第一版排除项

第一版明确排除：

1. `clarification judge`

处理原则：

1. 不纳入 v2 第一版主设计
2. 后续若确有必要，再单独补回

## 10. 与其他任务的对接

`S7-T2` 直接对接：

1. `S1-T2`
   prompt-build 调用需要进入 prompt 分层
2. `S3-T2`
   main-chain 挂到 `RuntimeOrchestrator`
3. `S4-T2`
   main-chain 调用依赖 `RunContext`
4. `S11-T2`
   post-chain verification 直接消费 `RunOutcome.handoff`
5. `S12-T2`
   事件模型需要区分 main-chain / post-chain / save-tools

## 11. 本任务结论摘要

可以压缩成 5 句话：

1. v2 按挂载位置而不是抽象角色名来组织模型调用
2. `memory recall` 和 `preference recall` 属于 prompt build
3. `prepare`、`execute`、`finalize`、`compression` 属于主链路
4. `verification` 是唯一正式 post-chain 模型调用
5. `preference extract` 和 `system memory finalize/write` 都视为消费 `handoff` 的保存工具
