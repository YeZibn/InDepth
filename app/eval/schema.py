from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExpectedArtifact:
    path: str
    must_exist: bool = True
    non_empty: bool = False
    contains: Optional[str] = None

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ExpectedArtifact":
        return ExpectedArtifact(
            path=str(data.get("path", "")).strip(),
            must_exist=bool(data.get("must_exist", True)),
            non_empty=bool(data.get("non_empty", False)),
            contains=str(data.get("contains")).strip() if data.get("contains") is not None else None,
        )


@dataclass
class TaskSpec:
    task_type: str = "general"
    goal: str = ""
    constraints: List[str] = field(default_factory=list)
    expected_artifacts: List[ExpectedArtifact] = field(default_factory=list)
    soft_score_threshold: float = 0.7
    llm_judge_enabled: bool = False
    llm_judge_rubric: str = ""

    @staticmethod
    def from_dict(data: Optional[Dict[str, Any]]) -> "TaskSpec":
        if not isinstance(data, dict):
            return TaskSpec()
        artifacts_data = data.get("expected_artifacts", []) or []
        artifacts: List[ExpectedArtifact] = []
        if isinstance(artifacts_data, list):
            for item in artifacts_data:
                if isinstance(item, dict):
                    artifacts.append(ExpectedArtifact.from_dict(item))
        constraints_raw = data.get("constraints", []) or []
        constraints = [str(x).strip() for x in constraints_raw if str(x).strip()] if isinstance(constraints_raw, list) else []
        return TaskSpec(
            task_type=str(data.get("task_type", "general")).strip() or "general",
            goal=str(data.get("goal", "")).strip(),
            constraints=constraints,
            expected_artifacts=artifacts,
            soft_score_threshold=float(data.get("soft_score_threshold", 0.7) or 0.7),
            llm_judge_enabled=bool(data.get("llm_judge_enabled", False)),
            llm_judge_rubric=str(data.get("llm_judge_rubric", "")).strip(),
        )


@dataclass
class RunOutcome:
    task_id: str
    run_id: str
    user_input: str
    final_answer: str
    stop_reason: str
    tool_failures: List[Dict[str, str]] = field(default_factory=list)
    runtime_status: str = "ok"


@dataclass
class VerifierResult:
    verifier_name: str
    passed: bool
    hard: bool = True
    score: Optional[float] = None
    confidence: float = 1.0
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunJudgement:
    self_reported_success: bool
    verified_success: bool
    final_status: str
    failure_type: Optional[str]
    overclaim: bool
    confidence: float
    verifier_breakdown: List[VerifierResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["verifier_breakdown"] = [v.to_dict() for v in self.verifier_breakdown]
        return payload
