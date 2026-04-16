# Runtime 编排层与能力层边界设计稿（V1）

更新时间：2026-04-16  
状态：Implemented（已落地）

## 0. 实施结果

本边界方案已经按“runtime 保留编排、能力层归仓”的方向落地，当前实现状态如下：

1. `runtime/` 目录已承载主要编排策略模块：
   - `todo_runtime_lifecycle.py`
   - `user_preference_lifecycle.py`
   - `runtime_stop_policy.py`
   - `runtime_finalization.py`
   - `runtime_compaction_policy.py`
   - `clarification_policy.py`
   - `tool_execution.py`
   - `system_memory_lifecycle.py`
2. `memory/` 目录已承载被下沉的能力模块：
   - `recall_service.py`
   - `memory_metadata_service.py`
3. `eval/` 目录已承载 verification handoff 能力模块：
   - `verification_handoff_service.py`
4. `AgentRuntime` 仍保留薄编排入口与依赖装配，不再直接承载大段 todo / preference / stop 细节。

当前结论：

1. `runtime/` 与 `memory/`、`eval/` 的边界已基本按本文定义对齐。
2. 本文后半部分关于“下一步建议”的内容保留为历史设计记录。

## 1. 背景

当前 runtime 的结构拆分已经做了几轮，`AgentRuntime` 中较重的职责已经逐步拆到独立模块：

1. `todo_runtime_lifecycle.py`
2. `user_preference_lifecycle.py`
3. `runtime_stop_policy.py`
4. `tool_execution.py`
5. `system_memory_lifecycle.py`
6. `verification_handoff_service.py`

但这只是“从单文件里拆出来”，还没有完全回答另一个更关键的问题：

1. 哪些东西应该继续留在 `runtime/` 目录，作为编排层的一部分。
2. 哪些东西应该下沉到 `memory/`、`eval/`、`observability/` 等能力层目录。

本设计稿的目标，就是明确这条边界。

## 2. 设计原则

本次边界划分采用一条主原则：

1. 编排层放在 `runtime/` 里，并按照功能拆分。
2. 能力层回到自己的目录下，按领域聚合。

换句话说：

1. `runtime/` 负责“什么时候做、按什么阶段做、失败后怎么收敛”。
2. `memory/`、`eval/`、`observability/` 负责“能做什么、对外提供什么能力”。

## 3. 先给结论

### 3.1 `runtime/` 里应该保留什么

`runtime/` 里保留所有“与 run 生命周期强相关”的编排逻辑：

1. step loop 驱动。
2. finish reason / stop reason 收敛。
3. clarification suspend / resume。
4. todo recovery 触发时机。
5. mid-run compaction 触发时机。
6. run 开始与结束的 prepare / finalize 流程。
7. runtime 如何调用 memory / eval / obs 的顺序与时机。

这些逻辑的共同点是：

1. 它们强依赖 `task_id`、`run_id`、`runtime_state`、`stop_reason`。
2. 它们描述的是“时序与策略”，而不是底层能力本身。

### 3.2 `memory/` 里应该放什么

`memory/` 里保留所有记忆能力本身：

1. store / repository。
2. recall / search / upsert 能力。
3. memory card metadata 生成器。
4. recall rerank 能力。
5. render / normalize / transform 之类不依赖 runtime 阶段的逻辑。

一句话：

1. `memory/` 不应该知道 runtime 的 stop reason。
2. `memory/` 只应该知道如何存、如何取、如何格式化。

### 3.3 `eval/` 里应该放什么

`eval/` 里保留所有评估能力：

1. verifier agent。
2. orchestrator / judge。
3. handoff schema 与 normalization。
4. verdict / confidence / failure_type 的生成逻辑。

一句话：

1. `eval/` 负责“怎么判断”。
2. `runtime/` 负责“什么时候去判断、判断失败后怎么收敛”。

### 3.4 `observability/` 里应该放什么

`observability/` 里保留所有观测能力：

1. event schema。
2. emit / sink / storage。
3. event normalization。
4. 事件查询与导出。

一句话：

1. `observability/` 不负责决定何时 emit 哪个业务事件。
2. 它只负责接收结构化事件并把它记下来。

## 4. 边界判断标准

为了避免后面“看起来像 memory，就往 memory 里塞”，这里给出明确的判断规则。

### 4.1 应该留在 `runtime/` 的标准

满足以下任一条件，就应优先留在 `runtime/`：

1. 逻辑依赖 `runtime_state`、`stop_reason`、`task_status`。
2. 逻辑的核心是“何时触发某能力”。
3. 逻辑跨越多个能力域，比如同时动用 memory、eval、obs。
4. 逻辑本质是 run lifecycle 的阶段控制。

### 4.2 应该下沉到能力层的标准

满足以下大多数条件，就应该下沉：

1. 不依赖 runtime 阶段语义。
2. 可以被 runtime 之外复用。
3. 输入输出稳定，像一个独立能力。
4. 逻辑本质是领域能力，而不是编排策略。

## 5. 推荐的目标目录结构

建议演进到如下结构：

```text
app/core/
  runtime/
    agent_runtime.py
    runtime_prepare.py
    runtime_loop.py
    runtime_stop_policy.py
    runtime_finalization.py
    runtime_compaction_policy.py
    todo_runtime_lifecycle.py
    clarification_policy.py

  memory/
    system_memory_store.py
    user_preference_store.py
    recall_service.py
    rerank_service.py
    memory_card_metadata_service.py
    recall_rendering.py

  eval/
    orchestrator.py
    verification_handoff_service.py
    verifier_agent.py
    schema.py

  observability/
    events.py
    event_schema.py
    sinks/
```

注意：

1. `runtime/` 下面全是“如何编排”。
2. `memory/`、`eval/`、`observability/` 下面全是“提供什么能力”。

## 6. 当前模块的建议归属

### 6.1 建议继续留在 `runtime/`

这些模块虽然会调用 memory / eval / obs，但它们本质还是 runtime strategy：

1. `todo_runtime_lifecycle.py`
2. `runtime_stop_policy.py`
3. `tool_execution.py`
4. 未来的 `runtime_finalization.py`
5. 未来的 `runtime_prepare.py`
6. 未来的 `runtime_compaction_policy.py`
7. 未来的 `clarification_policy.py`

原因：

1. 它们都强依赖 run 阶段和 runtime 状态。
2. 它们本质描述的是“触发顺序、收敛策略、编排时机”。

### 6.2 建议逐步迁出 `runtime/` 的模块

以下模块里其实混了较多能力层内容，后续可以考虑继续下沉：

1. `system_memory_lifecycle.py`
2. `verification_handoff_service.py`

但不是整文件直接挪，而是拆成两层。

#### `system_memory_lifecycle.py`

建议拆成：

1. `runtime/` 保留：
   - 何时 recall
   - 何时 finalize
   - recall/finalize 在 run 里的装配顺序
2. `memory/` 下沉：
   - recall query builder
   - rerank service
   - memory card metadata service
   - recall block rendering
   - semantic title builder

也就是说，名字里带 lifecycle 的部分仍然是 runtime strategy；真正的 recall / metadata / rendering 能力应归 memory。

#### `verification_handoff_service.py`

建议拆成：

1. `runtime/` 保留：
   - 何时构建 handoff
   - 何时走 fallback rule
   - handoff 与 runtime stop 状态之间的装配关系
2. `eval/` 下沉：
   - handoff schema
   - handoff normalize
   - handoff llm generation
   - handoff config builder

也就是说，handoff 的“结构与生成”是 eval 能力；handoff 的“触发时机”是 runtime 编排。

## 7. 现有 `AgentRuntime` 里还适合继续拆什么

按这个边界原则，`AgentRuntime` 里当前最适合继续外提的有三块。

### 7.1 `runtime_finalization.py`

建议收走：

1. `awaiting_user_input` 之后的暂停收尾。
2. `task_finished` 事件发送。
3. todo recovery 兜底。
4. verification 调用与事件发射。
5. memory finalize。
6. user preference capture。
7. memory compaction / compact_final。

原因：

1. 它们都是 run 结束阶段的编排。
2. 它们跨 memory / eval / obs 多域。
3. 它们属于 runtime phase orchestration，不属于任一能力层本体。

### 7.2 `clarification_policy.py`

建议收走：

1. clarification judge prompt。
2. clarification judge config。
3. clarification llm / heuristic 判断。
4. 缺失信息 hints 提取规则。

原因：

1. 它本质是 runtime 的一个策略子域。
2. 它虽然调用模型，但不属于 memory / eval / obs。

### 7.3 `runtime_compaction_policy.py`

建议收走：

1. `_maybe_compact_mid_run(...)`
2. token usage 相关压缩阈值策略

原因：

1. 这是 runtime 对上下文预算的调度策略。
2. 不属于 memory store 本身。

## 8. 什么不要着急搬到能力层

这点很重要，避免“按目录归属强行搬家”。

以下逻辑虽然看起来像 memory / eval / obs，但暂时不建议一步到位直接搬过去：

1. run-start recall 注入时机。
2. run-end finalize 时机。
3. verifier 启动前后的事件顺序。
4. clarification 状态下跳过 verification。
5. todo recovery 对 verification_handoff 的覆盖。

原因：

1. 这些都依赖 runtime 状态机。
2. 直接搬到能力层，会把能力层反向耦合到 runtime protocol。

## 9. 推荐的迁移路径

为了避免一边搬目录一边改语义，建议分两阶段。

### 阶段一：先把 `AgentRuntime` 变成纯编排器

目标：

1. 所有 runtime strategy 都先从 `AgentRuntime` 本体拆出去。
2. 但仍保留在 `runtime/` 目录下。

这一步完成后的结果：

1. `AgentRuntime` 很薄。
2. runtime 目录内部分工明确。
3. 每块 strategy 都有稳定入口。

### 阶段二：再把“能力部分”从 runtime strategy 中下沉

等第一步稳定后，再对以下模块做“能力抽离”：

1. `system_memory_lifecycle.py` 中的 memory service 部分下沉到 `memory/`
2. `verification_handoff_service.py` 中承载 handoff generation / normalize 能力
3. 事件 schema / normalization 若还混在 runtime 附近，则继续下沉到 `observability/`

这样做的好处：

1. 迁移对象已经是稳定模块，而不是半成品。
2. 依赖方向更容易看清。
3. 回归风险更低。

## 10. 推荐的最终依赖方向

建议最终遵循以下依赖方向：

```text
runtime  -> memory
runtime  -> eval
runtime  -> observability

eval     -> model
memory   -> model
observability -> (no runtime dependency)
```

明确禁止：

```text
memory -> runtime
eval -> runtime
observability -> runtime
```

也就是说：

1. runtime 可以调用能力层。
2. 能力层不能反过来知道 runtime 状态机。

## 11. 中文注释策略

既然你希望 runtime 是编排层，那中文注释也应该跟着边界走。

### 11.1 runtime 层的注释重点

runtime 层的中文注释主要解释：

1. 为什么这个阶段在这里触发。
2. 为什么这个能力在这个时点被调用。
3. 为什么某些状态会跳过后续流程。

### 11.2 能力层的注释重点

能力层的中文注释主要解释：

1. 输入输出契约。
2. 归一化规则。
3. 关键阈值与约束。

也就是说：

1. runtime 注释解释“时机与流程”。
2. memory/eval/obs 注释解释“能力与规则”。

## 12. 建议的下一步

按这份设计稿，当时建议不要立刻搬 `system_memory_lifecycle.py` 和 `verification_handoff.py` 到别的目录。

更稳的顺序是：

1. 先补 `runtime_finalization.py`
2. 再补 `clarification_policy.py`
3. 再补 `runtime_compaction_policy.py`
4. 等 `AgentRuntime` 足够薄后，再做第二轮“能力下沉”

## 13. 一句话总结

这个方案的核心不是“按名字搬目录”，而是先把问题拆成两层：

1. `runtime/` 只保留编排层，按功能拆分。
2. `memory/`、`eval/`、`observability/` 只保留能力层，按领域聚合。

先把编排层做薄，再把能力层归仓，结构才会真正稳定。
