# Prepare / Planner 实现说明

## 文档定位

本文记录 `runtime-v2` 当前 `PreparePhase / Planner` 的实际落地情况、代码入口、正式责任链与当前边界。

它对应的是模块 18 的当前实现结果，而不是 `design/` 下的设计决策原文。

## 当前代码入口

当前 `prepare` 落地主要位于：

1. [runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
2. [assembler.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/prompting/assembler.py)
3. [models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/prompting/models.py)
4. [models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/state/models.py)

对应测试主要位于：

1. [test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)
2. [test_prompting.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_prompting.py)

## 当前责任链

当前第一版 `prepare` 主链如下：

1. `RuntimeOrchestrator.run_prepare_phase(...)`
2. 追加本 run 的 `run-start` memory entry
3. 构造 prepare 视角的 prompt 输入
4. `ExecutionPromptAssembler.build_prepare_prompt(...)`
5. 渲染三段 prompt block
6. 发起一次 planner model 调用
7. 解析 planner JSON payload
8. 将 planner payload 规范化为 `PrepareResult`
9. 将 `PrepareResult.patch` 应用回正式 graph
10. 回写 `goal / prepare_result / active_node_id`
11. 追加轻量 prepare memory entry
12. phase 从 `PREPARE` 推进到 `EXECUTE`

## 当前正式数据结构

### `PrepareResult`

当前第一版正式结构位于 [state/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/state/models.py)：

1. `goal`
2. `patch`

其中：

1. `goal` 是 prepare 收敛出的当前 run 正式目标
2. `patch` 是 prepare 产出的正式 graph 结果

`PrepareResult` 会挂到：

1. `runtime_state.prepare_result`

并且：

1. `goal` 会回写到 `run_identity.goal`

### planner payload

当前第一版 planner 不直接产出正式 `TaskGraphNode`，而是先产出草案 payload。

最小 payload 结构是：

1. `goal`
2. `active_node_ref`
3. `nodes`

其中每个草案 node 最小字段包括：

1. `ref`
2. `name`
3. `kind`
4. `description`
5. `node_status`
6. `owner`
7. `dependencies`
8. `order`

## 当前 prompt 结构

当前 `prepare` 继续复用统一三层 prompt 架构：

1. `base prompt`
2. `phase prompt`
3. `dynamic injection`

但输入视角不再是 execute 的 `active node` 视角，而是 `task / graph planning` 视角。

当前 prepare 动态注入主要包括：

1. `user_input`
2. 旧 `goal`
3. graph 摘要
4. task 级 `runtime memory`
5. capability 文本
6. `finalize_return_input` 预留输入

## 当前 orchestrator 负责的规范化工作

当前第一版明确由 orchestrator 负责：

1. 校验 planner payload 是否为合法 JSON object
2. 校验 `goal / active_node_ref / nodes` 是否齐全
3. 校验每个 node 草案的最小字段是否合法
4. 为每个草案节点生成正式 `node_id`
5. 统一补当前 `graph_id`
6. 将草案 `dependencies` 从 `ref` 映射成正式 `node_id`
7. 将 `active_node_ref` 映射成正式 `patch.active_node_id`
8. 将规范化结果组装成正式 `PrepareResult.patch`

这意味着：

1. LLM 只负责 planning 草案
2. 系统负责正式化与落图

## 当前第一版校验规则

当前第一版已实现的硬校验包括：

1. `goal` 不能为空
2. `nodes` 不能为空
3. `active_node_ref` 必须存在于 `nodes`
4. node `ref` 不能为空且不能重复
5. `name / kind / description` 不能为空
6. `node_status` 只允许 `pending / ready`
7. `order` 必须为正整数
8. `dependencies` 必须引用已存在的草案 `ref`
9. `active_node_ref` 指向的节点必须是 `ready`

## 当前第一版范围

当前第一版只支持：

1. 空图初始化 planning

当前明确不支持：

1. 非空图增量 planning
2. prepare 内多轮循环
3. prepare tool call loop
4. replan 回流实现

因此当 graph 非空时，`run_prepare_phase(...)` 当前会直接报错，而不是静默合并。

## 当前 memory 写入

当前 `prepare` 会写两类短期上下文：

1. `run-start`
   - 角色：`user`
   - 内容：本次 run 的原始 `user_input`
2. `prepare`
   - 角色：`system`
   - 内容只保留轻量正式结论：
     - `goal`
     - `graph_change_summary`

当前不写：

1. planner thought
2. 候选方案
3. 被否决路径

## 当前工程 fallback

当前实现保留了一个很轻的工程 fallback：

1. 当 planner model 调用本身失败时
2. orchestrator 会直接构造一个单节点最小 `TaskGraphPatch`
3. 同时将 `goal` 收敛为当前 `goal` 旧值或 `user_input`

这只是工程可运行性保护，不是正式主语义。

当前正式语义仍然是：

1. planner payload 非法时直接失败
2. 不因为非法 payload 自动伪造规划结果

## 当前测试覆盖

当前已覆盖：

1. prepare prompt 的正式文本与动态注入
2. planner 正常返回时：
   - goal 回写
   - graph 初始化
   - dependency 映射
   - active node 同步
   - prepare memory entry 写入
3. planner payload 非法时直接报错
4. 非空图 prepare 当前直接报错
5. host / orchestrator / skills 相关回归不被破坏
