# S4-T3 统一状态图定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S4-T3`

## 1. 目标

本任务用于定义 `runtime-v2` 的统一状态图。

目标是：

1. 明确 run 级状态、phase 级状态、结果状态之间的关系
2. 避免继续把“生命周期状态”和“结果状态”混写成一套
3. 为后续 orchestrator、task graph、verification 提供统一状态语义

## 2. 正式结论

`runtime-v2` 第一版统一采用 3 条主状态线：

1. `lifecycle_state`
2. `phase_state`
3. `result_status`

这 3 条状态线分开建模，不合并。

## 3. 三条状态线

## 3.1 lifecycle_state

`lifecycle_state` 表示一次 run 的生命周期推进状态。

第一版建议状态集合：

1. `preparing`
2. `executing`
3. `finalizing`
4. `paused`
5. `completed`
6. `failed`

它回答的问题是：

`这次 run 当前走到了生命周期的哪个阶段？`

## 3.2 phase_state

`phase_state` 表示当前 phase 本身的运行状态。

第一版建议状态集合：

1. `idle`
2. `running`
3. `completed`
4. `failed`
5. `paused`

它回答的问题是：

`当前 phase 自己处在什么执行状态？`

## 3.3 result_status

`result_status` 表示这次 run 最终结果如何判定。

第一版建议状态集合：

1. `pass`
2. `partial`
3. `fail`

它回答的问题是：

`这次 run 的最终结果怎么判断？`

## 4. 关键语义区分

本任务最重要的结论是：

1. `completed` 不等于 `pass`
2. `failed` 不完全等于 `fail`

原因如下：

### `lifecycle_state=completed`

表示：

1. 这次 run 已经走完主链路与收尾流程
2. run 已经正常结束

但它不代表：

1. 任务一定通过验证
2. 结果一定是 `pass`

因此：

1. `lifecycle_state=completed`
2. `result_status` 仍可能是：
   - `pass`
   - `partial`
   - `fail`

### `lifecycle_state=failed`

表示：

1. 运行过程本身出现失败
2. 主链路未正常收敛

这种情况下通常会对应 `result_status=fail`，但两者语义仍不应混成一个字段。

## 5. paused 的位置

本任务明确规定：

1. `paused` 同时允许出现在 `lifecycle_state`
2. `paused` 也允许出现在 `phase_state`

原因是：

1. pause 既是 run 级事实
2. 也是当前 phase 的执行事实

例如：

1. `lifecycle_state=paused`
2. `phase_state=paused`

表示：

1. 整个 run 暂停了
2. 并且暂停发生在当前 phase 内部

## 6. completed / failed 的位置

本任务明确规定：

1. `completed` / `failed` 可以同时出现在 `lifecycle_state`
2. `completed` / `failed` 也可以出现在 `phase_state`

但语义不同：

### lifecycle_state 中的 `completed/failed`

表示 run 级终止结果。

### phase_state 中的 `completed/failed`

表示当前 phase 的结束状态。

这意味着：

1. 一个 phase 可以 `completed`
2. 但 run 仍继续进入下一个生命周期阶段

## 7. result_status 的赋值时机

本任务明确规定：

1. `result_status` 只在 finalize 后才正式有值

在 finalize 前：

1. 可以为空
2. 或实现层使用 `unknown`

但在正式设计语义上，它不应在 prepare / execute 阶段被提前定死。

原因是：

1. `result_status` 是结果判断，不是运行中状态
2. 它依赖 handoff、verification、最终收敛结果

## 8. 状态关系示意

可以用下面这张关系图理解：

```text
lifecycle_state:
  preparing -> executing -> finalizing -> completed
                               \-> failed
  preparing/executing/finalizing -> paused

phase_state:
  idle -> running -> completed
                 \-> failed
                 \-> paused

result_status:
  pass | partial | fail
```

## 9. 第一版状态约束

为了避免状态继续混乱，第一版明确 5 条约束：

1. `lifecycle_state` 只描述 run 生命周期
2. `phase_state` 只描述当前 phase 运行态
3. `result_status` 只描述最终结果态
4. 不允许再用单一字段同时承担生命周期态和结果态
5. `completed != pass` 必须作为正式规则写入

## 10. 对其他任务的直接输入

`S4-T3` 直接服务：

1. `S3-T4` step loop 最小职责定义
2. `S5-T3` task graph 最小执行单元
3. `S11-T3` handoff 结构
4. `S11-T4` 完成语义定义
5. `S12-T2` 事件模型

同时它直接依赖：

1. `S3-T3` phase engine 接口
2. `S4-T2` 核心状态对象定义

## 11. 本任务结论摘要

可以压缩成 5 句话：

1. v2 用 `lifecycle_state`、`phase_state`、`result_status` 三条状态线
2. `paused` 同时允许出现在 lifecycle 和 phase 层
3. `completed/failed` 也允许同时出现在 lifecycle 和 phase 层，但语义不同
4. `result_status` 只在 finalize 后才正式有值
5. `completed` 不等于 `pass`
