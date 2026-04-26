# S5-T6 Task Graph 跨动作挂载规则（V1）

更新时间：2026-04-23  
状态：Draft  
对应任务：`S5-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 task graph 与跨动作能力之间的挂载关系。

本任务不再讨论：

1. node 的结构定义
2. node 状态推进规则
3. tool 协议细节
4. closeout 内部流程

这里只回答一件事：

哪些能力需要正式挂进 task graph，哪些不需要。

## 2. 正式结论

第一版正式结论如下：

1. `subagent` 是唯一需要正式挂入 task graph 的跨动作能力
2. 普通 `tool execution` 不进入 graph 结构
3. `search` 属于 tool
4. `memory recall` 不属于 tool，也不属于 graph 挂载
5. `memory fetch` 属于 tool
6. `finalize / verification` 不进入 task graph

## 3. `subagent` 的挂载方式

第一版中，`subagent` 必须绑定到 node。

这是硬规则，不允许 `subagent` 作为 graph 外的漂浮能力存在。

原因是：

1. `subagent` 会改变执行骨架
2. `subagent` 会影响 `owner`
3. `subagent` 有完整生命周期
4. `subagent` 的结果、失败、回收都必须能落回 graph

## 4. `subagent` 的两层表达

第一版采用两层表达方式。

### 4.1 生命周期动作层

以下动作走显式 node：

1. 创建
2. 配置
3. 启动
4. 结果回收
5. 关闭
6. 销毁

也就是说：

1. `subagent` 生命周期本身就是正式工作
2. 这些动作必须能在 graph 上被追踪

### 4.2 工作执行层

真正由 `subagent` 执行的工作 node，不再额外建特殊 graph 结构，而是通过 `owner` 表达归属。

也就是说：

1. node 仍然是 node
2. 只是它的执行者不是 main-chain，而是某个 `subagent`

## 5. 普通 Tool Execution 的归位

第一版普通 tool 调用不进入正式 graph 结构。

tool 的定位是：

1. 当前 node 执行过程中的能力使用
2. 不是 graph 的正式组成部分

因此：

1. tool result 默认先回流当前 node
2. 由 `step` 决定是否把它转成正式 `NodePatch / GraphPatch`

## 6. `search` 的归位

第一版明确规定：

1. `search` 是 tool
2. `search` 不是 graph 对象
3. `search` 不单独挂 task graph

如果某个 node 需要检索：

1. 该 node 本身仍是普通 node
2. node 执行过程中可调用 search tool
3. search 结果进入当前 node 的 `evidence / notes / artifacts`

## 7. `memory recall` 的归位

第一版明确规定：

1. `memory recall` 不是 tool
2. `memory recall` 不属于 graph 挂载

它的定位是：

1. run 开始时的 prompt injection / runtime preload 机制
2. 属于正式执行前的上下文装配动作

因此：

1. recall 不由 step 临时发起
2. recall 不作为 node 执行动作表达
3. recall 不进入 task graph 结构

## 8. `memory fetch` 的归位

第一版明确规定：

1. `memory fetch` 是 tool

它的定位是：

1. 执行过程中，step 主动请求读取某条记忆正文或细节

因此：

1. `memory fetch` 属于 node 执行过程中的能力调用
2. `memory fetch` 结果回流当前 node
3. `memory fetch` 不单独进入 graph 结构

## 9. `finalize / verification` 的归位

第一版明确规定：

1. `finalize / verification` 不进入 task graph

原因如下：

1. 它们属于 run closeout 链路
2. 它们不应污染主执行骨架
3. 它们不是普通执行节点语义

因此：

1. task graph 负责任务执行骨架
2. finalize / verification 负责结果收口

## 10. 第一版最小总规则

可以把本任务压缩成下面 5 条：

1. 只有 `subagent` 正式进入 graph 挂载
2. subagent 生命周期动作走显式 node
3. 普通 tools 不进 graph，只回流当前 node
4. `memory recall` 是启动注入，不是 tool
5. `finalize / verification` 属于 closeout，不属于 graph

## 11. 对后续任务的直接输入

`S5-T6` 直接服务：

1. `S6` tool domain 设计
2. `S8` memory hook / fetch 归位
3. `S10` subagent runtime 绑定设计
4. `S11` finalize / verification 与 graph 的边界划分

## 12. 本任务结论摘要

可以压缩成 6 句话：

1. `subagent` 必须绑定到 node
2. subagent 生命周期动作本身走显式 node
3. `search` 是 tool，不是 graph 对象
4. `memory recall` 是启动注入，不是 tool
5. `memory fetch` 是 tool，执行时按需调用
6. `finalize / verification` 不进入 task graph
