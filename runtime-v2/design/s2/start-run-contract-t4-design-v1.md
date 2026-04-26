# S2-T4 新 Run 启动协议（V1）

更新时间：2026-04-23  
状态：Draft

## 1. 目标

定义 `RuntimeHost` 在“启动一个新 run”时的最小协议，确保宿主层、runtime core、状态模型层后续对齐。

本文只解决四件事：

1. 什么情况下算 `start run`。
2. `start run` 前 host 必须准备什么。
3. `start run` 调用 runtime core 时传什么。
4. `start run` 返回后 host 如何更新宿主态。

## 2. 本轮结论

第一版采用以下规则：

1. `submit_user_input(...)` 是唯一正式用户入口。
2. 第一版只定义 `start run` 主链路。
3. 若当前还没有 `task_id`，host 自动创建默认 task。
4. `start run` 时必须生成新的 `run_id`。

## 3. 何时进入 `start run`

以下任一情况成立时，host 应进入 `start run`：

1. 当前刚调用过 `start_task(...)`。
2. 当前 host 处于 reset 后的新待命状态。
3. 当前收到一次需要正式提交给 runtime 的新输入。

换句话说，第一版 `submit_user_input(...)` 默认进入 `start run`。

## 4. Host 前置准备

进入 `start run` 之前，host 必须完成以下准备：

### 4.1 保证存在 `session_id`

1. `session_id` 必须已经存在。
2. 若 host 已初始化，则直接复用当前 `session_id`。

### 4.2 保证存在 `task_id`

1. 若已有 `current_task_id`，则直接复用。
2. 若还没有 `current_task_id`，则 host 自动创建默认 task。

第一版建议：

1. 自动补建默认 task。
2. 不要求外层必须先显式调用 `start_task(...)`。

### 4.3 生成新的 `run_id`

1. 新 run 启动时必须生成新的 `run_id`。
2. 不复用已结束 run 的 `run_id`。

## 5. 传给 RuntimeCore 的最小输入

第一版建议 `RuntimeHost` 在调用 runtime core 时，至少传入以下字段：

```ts
type StartRunInput = {
  session_id: string;
  task_id: string;
  run_id: string;
  user_input: string;
};
```

说明：

1. runtime core 接收的就是一次新的 `start-run` 输入。
2. 第一版不再使用 `is_resume` 这类区分位。
3. 第一版不要求 CLI / API 直接接触这个结构。

## 6. Start Run 结果

runtime core 返回后，host 至少需要拿到：

```ts
type StartRunOutput = {
  run_id: string;
  runtime_state: string;
  output_text: string;
};
```

## 7. Host 回写规则

收到 `StartRunOutput` 后，host 按最小规则更新宿主态：

1. 保留当前 `task_id`。
2. 返回本次 `run_id` 供宿主外层消费与诊断。

## 8. 自动补建默认 Task 的理由

第一版采用“自动补建默认 task”，原因如下：

1. `submit_user_input(...)` 可以成为真正单一主入口。
2. 外层调用方不需要先理解任务初始化协议。
3. 宿主层可以吸收“是否已有 task”这类样板判断。
4. 更符合 CLI / API 的自然使用方式。

## 9. 第一版不做的事情

第一版暂不在 `start run` 阶段支持：

1. 外层传入自定义 `run_id`。
2. 外层跳过 host 直接构造 `StartRunInput`。
3. 在启动新 run 时自动切换 `session_id`。
4. 在没有 task 的情况下抛错阻止执行。
5. 定义等待后重开新 run 的正式宿主协议。

## 10. 最小时序

```text
submit_user_input(user_input)
  -> 保证 session_id 存在
  -> 保证 task_id 存在，不存在则自动创建默认 task
  -> 生成新 run_id
  -> 调用 RuntimeCore.start run
  -> 收到 runtime_state / output_text
  -> 回写 host state
  -> 返回 HostRunResult
```

## 11. 对后续子任务的输入

`S2-T4` 完成后，后续可直接承接：

1. `S2-T5`：定义等待后重开新 run 的宿主协议。
2. `S2-T6`：定义 CLI 如何收缩到只消费 host 接口。
3. `S3`：让 runtime core 只消费统一的 `start-run` 输入。
