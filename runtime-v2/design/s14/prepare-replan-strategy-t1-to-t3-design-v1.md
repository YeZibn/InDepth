# S14 PreparePhase / Replan 正式策略补强（T1-T4）

更新时间：2026-05-01  
状态：Draft

## 1. 目标

本设计稿用于收口模块 23 当前已经讨论完成的 `T1 ~ T4`：

1. `PreparePhase` 第一版在初始 planning 与 `replan` 场景下的正式范围与边界
2. `PreparePhase` 在两种场景下的统一输入输出 contract
3. 非空 graph 上 `prepare_result.patch` 的第一版正式修改语义
4. `request_replan` 被消费后的状态变化、旧 `prepare_result` 覆盖规则与 graph 收口规则

## 2. 正式结论摘要

当前正式结论如下：

1. `PreparePhase` 第一版正式支持非空 graph 上的 `replan`
2. 第一版 `replan` 不做整图重写，而采用增量 planning
3. 第一版增量 planning 只允许：
   - 新增 node
   - 修改现有 node 的 planning 属性
4. 第一版明确禁止删除旧 node
5. `PreparePhase` 采用一套统一正式输入源，同时覆盖初始 planning 和 replan
6. `PrepareResult` 第一版继续保持极简正式结构：
   - `goal`
   - `patch`
7. `replan` 场景下，planner 允许同时表达：
   - 新增 node 草稿
   - 现有 node 更新草稿
8. 已进入终态的旧 node 第一版不允许被修改

## 3. 模块 23 任务 01：第一版范围与边界

### 3.1 非空 graph 的正式支持范围

当前正式确认：

1. `PreparePhase` 第一版正式支持非空 graph 上的 `replan`
2. 不再保留“非空图直接报错”的旧口径
3. `replan` 当前仍然通过统一 `PreparePhase` 执行，而不是另外新建独立 planner 组件

### 3.2 第一版 `replan` 的正式策略

当前正式确认：

1. 第一版 `replan` 采用增量 planning
2. 第一版不做整图重写
3. 第一版不做 graph 替换式 planning
4. 第一版不引入删除旧 node 的能力

### 3.3 允许的修改范围

当前正式确认：

1. 第一版只允许两类 planning 结果：
   - 新增 node
   - 修改现有 node 的 planning 属性
2. 这里的“planning 属性”不包括执行产物类字段
3. 已进入终态的 node 第一版不允许直接修改
4. 若后续计划需要绕过终态 node，则只能新增新 node 承接

### 3.4 fallback 与非法 payload 边界

当前正式确认：

1. planner payload 非法时，继续按正式失败收口
2. 不因为非法 payload 自动伪造 planning 结果
3. 只有“planner 模型调用失败”时，才保留单节点 fallback 作为工程兜底

## 4. 模块 23 任务 02：统一输入输出 contract

### 4.1 统一正式输入源

当前正式确认，`PreparePhase` 在初始 planning 和 replan 下都读取同一组正式输入源：

1. `user_input`
2. `current_goal`
3. `task_graph_state`
4. `runtime_memory`
5. `tool / skill capability summary`
6. `finalize_return_input`
7. `request_replan`

### 4.2 初始 planning 与 replan 的差异表达

当前正式确认：

1. 初始 planning 与 replan 不拆成两套独立 contract
2. 两者差异通过输入状态差异表达，而不是通过结果模型差异表达
3. 初始 planning 时：
   - `task_graph_state` 为空图
   - `request_replan` 为空
   - `finalize_return_input` 通常为空
4. replan 时：
   - `task_graph_state` 为非空图
   - `request_replan` 存在
   - `finalize_return_input` 允许存在

### 4.3 `request_replan` 与 `finalize_return_input` 的位置

当前正式确认：

1. `request_replan` 只作为 `PreparePhase` 的正式输入和 prompt 注入来源存在
2. `request_replan` 不进入 planner 输出 contract
3. `finalize_return_input` 继续保留为 `PreparePhase` 的正式输入之一
4. 它主要服务于 `verification fail -> replan` 场景

### 4.4 `PrepareResult` 的第一版结构

当前正式确认：

1. `PrepareResult` 第一版继续保持极简正式结构：
   - `goal`
   - `patch`
2. `active node` 继续通过 `patch.active_node_id` 承载
3. 第一版不新增：
   - `summary`
   - `mode`
   - `reason`

## 5. 模块 23 任务 03：非空 graph 上 patch 的正式修改语义

### 5.1 两类 node 草稿

当前正式确认，`replan` 场景下 planner 可以同时产出两类 node 草稿：

1. 新增 node 草稿
2. 现有 node 更新草稿

### 5.2 两类草稿的引用方式

当前正式确认：

1. 新增 node 继续使用临时 `ref`
2. 更新现有 node 必须显式引用正式 `node_id`

这意味着：

1. 初始 planning 仍然处于纯 `ref` 世界
2. replan 进入非空 graph 后，planner 若要修改旧 node，必须直接指向正式 `node_id`

### 5.3 patch 的第一版动作集合

当前正式确认，`prepare_result.patch` 第一版正式修改动作只保留：

1. `create`
2. `update`

当前明确不支持：

1. `delete`
2. `replace_node`
3. `replace_graph`

### 5.4 `update` 允许修改的字段

当前正式确认，`update` 第一版只允许修改以下 planning 字段：

1. `name`
2. `description`
3. `owner`
4. `dependencies`
5. `node_status`

其中：

1. `node_status` 进一步收紧为只允许：
   - `pending`
   - `ready`
2. 不允许 planner 直接把 node 改成：
   - `running`
   - `completed`
   - `failed`
   - `blocked`

### 5.5 依赖规则

当前正式确认：

1. 新 node 可以依赖旧 node
2. 新 node 可以依赖本次 replan 新增的其他新 node
3. 非终态旧 node 可以更新 `dependencies`，并允许指向本次新增 node

### 5.6 终态 node 的限制

当前正式确认：

1. 已进入终态的旧 node 第一版不允许被修改
2. 这里的“不允许修改”包括：
   - 不允许改 planning 字段
   - 不允许改依赖
   - 不允许改状态
3. 该规则在 prepare payload 的 normalize / 校验阶段直接拦截
4. 不延后到 patch apply 阶段再拒绝

## 6. 模块 23 任务 04：`request_replan` 消费后的状态变化与覆盖规则

### 6.1 `prepare_result` 与 `goal` 的覆盖规则

当前正式确认：

1. replan 成功后，新 `prepare_result` 直接整体覆盖旧的 `runtime_state.prepare_result`
2. `prepare_result` 表达的是“当前最新正式 planning 结果”，而不是 planning 历史仓库
3. replan 成功后，`run_identity.goal` 也由新的 `prepare_result.goal` 正式覆盖旧 goal

### 6.2 `request_replan` 的保留与清空时机

当前正式确认：

1. `request_replan` 不在进入 `PreparePhase` 前提前清空
2. `request_replan` 只在 prepare 成功完成后清空
3. 若 prepare 中途失败，则保留 `request_replan`

这样做的原因是：

1. 失败时不能丢失这次 replan 的触发原因
2. 保留正式控制信息，便于后续诊断与重试

### 6.3 graph 与 active node 的同步规则

当前正式确认：

1. replan 成功前，旧 graph 不做预清理
2. 只有新的 patch 完成 normalize、校验并成功 apply 后，graph 才正式进入新状态
3. replan 成功后：
   - `runtime_state.active_node_id` 以新 patch 的 `active_node_id` 为准重新同步
   - graph `active_node_id` 也以新 patch 的 `active_node_id` 为准重新同步
4. replan 成功后不保留旧 `active_node_id`

### 6.4 replan 成功与失败的第一版收口

当前正式确认，以下情况都视为这次 replan 未成功消费：

1. planner 模型调用失败
2. planner payload 非法
3. patch 校验失败
4. patch 合法但没有任何实质修改

其中第 4 点当前也按失败收口，原因是：

1. `request_replan` 表达的是当前计划已经不够用
2. 若 replan 最终没有带来任何正式 planning 变化，则不应视为成功重规划

因此第一版收口规则如下：

1. replan 成功时：
   - 新 `prepare_result` 覆盖旧 `prepare_result`
   - 新 `goal` 覆盖旧 `goal`
   - 新 patch 正式 apply 到 graph
   - `request_replan` 清空
   - `active_node_id` 按新 patch 重同步
2. replan 失败时：
   - 旧 `prepare_result` 保留
   - 旧 graph 保留
   - `request_replan` 保留
   - 不伪装成“成功消费过 replan”

## 7. 模块 23 任务 05：prepare payload 校验、错误分类与 fallback 边界

### 7.1 第一版错误分类

当前正式确认，`PreparePhase` 第一版错误按以下 5 类收口：

1. `planner_model_error`
2. `planner_payload_parse_error`
3. `planner_contract_error`
4. `planner_graph_semantic_error`
5. `planner_noop_patch`

### 7.2 fallback 的第一版边界

当前正式确认：

1. 只有 `planner_model_error` 在初始 planning 场景允许单节点 fallback
2. `replan` 场景第一版完全禁止 fallback

### 7.3 硬失败范围

当前正式确认，以下情况全部按硬失败收口，不做 fallback：

1. payload 解析失败
2. contract 校验失败
3. graph 语义校验失败
4. no-op patch

其中：

1. `planner_noop_patch` 在初始 planning 和 replan 下都按失败处理
2. 这里的失败不伪装成“已成功 planning 但内容为空”

### 7.4 结构化错误保留

当前正式确认：

1. prepare 失败第一版应保留轻量结构化错误类型
2. 不只抛裸异常
3. 其主要用途包括：
   - runtime memory
   - 诊断
   - 未来 reflexion / observability

## 8. 当前仍未展开的内容

当前第一版仍未展开：

1. 删除 node、整图替换和更复杂的 graph 重构策略
2. prepare 失败结构化错误对象的最终代码模型
