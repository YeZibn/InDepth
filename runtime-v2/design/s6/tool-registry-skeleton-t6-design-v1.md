# S6-T6 Tool Registry Skeleton（V1）

更新时间：2026-04-22  
状态：Draft  
对应任务：`S6-T6`

## 1. 目标

本任务用于定义 `runtime-v2` 第一版 tool registry / adapter / validator 的最小骨架。

目标是：

1. 明确 v2 工具系统最小组件集合
2. 明确 registry、adapter、validator、executor 的职责边界
3. 让后续工具接入有统一入口，不再散落在 runtime 中

## 2. 正式结论

本任务最终结论如下：

1. v1 工具系统至少包含 4 个核心组件
2. registry 只负责注册与查询
3. adapter 只负责旧工具或具体实现适配
4. validator 只负责输入与协议校验
5. executor / gateway 负责真正执行工具调用

## 3. 第一版最小组件集合

第一版建议至少包含：

1. `ToolRegistry`
2. `ToolSpec`
3. `ToolValidator`
4. `ToolExecutor`
5. `ToolAdapter`

## 4. ToolSpec

`ToolSpec` 是工具的正式注册描述对象。

第一版建议至少包含：

```ts
type ToolSpec = {
  tool_name: string;
  category: "execution" | "task_graph" | "closeout" | "memory_search" | "subagent";
  description: string;
  input_schema_ref?: string;
  output_schema_ref?: string;
  handler_ref: string;
};
```

作用：

1. 给 registry 提供统一注册单位
2. 给 validator 提供校验依据
3. 给 executor 提供调度入口

## 5. ToolRegistry

`ToolRegistry` 的职责只包括：

1. 注册 `ToolSpec`
2. 按 `tool_name` 查询
3. 按 `category` 列出
4. 提供只读工具目录

它不负责：

1. 执行工具
2. 做参数校验
3. 解释业务语义
4. 更新 runtime 状态

推荐最小接口方向：

```ts
interface ToolRegistry {
  register(spec: ToolSpec): void;
  get(tool_name: string): ToolSpec | null;
  list(): ToolSpec[];
  list_by_category(category: ToolSpec["category"]): ToolSpec[];
}
```

## 6. ToolValidator

`ToolValidator` 的职责只包括：

1. 校验请求参数
2. 校验工具输出是否满足统一 envelope
3. 校验 `meta.category` 是否与 `ToolSpec` 一致

它不负责：

1. 执行工具
2. 解释 graph 语义
3. 修改状态

推荐最小接口方向：

```ts
interface ToolValidator {
  validate_request(tool: ToolSpec, args: unknown): void;
  validate_result(tool: ToolSpec, result: unknown): void;
}
```

## 7. ToolAdapter

`ToolAdapter` 的职责只包括：

1. 把旧工具接到 v2 统一协议
2. 把不同实现风格包装成统一 handler
3. 处理兼容层或迁移层

它不负责：

1. 工具目录管理
2. 运行时状态写回
3. 事件发射

推荐最小接口方向：

```ts
interface ToolAdapter {
  adapt(raw_tool: unknown): ToolSpec;
}
```

结论上：

1. 旧名兼容只允许在 adapter / compat 层存在
2. v2 正式 registry 中只注册新名字

## 8. ToolExecutor

`ToolExecutor` 是真正执行工具调用的统一入口。

它的职责包括：

1. 从 registry 查找工具
2. 调用 validator 校验请求
3. 执行 handler
4. 校验结果 envelope
5. 返回统一 tool result

它不负责：

1. 直接改 `RunContext`
2. 直接改 `TaskGraphState`
3. 直接发明 `StepResult`

推荐最小接口方向：

```ts
interface ToolExecutor {
  call(tool_name: string, args: unknown): ToolEnvelope;
}
```

## 9. ToolGateway 的位置

如果 runtime 侧需要一个更贴近 orchestrator 的入口，建议保留一个薄层：

```ts
interface ToolGateway {
  call(tool_name: string, args: unknown): ToolEnvelope;
}
```

它的定位是：

1. 给 `step` 或 `finalize` 提供调用入口
2. 内部委托 registry / validator / executor

第一版中：

1. `ToolGateway` 可以存在
2. 但它应保持很薄
3. 不应重新吞掉 registry / executor 的职责

## 10. 与工具分域的关系

本任务与 `S6-T4` 对齐如下：

1. 所有工具在注册时必须带正式 `category`
2. category 只能使用：
   - `execution`
   - `task_graph`
   - `closeout`
   - `memory_search`
   - `subagent`

registry 只负责保存这个分域信息，不解释它的 runtime 含义。

## 11. 与状态流的关系

本任务与 `S6-T5` 对齐如下：

1. executor 只返回统一 envelope
2. tool result 如何进入：
   - `NodePatch`
   - `TaskGraphState`
   - `handoff`
   - `RunOutcome`
   由 runtime / orchestrator 侧决定

也就是说：

1. 工具系统负责“调用成功并返回结构化结果”
2. runtime 负责“如何消费这个结果”

## 12. 推荐最小骨架关系

可以用下面这张图理解：

```text
ToolGateway
  -> ToolRegistry
  -> ToolValidator
  -> ToolExecutor
       -> handler

ToolAdapter
  -> produces ToolSpec
  -> register into ToolRegistry
```

## 13. 第一版边界

第一版明确不建议：

1. registry 直接执行工具
2. validator 直接解释业务语义
3. executor 直接写 runtime 状态
4. adapter 继续把旧 runtime 语义偷带进 v2 正式接口

## 14. 对其他任务的直接输入

`S6-T6` 直接服务：

1. `S3-T5` Step / Orchestrator 契约实现
2. `S6-T5` tool call 落账路径实现
3. `S12-T3` 工具事件接入
4. `S12-T4` 工具事件 payload 规范

同时它直接依赖：

1. `S6-T2` 统一 tool protocol
2. `S6-T4` 工具分域结构
3. `S6-T5` 状态流 / 事件流 / 证据链路径

## 15. 本任务结论摘要

可以压缩成 5 句话：

1. v1 工具系统最少包含 registry、adapter、validator、executor
2. registry 只负责注册与查询
3. adapter 只负责兼容与统一接入
4. validator 只负责请求和结果校验
5. executor 只负责执行，不直接写 runtime 状态
