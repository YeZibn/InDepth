# S2-T2 RuntimeHost 接口草案（V1）

更新时间：2026-04-23  
状态：Draft

## 1. 目标

为 `runtime-v2` 定义正式的 `RuntimeHost` 接口，使宿主层成为 CLI / API 与 runtime core 之间的唯一入口。

本文只回答三个问题：

1. `RuntimeHost` 对外暴露哪些正式方法。
2. 哪些职责必须留在 host，而不能下沉到 CLI 或 runtime core。
3. `RuntimeHost` 返回什么最小结果给宿主外层消费。

## 2. 设计定位

`RuntimeHost` 是宿主层正式对象。

它不负责执行 phase，也不负责理解 task graph 细节。它只负责：

1. 保存宿主态。
2. 管理 `task_id`、`run_id`。
3. 决定如何把用户输入提交给 runtime core。
4. 调用 runtime core。
5. 把 runtime 返回结果整理成宿主可消费结果。

因此，v2 中 CLI / API 不应直接操作 runtime core，而应统一经过 `RuntimeHost`。

## 3. 正式公开方法

第一版建议只暴露 4 个正式方法。

### 3.1 `start_task(label?: string) -> HostTaskRef`

作用：

1. 开启新的 task 宿主上下文。
2. 生成新的 `task_id`。
3. 清空旧的宿主运行绑定。

说明：

1. 它只处理宿主侧 task 切换。
2. 它本身不触发 runtime 执行。

### 3.2 `submit_user_input(user_input: string) -> HostRunResult`

作用：

1. 作为宿主层唯一正式执行入口。
2. 接收本轮用户输入。
3. 调用 runtime core 执行。
4. 返回宿主可消费的运行结果。

说明：

1. 第一版先只覆盖新 run 提交主链路。
2. 等待后继续推进统一通过再次调用 `submit_user_input(...)` 触发新的 `start-run`。

### 3.3 `reset_session() -> void`

作用：

1. 清空宿主当前绑定关系。
2. 清空 `current_task_id`。
3. 让 host 回到未绑定的待命状态。

说明：

1. 这是宿主控制接口，不是 runtime 清理接口。
2. 它不删除历史消息、记忆、事件或数据库记录。
3. 它只重置 host 自身内存态。

### 3.4 `get_host_state() -> RuntimeHostState`

作用：

1. 向 CLI / API 暴露当前宿主状态。
2. 用于状态展示、诊断和调试。

说明：

1. 该方法只返回宿主态快照。
2. 不返回 runtime 内部复杂状态。

## 4. 不建议公开的方法

第一版不建议把以下能力做成公开正式方法：

### 4.1 `resume_run(...)`

原因：

1. 第一版已取消独立 `resume-run` 协议。
2. 等待后继续推进统一重开新 run，不再需要单独公开恢复入口。
3. 保留该方法只会把旧语义重新带回 host 接口。

### 4.2 `run_core(...)`

原因：

1. 它会让外层绕过 host。
2. 这样会把 `task_id`、`run_id` 状态管理重新散到外层。

### 4.3 `set_waiting(...)`

原因：

1. 宿主态应由 runtime 返回结果驱动更新。
2. 不应允许外层直接写内部宿主状态。

## 5. 最小数据结构草案

第一版建议配套三个最小结构。

### 5.1 `HostTaskRef`

```ts
type HostTaskRef = {
  task_id: string;
};
```

### 5.2 `RuntimeHostState`

```ts
type RuntimeHostState = {
  session_id: string;
  current_task_id?: string;
};
```

### 5.3 `HostRunResult`

```ts
type HostRunResult = {
  task_id: string;
  run_id: string;
  runtime_state: string;
  output_text: string;
};
```

## 6. Host 内部必须承担的判断

以下判断必须保留在 `RuntimeHost` 内部：

1. 当前是否存在 `current_task_id`。
2. 当前是否需要创建默认 task。
3. 是否需要生成新的 `run_id`。
4. 当前是否需要基于已有上下文重开新的 run。

这些判断不应放到 CLI，也不应由 runtime core 反向承担。

## 7. Host 与外层的边界

CLI / API 可以做：

1. 调用 `start_task(...)`。
2. 调用 `submit_user_input(...)`。
3. 调用 `reset_session()`。
4. 读取 `get_host_state()`。

CLI / API 不应做：

1. 手动构造 runtime 内部控制标志。
2. 自行拼接 `run_id`。
3. 自行修改宿主内部状态。
4. 绕过 host 直接调用 runtime core。

## 8. 本轮确认结论

本轮已确认：

1. `RuntimeHost` 第一版正式暴露 4 个方法。
2. `submit_user_input(...)` 是唯一正式执行入口。
3. `reset_session()` 需要保留。
4. 第一版不保留独立 `resume run` 正式接口。

## 9. 对后续子任务的输入

`S2-T2` 完成后，后续可直接承接：

1. `S2-T3`：定义 `task_id / run_id / session_id` 生命周期。
2. `S2-T4`：定义 `start run` contract。
3. `S2-T5`：定义等待后重开新 run 的宿主协议。
