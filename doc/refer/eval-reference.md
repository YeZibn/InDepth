# InDepth Eval 参考

更新时间：2026-04-15

## 1. 目标

Eval 层用于把"模型回答完成"与"任务完成"分离，输出可追踪的结构化判定。

核心问题：
- 如何区分"回答完成"和"任务完成"？
- 如何让执行结果可审计？

相关代码：
- `app/eval/schema.py` - 数据模型
- `app/eval/orchestrator.py` - 评估协调器
- `app/eval/verifiers/*` - 验证器实现
- `app/eval/agent/verifier_agent.py` - LLM 判官

## 2. 架构图

### 2.1 评估模块架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          评估模块架构                                     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      AgentRuntime                                  │   │
│  │                      (run 结束时调用)                               │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   EvalOrchestrator                                │   │
│  │                                                                  │   │
│  │  evaluate(run_outcome) ──▶ RunJudgement                        │   │
│  │         │                                                       │   │
│  │         ▼                                                       │   │
│  │  ┌─────────────────────────────────────────────────────────┐   │   │
│  │  │              Verifier 链路 (有序执行)                       │   │   │
│  │  │                                                          │   │   │
│  │  │  ┌────────────────┐   ┌────────────────┐   ┌─────────┐ │   │   │
│  │  │  │StopReason      │   │ToolFailure     │   │LLM      │ │   │   │
│  │  │  │Verifier        │   │Verifier        │   │Judge    │ │   │   │
│  │  │  │(hard)          │   │(hard)          │   │Verifier │ │   │   │
│  │  │  └───────┬────────┘   └───────┬────────┘   │(soft)   │ │   │   │
│  │  │          │                    │            └────┬────┘ │   │   │
│  │  │          └────────────────────┼────────────────┘      │   │   │
│  │  │                               ▼                        │   │   │
│  │  │                    ┌─────────────────┐               │   │   │
│  │  │                    │ 收集 VerifierResult              │   │   │
│  │  │                    └─────────────────┘               │   │   │
│  │  └─────────────────────────────────────────────────────────┘   │   │
│  │                           │                                    │   │
│  │                           ▼                                    │   │
│  │  ┌─────────────────────────────────────────────────────────┐   │   │
│  │  │                   判定逻辑                                │   │   │
│  │  │                                                          │   │   │
│  │  │  硬失败优先:                                             │   │   │
│  │  │    hard=true && passed=false ──▶ fail                   │   │   │
│  │  │                                                          │   │   │
│  │  │  软检查:                                                 │   │   │
│  │  │    avg(score) < threshold ──▶ partial                   │   │   │
│  │  │    avg(score) >= threshold ──▶ pass                     │   │   │
│  │  └─────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                │                                        │
│                                ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      RunJudgement                                │   │
│  │  - self_reported_success                                       │   │
│  │  - verified_success                                            │   │
│  │  - final_status: pass / partial / fail                         │   │
│  │  - failure_type                                                │   │
│  │  - verifier_breakdown[]                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 判定流程

```
AgentRuntime.run() 结束
         │
         ▼
emit_event(task_finished)
         │
         ▼
EvalOrchestrator.evaluate(run_outcome)
         │
         ├──▶ build_default_deterministic_verifiers()
         │       │
         │       ├──▶ StopReasonVerifier (hard)
         │       └──▶ ToolFailureVerifier (hard)
         │
         ├──▶ 顺序执行每个 verifier
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  硬失败检查 (任一触发即 fail)                                   │
│                                                               │
│  for result in verifier_results:                              │
│      if result.hard and not result.passed:                   │
│          final_status = "fail"                                │
│          break                                                │
└─────────────────────────────────────────────────────────────┘
         │
         ├─── fail ──▶ 记录 failure_type
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  软评分检查                                                   │
│                                                               │
│  soft_results = [r for r in results if not r.hard]           │
│  if soft_results:                                             │
│      avg_score = sum(r.score for r in soft_results) / len()   │
│      if avg_score < run_outcome.verification_handoff.soft_score_threshold: │
│          final_status = "partial"                             │
│      else:                                                    │
│          final_status = "pass"                                │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
emit_event(task_judged, payload=RunJudgement)
```

## 3. 数据模型

### 3.1 VerificationHandoff

```python
verification_handoff = {
    "goal": "string",
    "constraints": ["string"],
    "expected_artifacts": [
        {"path": "string", "must_exist": True, "non_empty": False, "contains": "optional"}
    ],
    "claimed_done_items": ["string"],
    "key_tool_results": [{"tool": "string", "status": "ok|error", "summary": "string"}],
    "known_gaps": ["string"],
    "self_confidence": 0.8,
    "soft_score_threshold": 0.7,
    "rubric": "string",
}
```

### 3.2 RunOutcome

```python
@dataclass
class RunOutcome:
    task_id: str
    run_id: str
    user_input: str
    final_answer: str
    stop_reason: str                         # stop/length/model_failed/...
    tool_failures: List[Dict[str, str]]     # [{name, error}]
    runtime_status: str                     # ok/error
    verification_handoff: Dict[str, Any]   # 评估交接信息
```

### 3.3 RunJudgement

```python
@dataclass
class RunJudgement:
    self_reported_success: bool              # 自我报告成功
    verified_success: bool                  # 验证成功
    final_status: str                       # pass/partial/fail
    failure_type: Optional[str]             # 失败类型
    overclaim: bool                         # 过度声明
    confidence: float                       # 置信度
    verifier_breakdown: List[VerifierResult]  # 各验证器结果
```

### 3.4 VerifierResult

```python
@dataclass
class VerifierResult:
    verifier_name: str
    passed: bool
    score: Optional[float]                 # 0.0-1.0
    hard: bool                             # 是否硬检查
    reason: str                            # 通过/失败原因
    details: Optional[Dict] = None
```

## 4. 判定逻辑详解

### 4.1 self_reported_success 推断

`infer_self_reported_success()` 规则：

```
1. stop_reason 在异常集合时
   └── return False
      异常集合: length, model_failed, content_filter, tool_failed_before_stop

2. final_answer 命中负向关键词
   └── return False
   关键词: 未完成、失败、error、无法、无效

3. final_answer 命中正向关键词
   └── return True
   关键词: 已完成、done、success、成功、解决

4. 其他情况
   └── 根据 stop_reason 判断
       - stop + 有内容: True
       - 其他: False
```

### 4.2 硬检查 (Deterministic Verifiers)

**StopReasonVerifier**：
```python
# 硬失败条件
if stop_reason in {
    "length",
    "model_failed",
    "content_filter",
    "tool_failed_before_stop",
    "max_steps_reached"
}:
    passed = False
else:
    passed = True
```

**ToolFailureVerifier**：
```python
# 硬失败条件
if any(failure for tool_failures):
    passed = False
else:
    passed = True
```

### 4.3 软检查 (LLM Judge)

```python
class LLMJudgeVerifier(BaseVerifier):
    hard = False
    score = None  # 来自 VerifierAgent 输出

    def verify(self, run_outcome) -> VerifierResult:
        # 1. 构建 VerifierAgent
        # 2. 执行 LLM 评判
        # 3. 解析 JSON 输出: {passed, score, reason, checks}
        # 4. 异常时 fail-open: passed=True, score=None, confidence=0.2
```

## 5. VerifierAgent

### 5.1 定位

`VerifierAgent` 是独立的 LLM 验证 Agent，内置只读工具，专门用于复杂的任务验证：

```python
class VerifierAgent:
    def __init__(self, provider, config):
        self.provider = provider
        self.config = config
        self.tools = [
            list_work_files,    # 列出工作文件
            read_project_file,  # 读取项目文件
        ]
```

### 5.2 证据根目录推断

```
1. verification_handoff.expected_artifacts 中指定的路径
2. observability-evals/<task_id>__<run_id>
3. observability-evals/<task_id>（当 run_id==task_id 或无 run_id）
4. 历史 work/ 目录
```

### 5.3 输出要求

VerifierAgent 必须输出严格 JSON：

```json
{
  "passed": true,
  "score": 0.85,
  "reason": "任务按要求完成，所有工件已生成",
  "checks": [
    {"name": "文件存在性", "passed": true},
    {"name": "代码质量", "passed": true, "detail": "通过 lint"},
    {"name": "功能正确性", "passed": false, "detail": "测试用例 3 失败"}
  ]
}
```

### 5.4 安全约束

- 禁止路径穿越（如 `/etc/passwd`）
- 只允许读取 project root 下的文件

## 6. Runtime 集成

### 6.1 事件顺序

```
AgentRuntime.run() 结束
         │
         ▼
若 runtime_state=awaiting_user_input
         │
         ├──▶ emit_event(verification_skipped)
         │
         └──▶ 返回澄清问题（不触发 task_judged）
         
否则（终态 completed/failed）
         │
         ▼
emit_event(task_finished)
         │  <- 此时 payload 只有 runtime 信息，无验证结果
         ▼
EvalOrchestrator.evaluate()
         │
         ▼
emit_event(verification_started)
        │  <- payload 包含 handoff_source: llm|fallback_rule
        │
        ▼
emit_event(verification_passed / verification_failed)
        │
        ▼
emit_event(task_judged)
        │  <- 最终判定，以此时 payload 为准，含 verification_handoff_source 与 verification_handoff
         ▼
postmortem 生成（覆盖写）
```

### 6.2 postmortem 时机

- `task_finished`：先生成初版（给 VerifierAgent 提供同 run 证据）
- `task_judged`：评估后覆盖写最终版
- `verification_skipped`：澄清等待阶段也会生成 run 级复盘（无最终判定）

## 7. 扩展指南

### 7.1 添加自定义 Verifier

```python
class CustomVerifier(BaseVerifier):
    hard = False  # 或 True

    def verify(self, run_outcome) -> VerifierResult:
        # 自定义验证逻辑
        passed = ...
        score = ...
        return VerifierResult(
            verifier_name="custom",
            passed=passed,
            score=score,
            hard=self.hard,
            reason="..."
        )
```

### 7.2 注册到默认链路

修改 `build_default_deterministic_verifiers()`：

```python
def build_default_deterministic_verifiers():
    return [
        StopReasonVerifier(),
        ToolFailureVerifier(),
        # 添加自定义
        CustomVerifier(),
    ]
```

## 8. 测试映射

| 测试文件 | 覆盖内容 |
|---------|---------|
| `tests/test_eval_orchestrator.py` | 判定逻辑、硬失败、软评分 |
| `tests/test_verifier_agent.py` | LLM Judge、输出解析 |
| `tests/test_runtime_eval_integration.py` | Runtime 集成、事件顺序 |
| `tests/test_self_reported_success.py` | 自我报告推断 |

## 9. Postmortem 交付内容映射

生成时机说明：
- `verification_handoff` 优先在 step 终态时构建（非 `awaiting_user_input`）。
- 循环外评估前仍保留一次兜底生成。

postmortem 会从 `task_judged.payload.verification_handoff` 渲染“交付内容”区块，重点展示：
- `claimed_done_items`
- `expected_artifacts`
- `known_gaps`
- `verification_handoff_source`
