# runtime-v2 实现说明

## 文档定位

本目录用于记录 `runtime-v2` 各实现块的当前落地情况与思想架构说明。

和 `design/` 的区别是：

1. `design/` 记录的是设计决策
2. `implementation/` 记录的是已经开始落地的实现块、对应代码入口以及当前实现边界

## 当前实现块

1. 状态层：
   [state.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/state.md)
2. 宿主标识层：
   [host.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/host.md)
3. Task Graph：
   [task-graph.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/task-graph.md)

## 预留实现块

后续预计逐步补以下说明文档：

1. `orchestrator.md`
2. `tools.md`
3. `prompting.md`
4. `finalize.md`
5. `memory.md`
6. `subagent.md`
