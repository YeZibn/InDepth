# Prompting 实现说明

## 文档定位

本文记录 `runtime-v2` 当前 prompt 模块的实际落地情况、代码入口与当前边界。

它对应的是已经完成的模块 16，而不是 `design/` 下的 prompt 设计决策原文。

## 当前代码入口

当前 prompt 模块代码位于：

1. [models.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/prompting/models.py)
2. [assembler.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/prompting/assembler.py)
3. [__init__.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/prompting/__init__.py)

主链接线入口位于：

1. [runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/orchestrator/runtime_orchestrator.py)
2. [react_step.py](/Users/yezibin/Project/InDepth/runtime-v2/src/rtv2/solver/react_step.py)

## 当前正式结构

当前 prompt 模块正式采用三层结构：

1. `base_prompt`
2. `phase_prompt`
3. `dynamic_injection`

对应输出模型：

1. `ExecutionPrompt`

对应输入模型：

1. `ExecutionPromptInput`
2. `ExecutionNodePromptContext`

## 当前责任链

当前主链中的 prompt 责任划分如下：

1. `RuntimeOrchestrator` 负责读取：
   - `RunContext`
   - 当前 `TaskGraphNode`
   - `RuntimeMemoryProcessor`
   - `ToolRegistry`
2. `RuntimeOrchestrator` 负责整理：
   - `ExecutionNodePromptContext`
   - `ExecutionPromptInput`
3. `ExecutionPromptAssembler` 负责装配：
   - `ExecutionPrompt`
4. `RuntimeOrchestrator` 当前再把三段 prompt block 渲染为单个 `step_prompt` 字符串
5. `ReActStepRunner` 继续消费该 `step_prompt` 字符串

这意味着：

1. prompt 模块本身不直接读取整个状态树
2. prompt 模块不直接依赖 `RuntimeMemoryProcessor`
3. prompt 模块不负责 tool 执行、graph 推进或 recall 决策

## 当前输入来源

### `base_prompt`

当前由 `ExecutionPromptAssembler` 内部直接给出最小稳定文本。

它主要表达：

1. 主执行器身份
2. 真实性要求
3. 当前 node 导向
4. 工具使用总原则

### `phase_prompt`

当前由 `ExecutionPromptAssembler` 根据 `RunPhase` 生成。

现状如下：

1. `EXECUTE` 已有正式最小文本
2. `PREPARE` 仍为占位 stub
3. `FINALIZE` 仍为占位 stub

### `dynamic_injection`

当前由 orchestrator 先整理输入，再交给 assembler 渲染。

第一版已接入：

1. `user_input`
2. `goal`
3. 当前 node 的 id / name / description / status
4. 依赖节点轻量摘要
5. `artifacts`
6. `evidence`
7. `notes`
8. `runtime_memory_text`
9. `tool_capability_text`
10. `finalize_return_input`

其中：

1. `runtime_memory_text` 来自 `RuntimeMemoryProcessor.build_prompt_context_text(...)`
2. `tool_capability_text` 由 orchestrator 基于 `ToolRegistry` 生成最小摘要
3. 依赖节点当前只生成轻量摘要，不引入详细正文

## 当前实现边界

当前 prompt 模块已经正式落地，但仍保持轻量。

已经完成：

1. 正式输入输出模型
2. 三层 assembler 骨架
3. runtime memory / node / tool capability 的主链接入
4. orchestrator 对 prompt 模块的正式消费
5. `ReActStepRunner` 对渲染后 `step_prompt` 的正式消费口径

尚未完成：

1. `PREPARE / FINALIZE` 的正式 prompt 文本
2. evaluator / reflexion / replan 的 prompt 模块
3. message 级 prompt 输入
4. context budget / compression 感知下的 prompt 裁剪

## 当前测试

当前已覆盖的测试包括：

1. [test_prompting.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_prompting.py)
2. [test_runtime_orchestrator.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_runtime_orchestrator.py)
3. [test_react_step.py](/Users/yezibin/Project/InDepth/runtime-v2/tests/test_react_step.py)

主要覆盖：

1. 三段 prompt block 生成
2. 空字段渲染
3. `PREPARE / FINALIZE` stub 行为
4. orchestrator 主链接入
5. runner 消费渲染后 `step_prompt`
