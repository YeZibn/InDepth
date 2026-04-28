# ReAct Step 实现说明

## 当前范围

当前 `runtime-v2` 已正式落地最小单轮 ReAct step 骨架，并已接入 execute 主链中的最小 `RUNNING` 节点分支。

当前已实现：

1. `rtv2.model` 最小模型接入层
2. `HttpChatModelProvider`
3. `ReActStepInput`
4. `ReActStepOutput`
5. `ReActStepRunner`

对应代码：

1. [src/rtv2/model/base.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/model/base.py)
2. [src/rtv2/model/http_chat_provider.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/model/http_chat_provider.py)
3. [src/rtv2/solver/react_step.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/react_step.py)
4. [src/rtv2/orchestrator/runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
5. [tests/test_react_step.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_react_step.py)
6. [tests/test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)

## 当前设计结论

当前这一步按 agent step 视角建模，而不是按 runtime 内部状态参数建模。

当前正式结构如下：

1. `ReActStepInput`
   - `step_prompt: str`
2. `ReActStepOutput`
   - `thought: str`
   - `action: str`
   - `observation: str`
   - `step_result: StepResult`

其中：

1. `step_prompt` 表示本轮真正喂给 agent 的完整提示上下文
2. `thought / action / observation` 当前都先采用字符串字段
3. `step_result` 仍然是 runtime / orchestrator 真正消费的正式结果

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
4. 当前没有接入 tool calling

## 当前执行流程

`ReActStepRunner.run_step(...)` 当前执行链路如下：

1. 接收 `ReActStepInput(step_prompt=...)`
2. 构造最小 messages：
   - system：要求输出 JSON
   - user：传入 `step_prompt`
3. 调用 `model_provider.generate(messages, tools=[], config=...)`
4. 解析模型返回 JSON
5. 组装：
   - `thought`
   - `action`
   - `observation`
   - `StepResult`
6. 返回正式 `ReActStepOutput`

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

其中：

1. `status_signal` 当前最小集合为：
   - `progressed`
   - `ready_for_completion`
   - `blocked`
   - `failed`
2. 当 `status_signal != progressed` 时，`reason` 必须非空

## 当前边界

当前这一步明确不进入：

1. tool calling
2. unified runtime memory
3. `Reflexion`
4. `Completion Evaluator`
5. 多轮 solver 循环
6. graph 全量上下文注入
7. 模型侧正式生成 `TaskGraphPatch`

这些内容会在后续模块继续落地。
