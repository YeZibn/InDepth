# ReAct Step 实现说明

## 当前范围

当前 `runtime-v2` 已正式落地最小单轮 ReAct step 骨架，并已接入 execute 主链中的最小 `RUNNING` 节点分支。

当前已实现：

1. `rtv2.model` 最小模型接入层
2. `HttpChatModelProvider`
3. `ReActStepInput`
4. `ReActStepOutput`
5. `ReActStepRunner`
6. `rtv2.tools` 最小本地工具协议与执行层

对应代码：

1. [src/rtv2/model/base.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/model/base.py)
2. [src/rtv2/model/http_chat_provider.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/model/http_chat_provider.py)
3. [src/rtv2/solver/react_step.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/react_step.py)
4. [src/rtv2/tools/models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/tools/models.py)
5. [src/rtv2/tools/decorator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/tools/decorator.py)
6. [src/rtv2/tools/registry.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/tools/registry.py)
7. [src/rtv2/tools/executor.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/tools/executor.py)
8. [src/rtv2/orchestrator/runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
9. [tests/test_react_step.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_react_step.py)
10. [tests/test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)
11. [tests/test_tools.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_tools.py)

## 当前设计结论

当前这一步按 agent step 视角建模，而不是按 runtime 内部状态参数建模。

当前正式结构如下：

1. `ReActStepInput`
   - `step_prompt: str`
2. `ReActStepOutput`
   - `thought: str`
   - `action: str`
   - `observation: str`
   - `tool_call: ToolCall | None`
   - `step_result: StepResult | None`

其中：

1. `step_prompt` 表示本轮真正喂给 agent 的完整提示上下文
2. `thought / action / observation` 当前都先采用字符串字段
3. 当本轮需要工具时，先返回中间态 `tool_call`
4. 当本轮已经完成判断时，再返回正式 `step_result`

## 当前 LLM 接入方式

当前实现只借鉴旧版 InDepth 的 `.env` 约定和 OpenAI-compatible chat 协议，不直接依赖旧版 `app/*` 代码。

当前环境变量约定如下：

1. `LLM_MODEL_ID`
2. `LLM_API_KEY`
3. `LLM_BASE_URL`

当前 `HttpChatModelProvider` 的特点如下：

1. 直接读取 `.env` 和系统环境变量
2. 通过 OpenAI-compatible `/chat/completions` 发起请求
3. 当前支持最小 `GenerationConfig`
4. 当前已经支持最小本地 tool schema 透传与单次 tool 调用

## 当前执行流程

`ReActStepRunner.run_step(...)` 当前执行链路如下：

1. 接收 `ReActStepInput(step_prompt=...)`
2. 第一轮构造最小 messages 与可用 tool schemas
3. 调用 `model_provider.generate(messages, tools=schemas, config=...)`
4. 第一轮结果分两种：
   - 若模型直接返回最终 JSON
     - 直接解析为正式 `StepResult`
   - 若模型返回单次 `tool_call`
     - runtime 通过 `LocalToolExecutor` 执行本地工具
5. 若发生 tool call：
   - 组装第二轮 follow-up messages
   - 把 tool 结果作为 observation 上下文回填给模型
   - 第二轮禁止再次发起 tool call
6. 解析第二轮最终 JSON
7. 返回正式 `ReActStepOutput`

## 当前 tool 接线方式

当前 ReAct step 已具备最小本地工具能力：

1. `ReActStepRunner` 当前可注入：
   - `ToolRegistry`
   - `LocalToolExecutor`
2. 第一轮请求会把 `tool_registry.list_tool_schemas()` 传给模型
3. 当前支持两种 tool call 来源：
   - OpenAI-compatible `message.tool_calls`
   - JSON 结构中的 `tool_call`
4. 当前单轮最多只允许一次 tool call
5. 若第二轮仍尝试返回 tool call：
   - 当前直接按失败收口
6. 若模型请求 tool，但 runtime 未配置 executor：
   - 当前直接按失败收口

## 当前 execute 接线方式

当前 orchestrator 只在非常小的范围内接入 ReAct step：

1. 当 execute 选中的 node 为 `RUNNING` 时：
   - 不再直接本地构造 `RUNNING -> COMPLETED` 的最小推进结果
   - 改为调用一次 `ReActStepRunner`
2. orchestrator 会先组装最小 `step_prompt`
3. `step_prompt` 当前只包含：
   - `user_input`
   - 当前 node 的 `node_id / name / kind / status / description`
   - 当前单轮 step 的最小执行要求
4. orchestrator 当前只正式消费：
   - `react_output.step_result`
5. 若 `step_result.patch` 非空：
   - 仍由现有 `TaskGraphStore.apply_patch(...)` 回写 graph
6. 若 `step_result.patch` 为空：
   - 当前不额外生成补丁
   - 只表示 execute 已经通过真实 ReAct step 获得了一次正式 `StepResult`

## 当前输出约束

当前要求模型返回以下 JSON 字段：

1. `thought`
2. `action`
3. `observation`
4. `status_signal`
5. `reason`
6. 可选 `tool_call`

其中：

1. `status_signal` 当前最小集合为：
   - `progressed`
   - `ready_for_completion`
   - `blocked`
   - `failed`
2. 当 `status_signal != progressed` 时，`reason` 必须非空

## 当前边界

当前这一步明确不进入：

1. unified runtime memory
2. `Reflexion`
3. `Completion Evaluator`
4. 多轮 solver 循环
5. graph 全量上下文注入
6. 模型侧正式生成 `TaskGraphPatch`
7. 主链级 tool 事件 / 记忆沉淀

这些内容会在后续模块继续落地。
