# AgentRuntime 二次结构拆分方案（V2）

更新时间：2026-04-16  
状态：Implemented（已落地）

## 0. 实施结果

本方案对应的结构拆分已经完成，当前代码状态与本文最初提案相比有以下结果：

1. `app/core/runtime/agent_runtime.py` 已收缩到约 `785` 行，主循环保留编排骨架。
2. `todo` 生命周期已拆到 `app/core/runtime/todo_runtime_lifecycle.py`。
3. 用户偏好生命周期已拆到 `app/core/runtime/user_preference_lifecycle.py`。
4. stop policy 已拆到 `app/core/runtime/runtime_stop_policy.py`。
5. run 结束收尾已拆到 `app/core/runtime/runtime_finalization.py`。
6. mid-run / final compaction 策略已拆到 `app/core/runtime/runtime_compaction_policy.py`。
7. clarification 判定已拆到 `app/core/runtime/clarification_policy.py`。
8. memory metadata / recall 能力已分别下沉到：
   - `app/core/memory/memory_metadata_service.py`
   - `app/core/memory/recall_service.py`
9. verification handoff 已由主链路 finalizing 在 `app/core/runtime/agent_runtime.py` 中直接产出并提取。

验证状态：

1. 全量 `unittest discover` 已通过。
2. SQLite 连接未关闭导致的 `ResourceWarning` 已修复。

## 1. 背景

`app/core/runtime/agent_runtime.py` 第一轮拆分已经完成了四件事：

1. `runtime_utils.py` 下沉纯工具函数。
2. `verification_handoff.py` 下沉验证交接逻辑。
3. `system_memory_lifecycle.py` 下沉 system memory 生命周期逻辑。
4. `tool_execution.py` 下沉 tool execution 闭环。

但当前 `app/core/runtime/agent_runtime.py` 仍有约 `1778` 行，且还保留了几块较重的策略职责：

1. `todo` 上下文跟踪与失败恢复。
2. user preference recall / extract / apply。
3. stop reason 判定与 runtime state 收敛。
4. `run()` 内部状态推进逻辑仍然偏长，阅读主流程时需要不断跳进细节。

这意味着 V1 解决了“最粗颗粒的拆分”，但还没有真正把 `AgentRuntime` 收缩成“编排器”。

## 2. 这次拆分的目标

本轮目标不是继续做大而全的架构升级，而是把剩下最重、最影响阅读和扩展的三块职责彻底拆出来：

1. 让 `AgentRuntime` 主要负责主循环编排，不再承担大段策略细节。
2. 让 todo recovery、user preference、stop policy 变成独立可测模块。
3. 为后续扩展新策略时，提供稳定挂载点，避免所有逻辑继续堆回 `agent_runtime.py`。
4. 在关键入口和关键策略点补充中文注释，降低后续维护成本。

## 3. 非目标

这次先不做以下事情：

1. 不改 `AgentRuntime.run(...)` 对外接口。
2. 不改现有 `event_type`、`runtime_state`、`stop_reason` 的对外语义。
3. 不一次性把所有 runtime helper 改成 class-based service。
4. 不先做行为优化，只做结构重组与注释补强。

## 4. 当前问题分布

### 4.1 Todo recovery 已经像一个独立子系统

当前以下逻辑都还在 `AgentRuntime` 内：

1. `_update_active_todo_context(...)`
2. `_tool_requires_todo_binding(...)`
3. `_maybe_emit_todo_binding_warning(...)`
4. `_build_orphan_todo_recovery(...)`
5. `_build_runtime_fallback_record(...)`
6. `_auto_manage_todo_recovery(...)`
7. `_append_recovery_summary_for_user(...)`

问题：

1. 主循环里只想知道“失败后是否触发恢复”，却要依赖 todo 的内部状态机细节。
2. `tool execution` 已经拆出去了，但 todo 状态推进仍留在 runtime 本体里，边界不一致。
3. 未来如果接入更复杂的 recovery policy，会继续把 `AgentRuntime` 撑大。

### 4.2 User preference lifecycle 也已经形成完整闭环

当前以下逻辑都还在 `AgentRuntime` 内：

1. `_inject_user_preference_recall(...)`
2. `_capture_user_preferences(...)`
3. `_extract_user_preferences_llm(...)`
4. `_normalize_preference_value(...)`
5. `_is_sensitive_preference_value(...)`
6. `_value_changed(...)`
7. `_apply_user_preference_updates(...)`

问题：

1. 它本质上和 `system_memory_lifecycle.py` 的模式相同，都是“run 前 recall、run 后 capture”。
2. 现在 mixed 在 runtime 本体里，会让阅读者误以为它是主循环不可分离的一部分。
3. 用户偏好是未来高频迭代点，继续放在 runtime 里会提高回归风险。

### 4.3 Stop policy 仍嵌在 `run()` 里

当前 `run()` 内部直接处理：

1. `finish_reason == tool_calls`
2. `finish_reason == stop`
3. clarification request 判定
4. empty stop content 兜底
5. `length` / `content_filter` / fallback content
6. max steps reached

问题：

1. 主循环在做“状态推进”和“停止策略”两类事情。
2. stop policy 很难单独验证。
3. 后续一旦新增 stop 条件，`run()` 会继续膨胀。

## 5. 建议的目标结构

建议在 `app/core/runtime/` 下继续拆出以下模块：

### 5.1 `todo_runtime_lifecycle.py`

职责：

1. 管理 active todo context。
2. 负责 todo binding guard。
3. 负责 fallback record / recovery decision 生成与自动追加 follow-up subtasks。
4. 负责将 recovery 摘要追加到最终用户输出。

建议导出能力：

1. `update_active_todo_context(...)`
2. `maybe_emit_todo_binding_warning(...)`
3. `auto_manage_todo_recovery(...)`
4. `append_recovery_summary_for_user(...)`

### 5.2 `user_preference_lifecycle.py`

职责：

1. 负责用户偏好 recall 注入。
2. 负责偏好抽取。
3. 负责偏好更新应用与敏感信息拦截。

建议导出能力：

1. `inject_user_preference_recall(...)`
2. `capture_user_preferences(...)`
3. `extract_user_preferences_llm(...)`
4. `apply_user_preference_updates(...)`

### 5.3 `runtime_stop_policy.py`

职责：

1. 对模型输出做 stop reason 判定。
2. 统一返回 runtime state、stop reason、final answer。
3. 处理 clarification request 识别与 stop/fail 的归一化收敛。

建议导出能力：

1. `resolve_model_step_outcome(...)`
2. `resolve_max_steps_outcome(...)`

### 5.4 可选：`runtime_types.py`

如果后续参数开始增多，建议增加轻量 dataclass，避免函数参数继续膨胀：

1. `RuntimeDeps`
2. `RunContext`
3. `StepOutcome`
4. `TodoRecoveryResult`

注意：

1. V2 不强制上 dataclass。
2. 只有当参数数量明显开始失控时再引入。

## 6. 职责边界建议

### 6.1 `AgentRuntime` 保留什么

`AgentRuntime` 建议只保留以下职责：

1. 初始化依赖与 runtime 配置。
2. 准备 messages / tools / run-level 状态。
3. 驱动 step loop。
4. 调用各 lifecycle / policy 模块。
5. 在 run 结束时统一做 verification、memory finalize、message compact。

### 6.2 `AgentRuntime` 不再直接负责什么

建议不再让它直接持有这些策略实现细节：

1. todo 恢复规则。
2. user preference 规则。
3. finish_reason 分支细节。
4. 各类 normalize / guard / sensitive 判断。

## 7. 推荐的拆分顺序

### Phase A：拆 `todo_runtime_lifecycle.py`

优先级最高，原因：

1. 代码块集中。
2. 与主循环语义耦合弱，但体量大。
3. 测试已经较集中，回归验证成本可控。

迁移目标：

1. `_update_active_todo_context(...)`
2. `_tool_requires_todo_binding(...)`
3. `_maybe_emit_todo_binding_warning(...)`
4. `_build_orphan_todo_recovery(...)`
5. `_build_runtime_fallback_record(...)`
6. `_auto_manage_todo_recovery(...)`
7. `_append_recovery_summary_for_user(...)`

### Phase B：拆 `user_preference_lifecycle.py`

优先级第二，原因：

1. 逻辑已成闭环。
2. 与 `system_memory_lifecycle.py` 的抽象模型一致。
3. 单测覆盖面已经存在。

迁移目标：

1. `_inject_user_preference_recall(...)`
2. `_capture_user_preferences(...)`
3. `_extract_user_preferences_llm(...)`
4. `_normalize_preference_value(...)`
5. `_is_sensitive_preference_value(...)`
6. `_value_changed(...)`
7. `_apply_user_preference_updates(...)`
8. `_build_user_preference_extract_config(...)`

### Phase C：拆 `runtime_stop_policy.py`

优先级第三，原因：

1. 会直接影响 `run()` 的可读性。
2. 但 stop policy 与主循环交界最紧，需要在前两步稳定后再抽。

迁移目标：

1. `finish_reason == stop` 的结果判定。
2. clarification judge 结果整合。
3. `length` / `content_filter` / fallback content 判定。
4. `max_steps_reached` 判定。

### Phase D：收敛 `run()` 骨架

目标：

1. 让 `run()` 主体按“准备 -> 循环 -> 收尾”三段结构收敛。
2. 将内部临时变量整理为少量明确状态对象。
3. 清理掉已经被模块化后的私有 helper。

## 8. 中文注释策略

你提到希望把重点地方中文注释一下，我建议不是“到处写注释”，而是只在关键骨架和关键策略点写，避免注释噪音。

### 8.1 必须加中文注释的位置

建议至少补这几类：

1. `AgentRuntime.run(...)`
说明该方法是 runtime 的主编排入口，分哪几个阶段推进。

2. step loop 内的几个关键分支
例如：
- 为什么 `tool_calls` 分支只做工具执行，不做停止收敛。
- 为什么 `awaiting_user_input` 要跳过 verification。
- 为什么 `task_finished` 事件要在 verifier 前发出。

3. todo recovery 入口
说明什么时候认为是 orphan failure，什么时候认为可以自动恢复。

4. user preference apply 入口
说明为什么要双门槛：`auto_write_min_confidence` 与 `conflict_min_confidence`。

5. stop policy 入口
说明 stop reason、runtime state、final answer 三者是如何统一收敛的。

### 8.2 注释粒度建议

建议用“段落注释”，不要写成逐行翻译。

好的中文注释应该解释：

1. 这段逻辑为什么存在。
2. 这里最重要的约束是什么。
3. 哪些行为不能轻易改。

不建议注释：

1. 显而易见的变量赋值。
2. 函数名本身已经说清楚的事情。
3. 和代码重复的描述。

### 8.3 注释示例

示例一：主循环

```python
# Runtime 主循环只负责“编排”，不直接承载策略细节。
# 每个 step 只做三件事：向模型请求、处理工具调用、或收敛本轮输出。
for step in range(1, self.max_steps + 1):
    ...
```

示例二：awaiting user input

```python
# 一旦模型明确进入“等待用户补充信息”状态，本轮 run 视为暂停而非失败。
# 此时不能进入 verification，否则会把“合理暂停”误判成“任务未完成”。
if runtime_state == "awaiting_user_input":
    ...
```

示例三：todo 自动恢复

```python
# 只有当 runtime 已绑定到具体 subtask 时，才能自动写入 fallback 并规划恢复。
# 如果没有绑定 subtask，则只能生成 orphan recovery，交回主 agent 决策。
if subtask_number is None:
    ...
```

## 9. 推荐的注释落点

建议首轮先补这些位置：

1. `app/core/runtime/agent_runtime.py`
2. `app/core/runtime/todo_runtime_lifecycle.py`
3. `app/core/runtime/user_preference_lifecycle.py`
4. `app/core/runtime/runtime_stop_policy.py`

如果暂时还没拆出新模块，那么先在现有这些函数上补中文注释：

1. `_auto_manage_todo_recovery(...)`
2. `_capture_user_preferences(...)`
3. `_apply_user_preference_updates(...)`
4. `_judge_clarification_request(...)`
5. `run(...)`

## 10. 验收标准

结构层面：

1. `agent_runtime.py` 行数下降到 `900` 行以内。
2. `run()` 的主干逻辑可以在单屏范围内读懂主要阶段。
3. todo / preference / stop policy 都有独立模块和对应测试。

行为层面：

1. clarification suspend / resume 行为不变。
2. todo recovery 输出和 event 链路不回归。
3. user preference recall / capture 行为不变。
4. verification 与 task_finished 事件顺序不变。

可维护性层面：

1. 关键骨架有中文注释。
2. 新增策略时优先扩展子模块，而不是继续向 `AgentRuntime` 塞逻辑。

## 11. 实施建议

建议按以下顺序落地：

1. 先新增设计文档并确认边界。
2. 先拆 `todo_runtime_lifecycle.py`，同时补中文注释。
3. 再拆 `user_preference_lifecycle.py`。
4. 最后抽 `runtime_stop_policy.py` 并收敛 `run()`。
5. 每一步都跑对应测试，不做跨阶段大改。

## 12. 我建议你现在就这么做

如果按“风险最低、收益最大”的原则推进，我建议下一步直接进入：

1. Phase A：拆 `todo_runtime_lifecycle.py`
2. 在 `run()`、todo recovery 入口、awaiting user input 分支补中文注释

原因：

1. 这块体量最大。
2. 影响主流程阅读最明显。
3. 拆完后你会立刻感觉 `AgentRuntime` 清爽一截。
