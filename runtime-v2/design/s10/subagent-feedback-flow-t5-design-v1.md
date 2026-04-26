# S10-T5 SubAgent 结果、证据、状态回流（V1）

更新时间：2026-04-24  
状态：Draft  
对应任务：`S10-T5`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版中 subagent 的结果、证据和状态如何正式回流到主链。

本任务不再讨论：

1. subagent 的运行模型
2. subagent 与主任务图的绑定结构
3. subagent 角色模型
4. subagent 失败、超时、取消策略细节

这里只回答五件事：

1. subagent 最小结果包应包含什么
2. 哪些内容属于正式回流
3. 哪些内容不应默认进入主链正式状态
4. 主链 `collect` 后如何处理这些回流内容
5. `handoff_hint` 的正式定位是什么

## 2. 正式结论

第一版正式结论如下：

1. `subagent` 的正式回流目标是让主链知道：
   - 它做了什么
   - 它最终做成了什么、做到什么程度
2. 第一版最小结果包采用 7 类字段：
   - `execution_status`
   - `work_summary`
   - `result_summary`
   - `artifacts`
   - `evidence`
   - `notes`
   - `handoff_hint`
3. `execution_status` 第一版固定为：
   - `completed`
   - `failed`
   - `partial`
   - `timed_out`
   - `cancelled`
4. `work_summary` 用于回答“做了什么”
5. `result_summary` 用于回答“产出了什么、达到什么程度”
6. `artifacts` 表达正式产物引用
7. `evidence` 表达支撑结果成立的关键证据
8. `notes` 表达补充说明、局部观察和限制条件
9. `handoff_hint` 只作为主链 `step` 的判断输入
10. `handoff_hint` 不直接写入 graph 正式状态
11. `handoff_hint` 第一版采用轻文本字段
12. `artifacts` 和 `evidence` 第一版都采用数组结构，即使为空也保留数组形态
13. `subagent` 不直接返回 `NodePatch / GraphPatch`
14. `subagent` 不直接返回新增 node 列表或 graph 写回指令
15. subagent 的完整消息历史、推理过程和细碎中间态，不默认进入主链正式状态

## 3. 回流目标

第一版中，subagent 回流到主链的内容必须服务一个非常直接的目标：

1. 让主链知道 subagent 实际执行了什么
2. 让主链知道 subagent 最终交付了什么
3. 让主链知道这些结果是否有足够证据支撑
4. 让主链知道下一步是否需要继续推进、补充、返工或切换路径

因此第一版不追求把 subagent 的全部内部运行细节回灌主链，而只保留主链真正需要的正式输入。

## 4. 为什么要拆成 `work_summary` 和 `result_summary`

第一版明确规定：

1. 不能只保留一个笼统的 `summary`
2. 必须区分“做了什么”和“结果是什么”

原因如下：

1. 主链需要同时判断 subagent 是否按授权范围执行
2. 主链还需要判断 subagent 交回的结果是否足以支持下一步
3. 如果两者混在一个字段里，后续 `collect`、`closeout`、证据提取和问题归责都会不稳定

因此第一版采用：

1. `work_summary`
   - 偏过程摘要
   - 回答“这次做了哪些动作”
2. `result_summary`
   - 偏结果摘要
   - 回答“最终产出了什么、达到什么程度”

## 5. 最小结果包

第一版最小结果结构如下：

```ts
type SubAgentResult = {
  execution_status: "completed" | "failed" | "partial" | "timed_out" | "cancelled";
  work_summary: string;
  result_summary: string;
  artifacts: Array<{
    kind: string;
    ref: string;
    summary?: string;
  }>;
  evidence: Array<{
    kind: string;
    summary: string;
    ref?: string;
  }>;
  notes: string[];
  handoff_hint?: string;
};
```

## 6. 各字段定位

### 6.1 `execution_status`

作用：

1. 表达 subagent 最终执行结果状态
2. 为主链判断当前 node 是否完成、失败、部分完成、超时或取消提供直接输入

第一版固定取值如下：

1. `completed`
2. `failed`
3. `partial`
4. `timed_out`
5. `cancelled`

### 6.2 `work_summary`

作用：

1. 说明 subagent 实际执行了哪些动作
2. 帮助主链判断其是否按授权边界工作

### 6.3 `result_summary`

作用：

1. 说明 subagent 最终形成了什么结果
2. 帮助主链判断当前输出是否足以支撑下一步

### 6.4 `artifacts`

作用：

1. 表达正式产物引用
2. 让主链知道有哪些可被后续使用、验证或交接的结果对象

第一版采用数组结构，即使为空也保留数组。

### 6.5 `evidence`

作用：

1. 表达支撑结果成立的关键证据
2. 为主链后续验证、closeout 和归责提供基础材料

第一版采用数组结构，即使为空也保留数组。

### 6.6 `notes`

作用：

1. 表达补充说明
2. 承接局部观察、限制条件、未展开细节或边界说明

### 6.7 `handoff_hint`

作用：

1. 为主链 `step` 提供后续处理提示
2. 例如提示是否需要继续跟进、补充确认或转入其他动作

第一版采用轻文本字段，不采用结构化对象。

## 7. 正式回流的内容

第一版正式回流的内容主要包括：

1. 执行结果状态
2. 过程摘要
3. 结果摘要
4. 产物引用
5. 关键证据
6. 补充说明
7. 后续处理提示

这些内容共同构成主链在 `collect` 节点可消费的正式输入。

## 8. 不默认进入主链正式状态的内容

第一版明确规定，下列内容不默认进入主链正式状态：

1. subagent 的完整消息历史
2. subagent 的完整推理过程
3. 细碎的中间状态变更
4. 原始 tool 调用流水
5. graph 写回指令

原因如下：

1. 这些内容大多属于 subagent 内部运行细节
2. 如果默认回灌主链，会迅速污染正式状态结构
3. 主链真正需要的是稳定、可消费、可归责的结果输入，而不是完整内部轨迹

## 9. `handoff_hint` 的正式定位

第一版明确规定：

1. `handoff_hint` 只作为主链 `step` 的判断输入
2. `handoff_hint` 不具有正式 graph 写权限

这意味着：

1. 它可以影响主链的后续判断
2. 但它不能直接变成 graph 事实
3. 是否采纳、如何采纳，由主链 `step` 裁决

这样设计的原因是：

1. 避免 subagent 变成主链调度者
2. 保持 graph 正式写回入口唯一
3. 让提示和正式状态保持边界清晰

## 10. `collect` 后主链的处理规则

第一版中，主链在 `collect` 之后可按如下方式处理回流内容：

### 可作为当前 node 正式结果输入的内容

1. `execution_status`
2. `result_summary`
3. `artifacts`
4. `evidence`

### 可作为附加说明的内容

1. `notes`

### 仅作为后续判断提示的内容

1. `handoff_hint`

这里明确规定：

1. `handoff_hint` 不直接进入 graph 正式状态
2. 是否转成正式 `NodePatch / GraphPatch`，只能由主链 `step` 决定

## 11. 第一版不做的事情

第一版中，`S10-T5` 明确不做以下设计：

1. 不让 subagent 直接返回 `NodePatch`
2. 不让 subagent 直接返回 `GraphPatch`
3. 不让 subagent 直接返回新增 node 列表
4. 不让 subagent 直接切换 active node
5. 不默认把完整消息历史和推理过程回灌主链

## 12. 与其他任务的关系

`S10-T5` 直接依赖：

1. `S10-T2` subagent 运行模型
2. `S10-T3` subagent 与主任务图关系
3. `S10-T4` subagent 角色模型

`S10-T5` 直接服务：

1. `S10-T6` subagent 失败、超时、取消规则
2. `S10-T7` subagent skeleton
3. `S11` closeout 与证据链整合
4. `S12` subagent 观测与事件对齐

## 13. 本任务结论摘要

可以压缩成 6 句话：

1. subagent 回流的核心目标是让主链知道“做了什么”和“最后做成了什么”
2. 第一版最小结果包采用 `execution_status / work_summary / result_summary / artifacts / evidence / notes / handoff_hint`
3. `summary` 必须拆成 `work_summary` 和 `result_summary`
4. `handoff_hint` 只作为主链 `step` 的输入，不直接写入 graph
5. `artifacts` 和 `evidence` 都采用数组结构，即使为空也保留数组
6. subagent 不直接返回 patch、graph 写回指令或完整内部运行轨迹
