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
4. RuntimeOrchestrator：
   [orchestrator.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/orchestrator.md)
5. Runtime Memory：
   [memory.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/memory.md)
6. Prompting：
   [prompting.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/prompting.md)
7. Skills：
   [skills.md](/Users/yezibin/Project/InDepth/runtime-v2/implementation/skills.md)

## 预留实现块

后续预计逐步补以下说明文档：

1. `tools.md`
2. `finalize.md`
3. `subagent.md`
