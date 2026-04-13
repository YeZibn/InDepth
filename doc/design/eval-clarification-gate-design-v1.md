# InDepth Eval Clarification Gate V1 设计稿

更新时间：2026-04-13
状态：V1 设计中（待实现）

## 1. 目标

修复评估链路中的提前触发问题：当 Agent 在执行中向用户澄清需求时，不应被当作“最终答案”直接进入评估。

V1 目标：
1. 将“澄清提问”与“终态输出”从语义上分离。
2. 保证只有终态才触发 `EvalOrchestrator.evaluate()`。
3. 明确 `run` 记录与 `task` 收口的关系，避免多轮澄清时评估中断或误收敛。
4. 保留现有事件与结果结构的兼容性，降低迁移成本。

## 2. 问题定义

当前运行时在 `finish_reason=stop` 且有文本内容时，默认将内容视为 `final_answer`，并继续触发：
1. `task_finished`
2. `verification_started`
3. `verification_passed/failed`
4. `task_judged`

风险：
1. Agent 的“请确认 xx”会被误判为任务已完成并进入评估。
2. postmortem 会沉淀错误结论，污染后续复盘与记忆。
3. 观测面中任务状态被提前收敛，影响审计准确性。

## 3.1 触发语义（run vs task）

V1 语义：
1. 评估流程入口按 `run` 触发。
2. 最终结论按 `task` 收口。

解释：
1. 每个任务在主流程上维持连续执行链，不因澄清而强制新建 run。
2. 澄清时当前 run 进入 `awaiting_user_input`（挂起），用户补充后通过 `run_resumed` 在同一 run 内继续。
3. 只有进入终态（`completed/failed`）时，才产出最终 `task_judged` 结论。

## 3. 运行时状态模型（V1）

新增运行时中间状态：
1. `running`：执行中。
2. `awaiting_user_input`：等待用户补充信息（非终态）。
3. `completed`：任务完成（终态）。
4. `failed`：任务失败（终态）。

状态约束：
1. 仅 `completed/failed` 可进入评估。
2. `awaiting_user_input` MUST NOT 触发评估链路。

## 4. 评估门禁规则

现状：`finish_reason=stop` 即收敛并评估。  
V1：由“停机原因”升级为“停机原因 + 状态门禁”双条件。

门禁逻辑：
1. 若判定为 `awaiting_user_input`：
- 输出澄清问题给用户。
- 跳过 `evaluate()`。
- 标记当前 run 为“暂停等待输入”（非终态）。
- 用户补充后在同一 run 内恢复执行（`run_resumed`）。
2. 若判定为 `completed/failed`：
- 进入最终评估（`final`）并产出任务级判定。

## 5. 澄清识别策略

采用“显式优先，启发兜底”的两层策略：

1. 显式协议（首选）
- 模型输出结构化标志（如 `needs_user_input=true` 或等价字段）。
- 运行时优先读取显式标志，避免文本猜测误判。

2. 启发兜底（仅无显式标志时）
- 基于问句与澄清意图特征（例如“请确认/请补充/你是指”）判定。
- 命中后仅进入 `awaiting_user_input`，不视为终态成功。

## 5.1 终态判定规则（Terminal State）

判定原则：显式信号优先，规则兜底；宁可延后收口，不提前误判。

优先级顺序：
1. 显式状态（最高优先级）
- `awaiting_user_input`：非终态。
- `completed`：终态成功。
- `failed`：终态失败。

2. 停机硬信号兜底（仅无显式状态时）
- `stop_reason in {length, content_filter, model_failed, max_steps_reached, tool_failed_before_stop}`：
  视为终态失败。

3. 澄清意图判定（仅无显式状态且不属于停机硬信号时）
- 命中澄清意图（缺失关键信息、明确提问用户确认）：
  视为 `awaiting_user_input`（非终态）。

4. 完成证据判定（仅无显式状态且未命中澄清意图时）
- 同时满足“无澄清意图 + 有完成证据（如产物存在/关键约束满足）”：
  可判定为 `completed`。

5. 默认回退
- 其余情况一律判定为非终态（`awaiting_user_input` 或继续 `running`），禁止提前评估收口。

## 6. 事件与可观测性

新增事件：
1. `clarification_requested`
- 记录：提问摘要、缺失信息点、来源 step。
2. `verification_skipped`
- 记录：`reason=awaiting_user_input`。
3. `user_clarification_received`
- 记录：用户对澄清问题的补充输入已到达。
4. `run_resumed`
- 记录：同一 run 从等待态恢复执行。

评估类型：
1. `intermediate`：中间轮次，仅记录证据，不产出最终结论。
2. `final`：终态轮次，产出最终判定。

事件序列约束：
1. `awaiting_user_input` 分支不得出现 `verification_started` 与 `task_judged`。
2. 恢复分支为：`user_clarification_received -> run_resumed -> ... -> 终态评估`。
3. 终态分支保持现有 `task_finished -> verification_* -> task_judged`。

## 7. 评估落盘目录规范（Task/Run 双层）

目录结构（V1）：
1. `observability-evals/<task_id>/`：任务总目录。
2. `observability-evals/<task_id>/<run_id>/`：单次运行目录。

`run` 级文件：
1. `events.jsonl`：该 run 事件流水。
2. `postmortem.md`：该 run 复盘。
3. `judgement.json`：仅终态 run 写入；`awaiting_user_input` run 不写最终判定文件。

`task` 级文件：
1. `task_summary.json`：聚合同一任务所有 run 的状态与证据索引。
2. `task_judgement.json`：仅在任务终态时写入一次，作为最终可信结论。
3. `task_judgement_history.jsonl`：保留全部 `task_judged` 历史记录（按时间顺序）。

写入约束：
1. 澄清 run：写 `run` 目录并更新 `task_summary.json`，标记 `verification_skipped`。
2. 终态 run：写 run 判定文件，并覆盖更新 `task_summary.json`、`task_judgement.json`、`task_judgement_history.jsonl`。

## 7.1 意图分层（V1.1 可选）

V1 默认不引入 `intent` 分层，先保证 `task + run` 主链路稳定。

后续（V1.1）若任务内多目标频繁出现，可再引入 `intent` 维度用于审计与聚合。

## 8. 兼容与迁移策略

1. 返回值兼容：
- V1 继续兼容现有字符串输出，避免调用方一次性改造。
2. 语义增强：
- 通过事件 payload 暴露 `runtime_state`（如 `awaiting_user_input`）。
3. 渐进演进：
- 后续版本可升级为结构化返回（`status + message + missing_fields`）。

## 9. 测试回归要求

新增最小回归集：
1. `clarification_stop_should_not_trigger_evaluation`
- 断言不发 `verification_started/task_judged`。
2. `final_answer_should_trigger_evaluation`
- 断言终态仍保持完整评估链路。
3. `postmortem_should_not_finalize_on_awaiting_user_input`
- 断言等待用户输入场景不写入终态结论。
4. `task_folder_should_aggregate_multi_runs`
- 断言同一 `task_id` 下多个 `run_id` 目录并存，且 `task_summary.json` 正确聚合。
5. `task_judgement_should_only_exist_after_terminal_run`
- 断言澄清 run 不生成 `task_judgement.json`，终态 run 才生成。
6. `explicit_state_should_override_heuristics`
- 断言显式 `awaiting_user_input/completed/failed` 优先于文本启发式。
7. `hard_stop_reason_should_be_terminal_failed`
- 断言 `length/content_filter/model_failed/max_steps_reached` 归类为终态失败。
8. `no_evidence_should_not_be_completed`
- 断言仅有“完成措辞”但无验收证据时，不得判为 `completed`。

## 10. 风险与边界

1. 仅靠启发式可能误判，必须优先推动显式协议。
2. 多轮澄清可能拉长任务周期，需要结合超时/重试策略。
3. 老数据中已存在误评估记录，V1 不做历史修复，仅保证增量正确。
4. `run` 级证据跨轮聚合时需避免重复计数（同一失败事件去重）。

## 11. 实施建议（V1）

1. 先落地状态门禁与事件补齐（低风险、高收益）。
2. 同步落地 `task/run` 双层目录与汇总文件写入规则。
3. 再引入显式澄清标志与 fallback 规则。
4. 最后补齐回归测试并在 `doc/refer/eval-reference.md` 更新事件顺序图与目录结构图。
