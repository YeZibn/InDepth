from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


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
