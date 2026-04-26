# S11-T1 Verification 输入输出关系图（V1）

更新时间：2026-04-21  
状态：Draft  
对应任务：`S11-T1`

## 1. 当前核心模块

1. `app/eval/schema.py`
2. `app/eval/orchestrator.py`
3. `app/eval/verifiers/*`
4. `app/eval/agent/verifier_agent.py`
5. `app/core/runtime/runtime_finalization.py`

## 2. 当前主链路

```text
final_answer + stop_reason + tool_failures + verification_handoff
  -> RunOutcome
  -> EvalOrchestrator.evaluate()
  -> verifier chain
  -> RunJudgement
  -> task_judged / verification_* events
```

## 3. 当前关键输入

### RunOutcome

1. `task_id`
2. `run_id`
3. `user_input`
4. `final_answer`
5. `stop_reason`
6. `tool_failures`
7. `runtime_status`
8. `verification_handoff`

### verification_handoff

当前被 verifier 重点消费：

1. `goal`
2. `constraints`
3. `claimed_done_items`
4. `expected_artifacts`
5. `key_evidence`
6. `known_gaps`
7. `rubric`
8. `soft_score_threshold`

## 4. 当前关键输出

### RunJudgement

1. `self_reported_success`
2. `verified_success`
3. `final_status`
4. `failure_type`
5. `overclaim`
6. `confidence`
7. `verifier_breakdown`

## 5. 当前问题

1. handoff 既是 closeout 产物，又是 verifier 输入
2. deterministic verifier、LLM judge、VerifierAgent 三套评估角色边界还不够清楚
3. outcome、handoff、judgement 之间还缺少更明确的正式接口分层

## 6. 对后续的直接输入

这份 IO 图直接服务：

1. `S11-T2` run outcome 结构
2. `S11-T3` handoff 结构
3. `S11-T6` finalizing / verification pipeline
