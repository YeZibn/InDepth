# InDepth Eval 参考

更新时间：2026-04-17

## 1. 这层在解决什么问题

Eval 层的职责不是“再让模型回答一次”，而是把 Runtime 主链路结束后的结果整理成一个可审计的判断：

1. 这次运行是不是看起来“完成了”？
2. 这次完成是模型自己声称的，还是经过验证支持的？
3. 如果没有真正完成，失败是硬失败，还是部分完成？
4. 后续复盘时，能不能看出判定依据是什么？

换句话说，Eval 层负责把“主执行链路的产出”转成“结构化结论”。

相关代码：
- `app/eval/schema.py`
- `app/eval/orchestrator.py`
- `app/eval/verification_handoff_service.py`
- `app/eval/verifiers/deterministic.py`
- `app/eval/verifiers/llm_judge.py`
- `app/eval/agent/verifier_agent.py`

## 2. 整体流程

### 2.1 一段话先讲完整流程

当 `AgentRuntime.run()` 结束时，系统先拿到这次运行的事实材料：用户输入、最终回答、`stop_reason`、工具失败列表、运行状态，以及一份 `verification_handoff`。然后 `EvalOrchestrator` 用这些材料构造 `RunOutcome`，依次交给一组 verifier。前面的 deterministic verifier 先判断“运行过程本身是否健康”，比如是否正常收敛、是否存在工具失败；如果这些硬检查已经失败，最终结论就会直接进入 `fail`。如果硬检查通过，后面的 LLM verifier 才继续判断“这次结果是否真的完成了用户目标”，并给出一个软评分。最后 `EvalOrchestrator` 把这些 verifier 结果汇总成 `RunJudgement`，写出 `pass / partial / fail`、失败类型、是否 overclaim、整体置信度，以及每个 verifier 的明细。

### 2.2 分阶段流程

```
Runtime 主链路结束
    │
    ├── 1. 收集运行事实
    │      - user_input
    │      - final_answer
    │      - stop_reason
    │      - runtime_status
    │      - tool_failures
    │      - verification_handoff
    │
    ├── 2. 组装 RunOutcome
    │
    ├── 3. EvalOrchestrator 构建 verifier 链
    │      - deterministic verifiers
    │      - 可选 verifier agent judge
    │
    ├── 4. 顺序执行 verifier
    │      - 每个 verifier 输出 VerifierResult
    │
    ├── 5. 汇总判定
    │      - 先看 hard failure
    │      - 再看 soft score
    │      - 再推断 overclaim / confidence
    │
    └── 6. 产出 RunJudgement
           - self_reported_success
           - verified_success
           - final_status
           - failure_type
           - overclaim
           - confidence
           - verifier_breakdown
```

### 2.3 用文字拆开每一步

#### 第一步：收集运行事实

主执行链路在结束时已经知道很多“客观事实”：

1. 用户原始请求是什么。
2. 最终回答写了什么。
3. Runtime 是正常 `stop`，还是因为 `length`、`model_failed`、`max_steps_reached` 等原因结束。
4. 中途有没有工具失败。
5. Runtime 自己的状态是 `ok` 还是 `error`。
6. 交给评估侧的 `verification_handoff` 是什么。

Eval 层不自己重新推断这些事实，而是消费它们。

#### 第二步：组装 `RunOutcome`

这些事实会被整理成一个统一的输入对象 `RunOutcome`。之后所有 verifier 都只看这一个对象，不直接耦合 Runtime 内部状态。

#### 第三步：构建 verifier 链

`EvalOrchestrator` 会先准备一条 verifier 链。当前默认链路分两层：

1. deterministic verifiers
   - 判断“运行过程是否健康”
   - 这类检查是硬检查
2. optional LLM judge
   - 判断“结果是否真完成”
   - 这类检查是软检查

当前默认 deterministic verifier 有两个：

1. `StopReasonVerifier`
2. `ToolFailureVerifier`

如果启用了 LLM judge，并且传入了 `llm_judge_provider`，链路末尾还会加上：

1. `LLMJudgeVerifier`

#### 第四步：顺序执行 verifier

每个 verifier 都会读取 `RunOutcome`，返回一个 `VerifierResult`。

`VerifierResult` 统一描述：

1. 这个 verifier 叫什么。
2. 它是否通过。
3. 它是硬检查还是软检查。
4. 如果是软检查，分数是多少。
5. 理由是什么。
6. 它附带了哪些证据。

这一层的好处是：无论后面加多少 verifier，`EvalOrchestrator` 汇总时都不需要知道每个 verifier 的细节实现。

#### 第五步：汇总最终判定

`EvalOrchestrator` 的汇总逻辑很明确，顺序也很重要：

1. 先看所有硬检查里有没有失败。
   - 只要有任意一个 `hard=True` 且 `passed=False`，最终结果直接是 `fail`。
   - 这一步优先级最高。
2. 如果硬检查都通过，再看软检查分数。
   - 当前会取所有软检查里 `score` 非空的结果求平均。
   - 如果平均分低于 `verification_handoff.soft_score_threshold`，最终结果是 `partial`。
   - 否则是 `pass`。
3. 再根据最终结果补充衍生字段。
   - `self_reported_success`
   - `verified_success`
   - `overclaim`
   - `confidence`

#### 第六步：输出 `RunJudgement`

最终产出的 `RunJudgement` 是 Eval 层的正式结论。后续观测、复盘、分析都应该基于它，而不是再去猜 Runtime 当时发生了什么。

## 3. 核心数据模型

### 3.1 `RunOutcome`

`RunOutcome` 是 Eval 的输入。

```python
@dataclass
class RunOutcome:
    task_id: str
    run_id: str
    user_input: str
    final_answer: str
    stop_reason: str
    tool_failures: List[Dict[str, str]] = field(default_factory=list)
    runtime_status: str = "ok"
    verification_handoff: Dict[str, Any] = field(default_factory=dict)
```

字段理解：

1. `task_id` / `run_id`
   - 标识这次运行是谁。
2. `user_input`
   - 用户原始目标。
3. `final_answer`
   - Runtime 输出给用户的最终文本。
4. `stop_reason`
   - 这次 run 是怎么结束的。
5. `tool_failures`
   - 已知工具失败摘要。
6. `runtime_status`
   - Runtime 自己对运行状态的判断。
7. `verification_handoff`
   - 交给 Eval 的结构化评估交接材料。

### 3.2 `VerifierResult`

`VerifierResult` 是每个 verifier 的统一输出。

```python
@dataclass
class VerifierResult:
    verifier_name: str
    passed: bool
    hard: bool = True
    score: Optional[float] = None
    confidence: float = 1.0
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
```

字段理解：

1. `verifier_name`
   - 这个结果来自哪个 verifier。
2. `passed`
   - 该 verifier 是否通过。
3. `hard`
   - 是否属于硬检查。
4. `score`
   - 软检查分值，硬检查通常为空。
5. `confidence`
   - 该 verifier 自己对结论的置信度。
6. `reason`
   - 人类可读的简短原因。
7. `evidence`
   - 附加证据。

### 3.3 `RunJudgement`

`RunJudgement` 是 Eval 的最终输出。

```python
@dataclass
class RunJudgement:
    self_reported_success: bool
    verified_success: bool
    final_status: str
    failure_type: Optional[str]
    overclaim: bool
    confidence: float
    verifier_breakdown: List[VerifierResult] = field(default_factory=list)
```

字段理解：

1. `self_reported_success`
   - 从最终回答文本与 `stop_reason` 推断，模型自己是不是“声称做成了”。
2. `verified_success`
   - 经过 verifier 汇总后，系统是否认可这次完成。
3. `final_status`
   - `pass / partial / fail`
4. `failure_type`
   - 如果失败或部分完成，首要失败类型是什么。
5. `overclaim`
   - 模型自称成功，但验证不认可时为 `True`。
6. `confidence`
   - 汇总后的整体置信度。
7. `verifier_breakdown`
   - 所有 verifier 的明细。

## 4. `verification_handoff` 在这套流程里的作用

### 4.1 它是什么

`verification_handoff` 是 Runtime 主链路交给 Eval 的一份“评估交接单”。它的作用是把主链路知道、但 verifier 不容易自己重新猜出来的上下文，提前整理好。

一个典型 handoff 会包含：

1. `goal`
2. `constraints`
3. `expected_artifacts`
4. `claimed_done_items`
5. `key_tool_results`
6. `known_gaps`
7. `recovery`
8. `self_confidence`
9. `soft_score_threshold`
10. `rubric`

### 4.2 它是怎么来的

`verification_handoff` 由 `build_verification_handoff(...)` 生成，位置在 [`app/eval/verification_handoff_service.py`](/Users/yezibin/Project/InDepth/app/eval/verification_handoff_service.py)。

它的生成逻辑是：

1. 先构造一个规则版 fallback handoff。
2. 如果启用了 handoff LLM，则尝试让模型基于 runtime facts 生成更好的 handoff。
3. 如果 LLM 失败或输出不合法，就退回规则版。
4. 如果 LLM 成功，也还要经过 normalize，再并回 fallback 中缺失的字段。

### 4.3 为什么它重要

如果没有 handoff，Eval 只能看到：

1. 用户说了什么。
2. Runtime 最后回答了什么。
3. 有没有明显失败。

但很多“完成没完成”的判断需要更多上下文，比如：

1. 预期产物应该落在哪个路径。
2. 哪些约束不能违反。
3. 主链路自己承认了哪些已知缺口。
4. 工具执行里有哪些关键结果。

这些都由 handoff 来承载。

## 5. `EvalOrchestrator` 的汇总逻辑

核心实现见 [`app/eval/orchestrator.py`](/Users/yezibin/Project/InDepth/app/eval/orchestrator.py)。

### 5.1 `self_reported_success`

`infer_self_reported_success(final_answer, stop_reason)` 是一个轻量推断，不是最终结论。

它的判断顺序是：

1. 如果 `stop_reason` 属于明显异常结束：
   - `length`
   - `content_filter`
   - `model_failed`
   - `max_steps_reached`
   - `tool_failed_before_stop`
   那么直接判 `False`
2. 如果最终回答为空，判 `False`
3. 如果最终回答里出现明显负向提示词，如“未完成 / 失败 / error / 无法”，判 `False`
4. 如果最终回答里出现明显正向提示词，如“已完成 / done / success / 成功”，判 `True`
5. 其他情况下，如果 `stop_reason` 是健康结束（`stop / fallback_content / completed`），判 `True`

这个字段的意义不是“真完成了”，而是“模型看起来是在声称自己做成了”。

### 5.2 硬检查优先

当前 deterministic verifier 默认有两个：

1. `StopReasonVerifier`
2. `ToolFailureVerifier`

#### `StopReasonVerifier`

它要求：

1. `stop_reason` 必须在健康集合里：
   - `stop`
   - `fallback_content`
   - `completed`
2. `runtime_status` 必须是 `ok`

否则直接失败。

#### `ToolFailureVerifier`

它要求：

1. `tool_failures` 必须为空

只要有工具失败记录，就失败。

### 5.3 软检查

如果启用了 `LLMJudgeVerifier`，它会在 deterministic checks 之后运行。

这一步不是判断“过程是否健康”，而是判断“结果是否真的完成了目标”。它返回：

1. `passed`
2. `score`
3. `reason`
4. `checks`

这里的 `score` 会进入平均分计算。

### 5.4 最终状态如何落到 `pass / partial / fail`

规则如下：

1. 如果存在任意硬失败：
   - `verified_success = False`
   - `final_status = "fail"`
   - `failure_type = 第一个硬失败 verifier 名称`
2. 如果没有硬失败，但软评分均值低于 `soft_score_threshold`：
   - `verified_success = False`
   - `final_status = "partial"`
   - `failure_type = "soft_score_below_threshold"`
3. 否则：
   - `verified_success = True`
   - `final_status = "pass"`
   - `failure_type = None`

### 5.5 `confidence` 和 `overclaim`

`confidence` 的计算方式很直接：

1. 取每个 verifier 的 `confidence`
2. clamp 到 `[0, 1]`
3. 求平均

`overclaim` 的定义是：

1. `self_reported_success == True`
2. 但 `verified_success == False`

也就是“模型嘴上说成了，但验证不认可”。

## 6. `VerifierAgent` 是怎么工作的

### 6.1 它的定位

`VerifierAgent` 是一个独立的评估代理，不复用主 Runtime 的执行循环。它在 [`app/eval/agent/verifier_agent.py`](/Users/yezibin/Project/InDepth/app/eval/agent/verifier_agent.py)。

它的作用是：

1. 读取 `RunOutcome`
2. 根据 `verification_handoff` 推断证据根目录
3. 按需调用只读工具搜集证据
4. 输出一个严格 JSON 的评判结果

### 6.2 它为什么要独立

因为评估阶段和主执行阶段关注点不同：

1. 主执行链路关心“怎么完成任务”
2. VerifierAgent 关心“是否真的完成了任务”

把它单独隔离有两个好处：

1. 避免评估逻辑污染主执行 prompt
2. 可以更清楚地约束它只能做只读检查

### 6.3 它能做什么

它内置两类只读工具：

1. `list_work_files`
2. `read_project_file`

它不能随意执行写操作，也不能越出 project root。

### 6.4 它如何选择检查目录

它会优先从 `verification_handoff.expected_artifacts` 推断证据根目录；如果 handoff 没有足够信息，还会回退到：

1. `observability-evals/<task_id>__<run_id>`
2. `observability-evals/<task_id>`
3. `work/`

所以 handoff 里如果把期望产物写清楚，VerifierAgent 的判断质量会更高。

### 6.5 它的输出

它要求模型输出严格 JSON，对应 `LLMJudgeVerifier` 最终会读取的字段：

```json
{
  "passed": true,
  "score": 0.85,
  "reason": "任务按要求完成，证据基本充分",
  "checks": [
    "发现目标产物",
    "没有观察到明显工具失败"
  ]
}
```

如果 VerifierAgent 本身调用失败，`LLMJudgeVerifier` 会 fail-open：

1. `passed=True`
2. `score=None`
3. `confidence=0.2`
4. `reason=llm_judge_unavailable: ...`

这意味着：LLM judge 不可用时，不会把整次 Eval 直接打成失败。

## 7. 典型案例

### 7.1 健康完成

场景：

1. Runtime 正常 `stop`
2. `runtime_status = ok`
3. 没有工具失败
4. LLM judge 评分高于阈值

结果：

1. deterministic checks 全通过
2. soft score 达标
3. `final_status = pass`

### 7.2 过程失败

场景：

1. `stop_reason = model_failed`
2. 最终回答里还写了“已完成”

结果：

1. `self_reported_success = False` 或者即使为 `True` 也不重要
2. `StopReasonVerifier` 硬失败
3. 最终直接 `fail`

### 7.3 结果部分完成

场景：

1. Runtime 正常结束
2. 没有工具失败
3. 但 VerifierAgent 认为证据不足，给出低分

结果：

1. 硬检查通过
2. 软评分低于阈值
3. 最终 `partial`

### 7.4 Overclaim

场景：

1. 最终回答说“已经全部完成”
2. 但有工具失败，或 verifier 不认可

结果：

1. `self_reported_success = True`
2. `verified_success = False`
3. `overclaim = True`

## 8. 和 Runtime 的边界

Eval 不负责：

1. 决定什么时候停止执行
2. 决定要不要继续调用工具
3. 修复失败
4. 生成最终回答

Eval 负责：

1. 消费 Runtime 已经产出的事实
2. 做结构化判断
3. 给出可追踪结论

所以最合理的理解方式是：

1. Runtime 决定“做事”
2. Eval 决定“这次算不算真正做成”

## 9. 快速索引

### 9.1 主要入口

- `EvalOrchestrator.evaluate(run_outcome)`  
  文件：[`app/eval/orchestrator.py`](/Users/yezibin/Project/InDepth/app/eval/orchestrator.py)

- `build_verification_handoff(...)`  
  文件：[`app/eval/verification_handoff_service.py`](/Users/yezibin/Project/InDepth/app/eval/verification_handoff_service.py)

- `VerifierAgent.evaluate(...)`  
  文件：[`app/eval/agent/verifier_agent.py`](/Users/yezibin/Project/InDepth/app/eval/agent/verifier_agent.py)

### 9.2 默认 verifier

- `StopReasonVerifier`  
  文件：[`app/eval/verifiers/deterministic.py`](/Users/yezibin/Project/InDepth/app/eval/verifiers/deterministic.py)

- `ToolFailureVerifier`  
  文件：[`app/eval/verifiers/deterministic.py`](/Users/yezibin/Project/InDepth/app/eval/verifiers/deterministic.py)

- `LLMJudgeVerifier`  
  文件：[`app/eval/verifiers/llm_judge.py`](/Users/yezibin/Project/InDepth/app/eval/verifiers/llm_judge.py)
