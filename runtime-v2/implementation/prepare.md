# Prepare / Planner 实现说明

## 文档定位

本文记录 `runtime-v2` 当前 `PreparePhase / Planner` 的实际落地情况、代码入口、正式责任链与当前边界。

它对应的是模块 18 与模块 23 的当前实现结果，而不是 `design/` 下的设计决策原文。

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
10. 按成功/失败规则收口 `prepare_result / prepare_failure / request_replan`
11. 回写 `goal / prepare_result / active_node_id`
12. 追加轻量 prepare memory entry
13. phase 从 `PREPARE` 推进到 `EXECUTE`

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

### `PrepareFailure`

当前已新增轻量结构化 prepare 失败承载对象：

1. `failure_type`
2. `message`
3. `created_at`

它会挂到：

1. `runtime_state.prepare_failure`

当前第一版错误类型固定为：

1. `planner_model_error`
2. `planner_payload_parse_error`
3. `planner_contract_error`
4. `planner_graph_semantic_error`
5. `planner_noop_patch`

### planner payload

当前第一版 planner 不直接产出正式 `TaskGraphNode`，而是先产出草案 payload。

当前第一版 planner payload 在初始 planning 下最小结构是：

1. `goal`
2. `active_node_ref`
3. `nodes`

其中每个 create 草案 node 最小字段包括：

1. `ref`
2. `name`
3. `kind`
4. `description`
5. `node_status`
6. `owner`
7. `dependencies`
8. `order`

当前在 replan 场景下，planner payload 允许两类草案：

1. `create`
   - 继续使用临时 `ref`
2. `update`
   - 必须显式引用正式 `node_id`

当前 `update` 第一版只允许修改：

1. `name`
2. `description`
3. `owner`
4. `dependencies`
5. `node_status`

其中 `node_status` 进一步收紧为只允许：

1. `pending`
2. `ready`

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
6. `finalize_return_input`
7. `request_replan`

## 当前 orchestrator 负责的规范化工作

当前第一版明确由 orchestrator 负责：

1. 校验 planner payload 是否为合法 JSON object
2. 校验 `goal / active_node_ref / nodes` 是否齐全
3. 按 `create / update` 两类语义分别校验 node 草案
4. 为 create 草案节点生成正式 `node_id`
5. 校验 replan update 是否命中现有 node，且是否触碰终态 node
6. 统一补当前 `graph_id`
7. 将草案 `dependencies` 从 `ref / node_id` 映射成正式依赖 id
8. 将 `active_node_ref` 映射成正式 `patch.active_node_id`
9. 检查 patch 是否构成 no-op
10. 将规范化结果组装成正式 `PrepareResult.patch`

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

当前模块 23 后补的 replan 规则包括：

1. replan 场景支持非空 graph
2. 只允许 `create / update`
3. 不允许 `delete / replace_node / replace_graph`
4. `update` 只能命中非终态 node
5. `update.node_status` 只允许 `pending / ready`
6. 新 node 可以依赖旧 node，也可以依赖本次新增 node
7. 非终态旧 node 可以把 `dependencies` 更新为指向本次新增 node
8. patch 合法但没有任何实质修改时，按 `planner_noop_patch` 失败收口

## 当前第一版范围

当前第一版已经支持：

1. 空图初始化 planning
2. 非空图上的 replan 增量 planning

当前明确不支持：

1. 删除旧 node
2. 整图替换式 planning
3. prepare 内多轮循环
4. prepare tool call loop
5. 更复杂的 graph 重构策略

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

1. 只有在初始 planning 场景，且 planner model 调用本身失败时
2. orchestrator 才会直接构造一个单节点最小 `TaskGraphPatch`
3. 同时将 `goal` 收敛为当前 `goal` 旧值或 `user_input`

这只是工程可运行性保护，不是正式主语义。

当前正式语义仍然是：

1. replan 场景第一版完全禁止 fallback
2. planner payload 非法时直接失败
3. patch 语义非法时直接失败
4. no-op patch 直接失败
5. 不因为非法 payload 自动伪造规划结果

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
4. 初始 planning 模型失败时的 fallback
5. replan 场景下的 create/update 增量 planning
6. 终态 node update 拒绝
7. replan 模型失败时禁止 fallback
8. replan no-op patch 拒绝
9. host / orchestrator / skills 相关回归不被破坏
