# S2-T1 入口职责清单（V1）

更新时间：2026-04-23  
状态：Draft

## 1. 目标

明确 `runtime-v2` 在“入口与宿主层”中的职责切分，避免后续重构时继续把 CLI、宿主态、依赖装配、runtime 执行混在一起。

本文只回答三个问题：

1. 当前入口链路里，谁在负责什么。
2. v2 中这些职责分别应保留在哪一层。
3. 旧入口代码后续如何迁移。

## 2. 当前入口链路拆分

当前入口链路可拆为四层：

1. `runtime_agent.py`
2. `BaseAgent`
3. `bootstrap.py`
4. `AgentRuntime`

它们当前的实际职责如下。

## 3. 当前职责盘点

### 3.1 `runtime_agent.py`

当前定位：CLI 壳层。

当前职责：

1. 创建默认 agent。
2. 解析 `/task`、`/new`、`/status`、`/exit` 等命令。
3. 接收用户输入并把消息转交给 `BaseAgent.chat(...)`。
4. 处理最外层的交互循环。

当前判断：

1. 这一层已经足够薄。
2. 它不应该继续承担 runtime 语义。
3. 后续应继续保留为“输入输出壳层”。

### 3.2 `BaseAgent`

当前定位：会话宿主壳。

当前职责：

1. 保存 `current_task_id`。
2. 保存 `active_run_id`。
3. 保存 `awaiting_user_input`。
4. 决定本轮是否直接启动新 run，以及等待后是否重开新 run。
5. 调用 `runtime.run(...)`。
6. 根据 runtime 返回态更新宿主侧状态。

当前判断：

1. 它已经不只是“agent 对象包装器”。
2. 它实际上承担了宿主态管理职责。
3. 这个角色在 v2 中应保留，但建议正式改名为 `RuntimeHost`。

### 3.3 `bootstrap.py`

当前定位：依赖装配层。

当前职责：

1. 构造 `GenerationConfig`。
2. 构造 `ModelProvider`。
3. 构造 `MemoryStore` 与压缩器。
4. 构造 `ToolRegistry`。
5. 挂载 skills 与 skill tools。
6. 组装 `AgentRuntime` 所需依赖参数。

当前判断：

1. 它本质上已经是 runtime 的 factory / assembler。
2. 这层不应承载执行流程，只负责装配。
3. v2 中应继续保留为正式装配层。

### 3.4 `AgentRuntime`

当前定位：run 执行核心。

当前职责：

1. 接收 `user_input`、`task_id`、`run_id`、`resume_from_waiting`。
2. 驱动 prepare / execute / finalize 主链路。
3. 维护运行期状态、工具调用、收尾和记忆写回。

当前判断：

1. 它是 runtime core，不属于入口层。
2. 入口层只应调用它，不应与它共享宿主侧判断职责。

## 4. v2 正式职责切分

基于当前代码现状，v2 建议切分为四个正式角色。

### 4.1 CLI / UI Shell

职责：

1. 接收用户输入。
2. 解析宿主命令。
3. 展示输出。

不负责：

1. 生成 runtime 内部状态。
2. 决定 phase 切换。
3. 推断 run 恢复逻辑。

### 4.2 RuntimeHost

职责：

1. 保存宿主侧会话状态。
2. 管理 `task_id`、`run_id`。
3. 决定何时发起 `start run`，以及等待后如何重开新 run。
4. 持有 runtime core 实例。
5. 作为 CLI / API 与 runtime core 之间的唯一宿主接口。

不负责：

1. 执行 phase 逻辑。
2. 维护 task graph 正式状态。
3. 处理工具语义或 verification 语义。

### 4.3 RuntimeBootstrap

职责：

1. 组装 runtime 所需依赖。
2. 固化各链路 config。
3. 构造 host 和 runtime core 所需对象。

不负责：

1. 保存宿主态。
2. 决定 start / resume。
3. 执行 run。

### 4.4 RuntimeCore

职责：

1. 执行一次 run。
2. 消费 host 给出的启动参数。
3. 返回运行结果与宿主可消费状态。

不负责：

1. 自行生成宿主标识。
2. 自行判断自己是否属于某个长期会话。
3. 反向承担 CLI 交互逻辑。

## 5. 本轮确认的关键决策

本轮已确认以下边界：

1. `BaseAgent` 在 v2 中建议正式收敛为 `RuntimeHost`。
2. `task_id`、`run_id` 由 host 层负责管理。

## 6. 迁移建议

后续迁移时，建议按下面顺序处理：

1. 先把 `BaseAgent` 从“兼容旧 agent 对象”重命名为正式 `RuntimeHost`。
2. 再把 `bootstrap.py` 从“runtime kwargs 构造函数”收敛为正式 bootstrap / factory 层。
3. 最后让 CLI 仅依赖 `RuntimeHost`，不再直接感知 runtime 细节。

## 7. 对后续子任务的输入

`S2-T1` 完成后，后续子任务可直接承接：

1. `S2-T2`：定义 `RuntimeHost` 正式接口。
2. `S2-T3`：定义 `task_id / run_id / session_id` 标识模型。
3. `S2-T4`：定义 start-run contract。
4. `S2-T5`：定义等待后重开新 run 的宿主协议。
