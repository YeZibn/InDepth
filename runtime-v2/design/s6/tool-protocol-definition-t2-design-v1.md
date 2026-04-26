# S6-T2 Tool Protocol 定义（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S6-T2`

## 1. 目标

本任务用于定义 `runtime-v2` 的统一 tool 协议。

目标是：

1. 所有工具统一使用同一套返回信封
2. 让 runtime、task graph、verification、observability 都能围绕统一结构工作
3. 避免不同工具继续各自返回不同风格的数据

## 2. 正式结论

本任务的正式结论如下：

1. v2 所有工具统一使用标准信封
2. 成功时 `error = null`
3. 保留统一 `meta` 字段
4. 工具失败时允许返回部分 `result`
5. `meta.category` 必须显式区分工具域

## 3. 标准信封

v2 工具返回统一定义为：

```json
{
  "success": true,
  "error": null,
  "result": {},
  "meta": {}
}
```

字段含义：

1. `success`
   表示本次工具调用是否成功

2. `error`
   失败时为错误信息；成功时固定为 `null`

3. `result`
   工具的主要结果载荷

4. `meta`
   工具调用的统一元信息

## 4. 字段规则

## 4.1 success

规则：

1. `success=true` 表示工具已完成其主要目标
2. `success=false` 表示工具未完成其主要目标

## 4.2 error

规则：

1. 成功时固定为 `null`
2. 失败时必须为非空错误信息
3. 不使用空字符串 `""` 作为成功时占位

## 4.3 result

规则：

1. `result` 始终存在
2. 成功时承载主要返回数据
3. 失败时允许携带部分上下文或部分结果

这样设计的原因是：

1. runtime 恢复逻辑需要更多上下文
2. observability 和 postmortem 需要保留失败现场
3. 某些工具可能部分完成但总体失败

## 4.4 meta

规则：

1. `meta` 始终存在
2. 第一版允许字段较少，但必须保留统一入口

第一版建议最少包含：

1. `tool_name`
2. `category`
3. `duration_ms`
4. `source`
5. `warnings`

## 5. 工具域分类

v2 在 `meta.category` 中显式区分工具域。

第一版建议使用以下分类：

1. `execution`
2. `task_graph`
3. `node`
4. `memory`
5. `search`
6. `subagent`

说明：

1. 图级工具使用 `task_graph`
2. 节点级工具使用 `node`
3. 基础执行工具使用 `execution`

## 6. 失败返回示例

失败时允许返回部分 `result`，示意如下：

```json
{
  "success": false,
  "error": "node not found",
  "result": {
    "graph_id": "graph_123",
    "requested_node_id": "node_9"
  },
  "meta": {
    "tool_name": "update_node_status",
    "category": "node",
    "duration_ms": 12,
    "source": "runtime",
    "warnings": []
  }
}
```

## 7. 适用范围

本任务明确规定：

1. 所有 v2 工具统一采用这套信封
2. 不区分“内部工具”和“外部工具”的协议风格
3. 如果旧工具不兼容，必须通过适配层转换后再进入 v2

这意味着：

1. v2 runtime 只消费统一协议
2. v2 observability 只围绕统一协议记录
3. v2 verification 只围绕统一结果结构取证

## 8. 与命名决策的对接

本任务已经和 `S5-T2` 对齐：

1. 不再使用 `todo` / `subtask` 命名
2. 图级工具使用 `task_graph`
3. 节点级工具使用 `node`

例如：

1. `plan_task_graph`
2. `update_node_status`
3. `get_next_node`
4. `reopen_node`
5. `append_followup_nodes`
6. `generate_task_graph_report`

## 9. 对其他任务的直接输入

`S6-T2` 直接服务：

1. `S6-T3` runtime 与工具语义耦合策略
2. `S6-T4` 工具分域结构
3. `S6-T5` tool call 进入状态流、事件流、证据链的路径
4. `S6-T6` tool registry skeleton
5. `S3-T5` runtime skeleton

同时它也会直接影响：

1. `S5-T3` task graph 最小执行单元接口
2. `S11-T2` run outcome 中的工具结果表达
3. `S12-T2` 事件模型中的工具事件载荷结构

## 10. 本任务结论摘要

可以压缩成 5 句话：

1. v2 所有工具统一使用 `success / error / result / meta` 信封
2. 成功时 `error` 固定为 `null`
3. 失败时允许保留部分 `result`
4. `meta` 是正式字段，不是可选附属信息
5. `meta.category` 必须显式区分工具域
