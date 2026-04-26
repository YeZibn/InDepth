# S10-T6 SubAgent 失败、超时、取消规则（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S10-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 subagent 的失败、超时和取消规则。

本任务不再讨论：

1. subagent 的运行模型
2. subagent 与主任务图的绑定结构
3. subagent 角色模型
4. subagent 结果包字段细节

这里只回答五件事：

1. subagent 的异常终态有哪些
2. `partial` 与异常终态的边界是什么
3. 异常状态由谁裁决
4. 异常默认影响当前 node 还是直接影响 graph
5. 异常发生后是否仍然要求回收与销毁

## 2. 正式结论

第一版正式结论如下：

1. `subagent` 的异常终态固定为：
   - `failed`
   - `timed_out`
   - `cancelled`
2. `partial` 不属于异常终态
3. `partial` 表示已形成部分可用结果，主链仍可能继续消费
4. `failed` 表示当前授权目标未形成可用闭环，且失败是本次执行的主结论
5. `timed_out` 表示在授权时间或执行窗口内未完成，不等于逻辑失败
6. `cancelled` 表示由主链或宿主显式终止，不等于 subagent 自身失败
7. `subagent` 可以上报自己的执行结果状态
8. 正式裁决权始终属于主链 `step`
9. 异常默认先作用于当前 node
10. 异常不直接升级为 graph 级结论
11. 是否把异常升级成 `blocked / abandoned / follow-up required`，由主链 `step` 决定
12. 即使出现 `failed / timed_out / cancelled`，也应尽量进入 `collect -> destroy` 的显式回收路径
13. 只有在宿主层彻底失控、实例不可达或运行体已崩溃时，才允许无法完成完整回收
14. `failed / timed_out / cancelled` 都允许保留部分结果、证据和产物
15. 不能因为异常终态就默认丢弃已形成的 `artifacts / evidence / notes`
16. 第一版不允许 subagent 在异常时直接改 graph
17. 第一版不允许 subagent 在异常时绕过主链自行宣布后续动作

## 3. 异常终态集合

第一版中，subagent 的异常终态固定为 3 个：

1. `failed`
2. `timed_out`
3. `cancelled`

这样定义的作用是：

1. 让异常语义稳定
2. 让主链在 `collect` 后能围绕有限状态做正式判断
3. 为后续 `S10-T7` skeleton 和 `S12` observability 提供稳定状态集合

## 4. `partial` 与异常终态的边界

第一版明确规定：

1. `partial` 不属于异常终态
2. `partial` 表示虽然未完全完成，但已经形成部分可用结果

### 4.1 `partial`

表示：

1. 已形成部分可用结果
2. 主链仍可能继续消费这次执行产物

### 4.2 `failed`

表示：

1. 当前授权目标未形成可用闭环
2. 失败是本次执行的主结论

两者的关键区别不在于“是否有产物”，而在于：

1. 主链还能不能把这次执行当成有效输入继续消费

## 5. `timed_out` 与 `failed` 的边界

第一版明确规定：

1. `timed_out` 不等于逻辑失败
2. `timed_out` 表示在授权时间或执行窗口内未完成

因此：

1. `timed_out` 可以伴随部分结果
2. 主链仍可在 `collect` 后判断这些部分结果是否可用

## 6. `cancelled` 与 `failed` 的边界

第一版明确规定：

1. `cancelled` 不等于 subagent 自身失败
2. `cancelled` 表示由主链或宿主显式终止

因此：

1. `cancelled` 允许伴随部分结果
2. 主链仍可在 `collect` 后决定是否消费这些结果

## 7. 状态裁决权

第一版中，状态裁决权采用如下分工：

### subagent 负责

1. 上报自己的执行结果状态
2. 返回结果、证据、产物和说明

### 主链 `step` 负责

1. 做最终正式裁决
2. 决定当前 node 如何写回
3. 决定是否需要升级到 graph 级处理

这条边界是硬规则。

原因如下：

1. 避免 subagent 成为第二个主链裁决者
2. 保持正式状态写回入口唯一
3. 保持 `S10` 与 `S5` 的边界稳定

## 8. 默认影响范围

第一版明确规定：

1. 异常默认先作用于当前 node
2. 不直接升级为 graph 级结论

这意味着：

1. `failed / timed_out / cancelled` 首先是当前授权执行位置的问题
2. 是否进一步影响整图推进，由主链 `step` 决定

## 9. Graph 级升级规则

第一版中，subagent 异常不能自动把 graph 打成终态或阻塞态。

正式规则如下：

1. subagent 不能直接宣布 `blocked`
2. subagent 不能直接宣布 `abandoned`
3. subagent 不能直接宣布 follow-up 节点
4. 主链 `step` 才能决定是否把异常升级成：
   - `blocked`
   - `abandoned`
   - `follow-up required`

这样设计的原因是：

1. graph 级状态属于主链正式执行骨架
2. subagent 只能提供输入，不能越权写骨架状态

## 10. 回收与销毁规则

第一版明确规定：

1. 即使出现 `failed / timed_out / cancelled`，也应尽量进入 `collect -> destroy` 显式回收路径

原因如下：

1. 异常时往往更需要回收证据和残留产物
2. 如果不回收，后续归责、验证和恢复都会变差
3. `destroy` 可以防止实例在 graph 外继续漂浮

## 11. 允许无法完整回收的例外

第一版允许以下例外情况：

1. 宿主层彻底失控
2. subagent 实例不可达
3. 运行体已崩溃

只有在这些情况下，才允许无法完成完整回收路径。

也就是说：

1. 正常异常不构成跳过回收的理由
2. 只有基础运行条件失效，才允许放弃完整 `collect -> destroy`

## 12. 异常状态下的部分结果保留

第一版明确规定：

1. `failed / timed_out / cancelled` 都允许保留部分结果
2. 不能因为异常终态就默认丢弃已形成内容

可保留内容包括：

1. `artifacts`
2. `evidence`
3. `notes`

必要时也可以保留：

1. `work_summary`
2. `result_summary`

这样做的原因是：

1. 异常前可能已经形成有价值产物
2. 主链仍可能消费这些结果，或据此决定 follow-up

## 13. 异常时不允许做的事情

第一版中，subagent 在异常状态下明确不允许：

1. 直接改 `TaskGraphState`
2. 直接写 `GraphPatch`
3. 自行宣布新增 node
4. 绕过主链自行宣布后续动作

原因如下：

1. 即使发生异常，主链边界也不能被破坏
2. 异常不应成为越权写 graph 的理由

## 14. 与其他任务的关系

`S10-T6` 直接依赖：

1. `S10-T2` subagent 运行模型
2. `S10-T3` subagent 与主任务图关系
3. `S10-T5` subagent 结果、证据、状态回流

`S10-T6` 直接服务：

1. `S10-T7` subagent skeleton
2. `S2-T5` 恢复执行协议中的 subagent 边界
3. `S12` subagent 事件与异常观测对齐

## 15. 本任务结论摘要

可以压缩成 6 句话：

1. subagent 的异常终态第一版固定为 `failed / timed_out / cancelled`
2. `partial` 不属于异常终态，而是“部分可用结果”
3. subagent 只能上报状态，正式裁决权始终属于主链 `step`
4. 异常默认只作用于当前 node，不自动升级为 graph 级结论
5. 即使异常，也应尽量执行 `collect -> destroy`
6. 异常时允许保留部分结果，但不允许 subagent 直接改 graph 或绕过主链宣布后续动作
