# S2-T6 CLI 收缩与迁移说明（V1）

更新时间：2026-04-23  
状态：Draft

## 1. 目标

定义 `runtime-v2` 中 CLI 的收缩方向，确保 CLI 只保留宿主壳职责，不再承载 runtime 语义。

本文只回答三件事：

1. 现有 CLI 哪些能力保留。
2. 哪些能力应移出 CLI。
3. CLI 后续如何迁移到只依赖 `RuntimeHost`。

## 2. 当前 CLI 的实际定位

当前 CLI 主要位于：

1. `app/agent/runtime_agent.py`

它当前承担的能力包括：

1. 创建默认 agent。
2. 解析 `/task`、`/new`、`/status`、`/exit`。
3. 启动交互循环。
4. 把输入转交给 `BaseAgent.chat(...)`。
5. 对部分运行状态做外层提示。

## 3. v2 中 CLI 的正式定位

v2 中 CLI 应收缩为纯宿主壳层。

CLI 只负责：

1. 接收用户输入。
2. 解析 CLI 命令。
3. 调用 `RuntimeHost` 对外接口。
4. 渲染输出文本。
5. 展示最小宿主状态。

CLI 不负责：

1. 生成 `task_id`、`run_id`、`session_id`。
2. 决定 runtime 内部控制参数。
3. 直接调用 runtime core。
4. 解释 phase、handoff、task graph、tool registry 等内部结构。

## 4. 第一版建议保留的 CLI 命令

第一版建议保留以下命令：

1. `/task <label>`
作用：开启一个新 task。

2. `/status`
作用：展示最小宿主状态。

3. `/exit`
作用：退出当前 CLI 会话。

4. `/help`
作用：展示当前 CLI 命令帮助。

## 5. 第一版暂不开放的 CLI 命令

第一版暂不新增 `/reset`。

原因：

1. 当前主链路还不需要专门暴露宿主重置命令。
2. `reset_session()` 先保留为 host 内部或后续扩展接口。
3. 避免 CLI 在第一版过早变成宿主调试面板。

## 6. CLI 调用方式收缩

第一版之后，CLI 应只调用以下 `RuntimeHost` 接口：

1. `start_task(...)`
2. `submit_user_input(...)`
3. `get_host_state()`

除此以外，CLI 不应再直接触碰：

1. `AgentRuntime`
2. `bootstrap.py` 的装配细节
3. runtime 内部控制标志

## 7. 状态展示最小化

第一版 `CLI /status` 建议只展示：

```ts
type CliStatusView = {
  session_id: string;
  current_task_id?: string;
  active_run_id?: string;
  last_runtime_state?: string;
};
```

说明：

1. 第一版不展示更深层 runtime state。
2. 第一版不展示 phase、tool state、handoff state、memory state。
3. 状态信息保持可读，不扩展成调试面板。

## 8. 迁移步骤

建议按以下顺序迁移：

1. 先把 CLI 从 `BaseAgent` 切到 `RuntimeHost`。
2. 再把 CLI 中的状态展示改为只读取 `get_host_state()`。
3. 再把 `/task`、普通输入分别映射到 host 正式接口。
4. 最后移除 CLI 对 runtime 细节的直接假设。

## 9. 兼容策略

第一版兼容策略建议如下：

1. `/new` 不再保留。
2. `/mode` 不再保留为正式命令。
3. 普通文本输入默认调用 `submit_user_input(...)`。
4. 旧的 `BaseAgent.chat(...)` 入口后续逐步下线。

## 10. 第一版不做的事情

第一版暂不在 CLI 层支持：

1. 直接控制 phase。
2. 直接恢复旧 run。
3. 直接查看 runtime 内部消息状态。
4. 直接操作 task graph。
5. 直接触发 verifier 或 memory write。

## 11. 最终收缩目标

第一版完成后，CLI 应变成下面这条极简链路：

```text
CLI command / user input
  -> RuntimeHost
  -> RuntimeCore
  -> HostRunResult
  -> CLI render
```

也就是说：

1. CLI 是壳。
2. Host 是宿主管理层。
3. RuntimeCore 是执行层。

## 12. 对后续工作的输入

`S2-T6` 完成后：

1. `S2` 入口与宿主层第一版主线基本闭环。
2. 后续可以把重点切回 `S1 / S3 / S4 / S5` 的主干实现设计。
