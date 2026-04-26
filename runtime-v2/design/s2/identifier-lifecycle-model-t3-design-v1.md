# S2-T3 标识生命周期模型（V1）

更新时间：2026-04-23  
状态：Draft

## 1. 目标

为 `runtime-v2` 定义 `session_id`、`task_id`、`run_id` 三类正式标识的生命周期关系。

本文只解决三件事：

1. 三种标识分别代表什么。
2. 它们分别由谁生成、何时变化。
3. 它们之间是什么包含关系。

## 2. 本轮结论

第一版采用以下语义：

1. `session_id`：宿主会话级标识。
2. `task_id`：单个任务上下文标识。
3. `run_id`：某次具体运行实例标识。

也就是说，`session_id` 代表一个 `RuntimeHost` 从建立到 `reset_session()` 之间的宿主会话容器。

## 3. 三类标识定义

### 3.1 `session_id`

定义：

1. 标识一个宿主会话。
2. 由 `RuntimeHost` 创建时生成。
3. 在一次宿主会话内保持稳定。

变化时机：

1. Host 初始化时生成。
2. 调用 `reset_session()` 后重新生成。

不因以下情况变化：

1. `start_task(...)`
2. `submit_user_input(...)`
3. 等待后重开新 run 时继续复用当前 `session_id`

### 3.2 `task_id`

定义：

1. 标识一个正式任务上下文。
2. 由 `RuntimeHost.start_task(...)` 生成。
3. 同一个 task 下可存在多个 `run_id`。

变化时机：

1. 显式开启新任务时变化。
2. 宿主被 reset 后，重新启动任务时变化。

不因以下情况变化：

1. 同一任务内的多轮用户补充输入。
2. 等待后重开新 run。

### 3.3 `run_id`

定义：

1. 标识一次具体 run 实例。
2. 由 `RuntimeHost` 在启动 run 时生成。
3. 第一版只保证新 run 启动时生成新的 `run_id`。

变化时机：

1. 新 run 启动时生成。
2. 上一个 run 结束后，下一次重新启动新 run 时变化。

不因以下情况变化：

1. 等待后重开新 run 时不复用旧 `run_id`。

## 4. 三者关系

第一版关系如下：

```text
session_id
  └── task_id
        └── run_id
```

更准确地说：

1. 一个 `session_id` 下可以有多个 `task_id`。
2. 一个 `task_id` 下可以有多个 `run_id`。
3. 一个 `run_id` 只属于一个 `task_id`。
4. 一个 `task_id` 只属于一个 `session_id`。

## 5. 生成归属

三类标识统一由 `RuntimeHost` 管理。

具体归属如下：

1. `session_id`：由 host 初始化或 reset 时生成。
2. `task_id`：由 `start_task(...)` 生成。
3. `run_id`：由 `submit_user_input(...)` 在需要启动新 run 时生成。

runtime core 不负责生成这些宿主标识，只负责消费它们。

## 6. 生命周期规则

### 6.1 Host 初始化

在 host 初始化时：

1. 生成 `session_id`。
2. `current_task_id` 为空。
3. `active_run_id` 为空。

### 6.2 启动新任务

调用 `start_task(...)` 时：

1. 保留当前 `session_id`。
2. 生成新的 `task_id`。
3. 清空旧的 `active_run_id`。
4. 清空旧的宿主运行绑定。

### 6.3 提交用户输入并启动新 run

调用 `submit_user_input(...)` 时：

1. 复用当前 `session_id`。
2. 复用当前 `task_id`。
3. 生成新的 `run_id`。

### 6.4 等待后继续推进并重开新 run

第一版中，等待用户回复、verification 结果、subagent 结果或工具结果之后，继续推进统一视为：

1. 复用当前 `session_id`
2. 复用当前 `task_id`
3. 生成新的 `run_id`

也就是说，第一版不定义旧 `run_id` 的恢复续接。

### 6.5 Reset Host

调用 `reset_session()` 时：

1. 结束当前宿主绑定。
2. 清空 `current_task_id`。
3. 清空 `active_run_id`。
4. 重新生成新的 `session_id`。

## 7. 为什么这样切

第一版采用这套关系，原因是：

1. `session_id` 对应宿主态，最适合挂在 `RuntimeHost` 上。
2. `task_id` 对应任务边界，最适合挂任务历史、task graph、长期执行上下文。
3. `run_id` 对应一次运行实例，最适合挂消息流、工具调用、事件与收尾结果。

这样之后：

1. `reset_session()` 语义清晰。
2. `start_task(...)` 语义清晰。
3. 第一版把等待后继续推进统一收敛为“新 run 重开”，不把恢复语义压进主标识模型。

## 8. 第一版不做的事情

第一版暂不支持以下扩展语义：

1. 用 `session_id` 表示跨多个 host 的长期工作带。
2. 让多个 `task_id` 共享同一个业务工作流主标识。
3. 把 `run_id` 提升为跨 task 的父级执行链路标识。
4. 定义旧 `run_id` 的正式恢复续接规则。

这些能力后续若需要，可以在不破坏当前第一版结构的前提下扩展。

## 9. 最小结构草案

```ts
type RuntimeHostIdentity = {
  session_id: string;
  current_task_id?: string;
  active_run_id?: string;
};
```

```ts
type RunIdentity = {
  session_id: string;
  task_id: string;
  run_id: string;
};
```

## 10. 对后续子任务的输入

`S2-T3` 完成后，后续可直接承接：

1. `S2-T4`：定义新 run 启动协议。
2. `S2-T5`：定义等待后重开新 run 的宿主协议。
3. `S4`：在正式状态模型里吸纳 `run_identity` 结构。
