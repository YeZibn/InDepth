# S10-T7 SubAgent Skeleton（V1）

更新时间：2026-04-25  
状态：Draft  
对应任务：`S10-T7`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 subagent 的最小可实施结构骨架。

本任务不再讨论：

1. subagent 的运行模型细节
2. subagent 与主任务图的绑定规则细节
3. subagent 角色模型细节
4. subagent 结果回流字段细节
5. subagent 失败、超时、取消策略细节

这里只回答四件事：

1. `subagent skeleton` 的交付物到底是什么
2. skeleton 应由哪些正式组成块构成
3. 各组成块的职责边界是什么
4. skeleton 如何映射当前已有实现与迁移方向

## 2. 正式结论

第一版正式结论如下：

1. `subagent skeleton` 的交付物是第一版最小可实施结构骨架
2. 该骨架定义对象边界、接口层次、依赖关系、状态挂点和事件挂点
3. 第一版 `T7` 不要求展开具体代码实现细节
4. skeleton 应直接对应当前已有模块现实
5. 后续实现应能映射到现有：
   - `sub_agent.py`
   - `sub_agent_runtime.py`
   - `sub_agent_tool`
   - role prompt 相关落点
6. 第一版正式骨架固定为 5 个组成块：
   - `role registry`
   - `subagent runtime facade`
   - `subagent lifecycle controller`
   - `result collector`
   - `graph binding adapter`
7. 第一版不再额外增加新的正式骨架块
8. 第一版不单列 `subagent store/manager` 作为正式骨架块
9. 旧式 manager/store 相关职责先收进 `lifecycle controller` 与 `runtime facade`
10. 主链真正依赖的是 `runtime facade` 和 `graph binding adapter`
11. 主链不应直接依赖底层实例实现
12. `lifecycle controller` 和 `result collector` 必须可独立测试
13. 旧 `tool facade` 第一版可以保留，但只作为兼容壳层
14. 正式语义应下沉到 `S10` 主结构
15. 迁移方向应是：
   - `tool -> facade -> controller/collector/adapter`
16. `tool` 不再是 subagent 的正式本体

## 3. `subagent skeleton` 的交付物定位

第一版中，`subagent skeleton` 的交付物不是一份具体实现代码清单，而是一份最小可实施结构骨架。

它的作用是：

1. 给后续实现提供稳定结构边界
2. 把 `T2 ~ T6` 已经确定的结论汇总成可落地结构
3. 避免在实现阶段重新发明第二套 subagent 结构

因此第一版 skeleton 主要回答的是：

1. 有哪些正式组成块
2. 各块各自负责什么
3. 各块之间如何依赖
4. 当前旧实现往哪里迁移

## 4. 为什么要直接映射当前已有模块

第一版明确规定：

1. skeleton 必须能够映射到当前已有现实模块

当前已有现实落点主要包括：

1. `sub_agent.py`
2. `sub_agent_runtime.py`
3. `sub_agent_tool`
4. role prompt 模板

这样做的原因是：

1. `T7` 的目标不是重新发明一套脱离现实的理想结构
2. 后续实现需要可迁移路径
3. 如果 skeleton 与当前代码现实脱节，设计文档的落地价值会很低

## 5. 第一版正式骨架

第一版正式骨架固定为以下 5 个组成块：

1. `role registry`
2. `subagent runtime facade`
3. `subagent lifecycle controller`
4. `result collector`
5. `graph binding adapter`

第一版不再增加第 6 个正式骨架块。

## 6. `role registry`

### 6.1 作用

`role registry` 负责：

1. 管理正式角色定义
2. 提供 role lookup
3. 承接 `T4` 中定义的 role definition
4. 提供 role prompt、allowed tools、allowed skills、behavior constraints 的挂载入口

### 6.2 不负责的事情

`role registry` 不负责：

1. 执行 subagent
2. 写回 graph
3. 推进生命周期

## 7. `subagent runtime facade`

### 7.1 作用

`subagent runtime facade` 负责：

1. 作为主 runtime 调用 subagent 能力的统一入口
2. 接收主链已经决定好的 role、node binding、任务输入
3. 屏蔽底层实例创建和运行细节
4. 对主链暴露稳定调用接口

### 7.2 不负责的事情

`subagent runtime facade` 不负责：

1. 决定 role
2. 决定 graph 如何变化
3. 直接生成正式 `GraphPatch`

## 8. `subagent lifecycle controller`

### 8.1 作用

`subagent lifecycle controller` 负责：

1. 表达 `create / configure / start / collect / destroy`
2. 管理生命周期状态推进
3. 处理正常回收路径
4. 处理异常回收路径
5. 对接 `T6` 的失败、超时、取消规则

### 8.2 不负责的事情

`subagent lifecycle controller` 不负责：

1. 角色定义管理
2. graph 级裁决
3. closeout 级结果判定

## 9. `result collector`

### 9.1 作用

`result collector` 负责：

1. 对接 `T5`
2. 把原始执行结果收成正式 `SubAgentResult`
3. 保证最小结果包结构稳定
4. 区分：
   - `work_summary`
   - `result_summary`
   - `artifacts`
   - `evidence`
   - `notes`
   - `handoff_hint`

### 9.2 不负责的事情

`result collector` 不负责：

1. 直接写 graph
2. 裁决 graph 后续动作
3. 决定 role
4. 推进生命周期

## 10. `graph binding adapter`

### 10.1 作用

`graph binding adapter` 负责：

1. 对接 `T3`
2. 把 subagent 生命周期动作和工作归属映射回主 graph 语义
3. 处理 `owner`、`subagent_ref`、`collect` 回主链这些桥接问题
4. 为主链 `step` 提供可消费的绑定视图

### 10.2 不负责的事情

`graph binding adapter` 不负责：

1. 自行推进 graph
2. 成为 graph writer
3. 替代主链 `step`

## 11. 为什么不单列 `subagent store/manager`

第一版明确规定：

1. 不单列 `subagent store/manager` 作为正式骨架块

原因如下：

1. 当前旧实现里的 manager 容易重新长成中心化控制器
2. 这会和 `RuntimeOrchestrator` 形成职责竞争
3. 第一版更需要把职责拆回正式边界中

因此相关职责先收进：

1. `subagent runtime facade`
2. `subagent lifecycle controller`

## 12. 主链依赖方向

第一版中，主链真正依赖的是：

1. `subagent runtime facade`
2. `graph binding adapter`

主链不应直接依赖：

1. 底层 subagent 实例实现
2. 原始 manager pool 结构
3. 具体 role prompt 文件装配细节

这样做的原因是：

1. 保持主链边界稳定
2. 避免把 subagent 内部实现细节泄露给 orchestrator
3. 让后续迁移可以在 facade 后面逐步替换

## 13. 可测试性要求

第一版明确要求：

1. `lifecycle controller` 必须可独立测试
2. `result collector` 必须可独立测试

原因如下：

1. 生命周期推进与异常回收是最容易回归的边界
2. 结果包结构一旦不稳定，会直接影响主链 `collect` 与后续 closeout

## 14. Tool Facade 的定位

第一版中，旧 `tool facade` 可以继续保留，但其定位被正式收缩为：

1. 兼容壳层

这意味着：

1. tool 入口仍可作为外部调用方式存在
2. 但 tool 不再是 subagent 的正式本体

正式语义应下沉到：

1. `runtime facade`
2. `lifecycle controller`
3. `result collector`
4. `graph binding adapter`

## 15. 迁移方向

第一版正式迁移方向如下：

```text
tool
  -> facade
    -> controller / collector / adapter
```

这条迁移方向的含义是：

1. 保留旧入口兼容能力
2. 把正式语义逐步从工具入口中剥离
3. 让 `S10` 自身成为正式结构承载层

## 16. 与其他任务的关系

`S10-T7` 直接依赖：

1. `S10-T2` subagent 运行模型
2. `S10-T3` subagent 与主任务图关系
3. `S10-T4` subagent 角色模型
4. `S10-T5` subagent 结果、证据、状态回流
5. `S10-T6` subagent 失败、超时、取消规则

`S10-T7` 直接服务：

1. 后续 subagent 代码实现
2. `S12` subagent 事件与测试骨架
3. 旧 `sub_agent` 相关模块的迁移重组

## 17. 本任务结论摘要

可以压缩成 6 句话：

1. `subagent skeleton` 的交付物是第一版最小可实施结构骨架
2. 第一版正式骨架固定为 `role registry / runtime facade / lifecycle controller / result collector / graph binding adapter`
3. 第一版不单列 `subagent store/manager`，相关职责先收进 facade 和 controller
4. 主链真正依赖的是 facade 和 adapter，而不是底层实例实现
5. `lifecycle controller` 和 `result collector` 必须可独立测试
6. 旧 tool 入口可以保留，但正式迁移方向应是 `tool -> facade -> controller/collector/adapter`
