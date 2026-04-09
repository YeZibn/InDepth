import os
from typing import Dict

from app.eval.schema import RunOutcome, TaskSpec, VerifierResult
from app.eval.verifiers.base import Verifier


class StopReasonVerifier(Verifier):
    name = "stop_reason_verifier"

    def verify(self, task_spec: TaskSpec, run_outcome: RunOutcome) -> VerifierResult:
        allowed_stop_reasons = {"stop", "fallback_content", "completed"}
        passed = run_outcome.stop_reason in allowed_stop_reasons and run_outcome.runtime_status == "ok"
        reason = (
            f"stop_reason={run_outcome.stop_reason}, runtime_status={run_outcome.runtime_status}"
            if not passed
            else "stop reason is healthy"
        )
        return VerifierResult(
            verifier_name=self.name,
            passed=passed,
            hard=True,
            confidence=1.0,
            reason=reason,
            evidence={"stop_reason": run_outcome.stop_reason, "runtime_status": run_outcome.runtime_status},
        )


class ToolFailureVerifier(Verifier):
    name = "tool_failure_verifier"

    def verify(self, task_spec: TaskSpec, run_outcome: RunOutcome) -> VerifierResult:
        passed = len(run_outcome.tool_failures) == 0
        return VerifierResult(
            verifier_name=self.name,
            passed=passed,
            hard=True,
            confidence=1.0,
            reason="tool failures detected" if not passed else "no tool failure detected",
            evidence={"tool_failures": run_outcome.tool_failures[:10]},
        )


class ArtifactVerifier(Verifier):
    name = "artifact_verifier"

    def _check_one(self, path: str, non_empty: bool, contains: str | None) -> Dict[str, str]:
        if not os.path.exists(path):
            return {"passed": "false", "reason": "file_not_found"}
        if non_empty and os.path.getsize(path) <= 0:
            return {"passed": "false", "reason": "file_empty"}
        if contains is not None:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if contains not in content:
                return {"passed": "false", "reason": "content_missing"}
        return {"passed": "true", "reason": "ok"}

    def verify(self, task_spec: TaskSpec, run_outcome: RunOutcome) -> VerifierResult:
        if not task_spec.expected_artifacts:
            return VerifierResult(
                verifier_name=self.name,
                passed=True,
                hard=True,
                confidence=0.8,
                reason="no expected artifacts configured",
                evidence={},
            )

        checks = []
        all_passed = True
        for expected in task_spec.expected_artifacts:
            if not expected.path:
                all_passed = False
                checks.append({"path": "", "passed": False, "reason": "empty_path"})
                continue
            if not expected.must_exist:
                checks.append({"path": expected.path, "passed": True, "reason": "must_exist=false"})
                continue
            result = self._check_one(expected.path, expected.non_empty, expected.contains)
            passed = result["passed"] == "true"
            all_passed = all_passed and passed
            checks.append({"path": expected.path, "passed": passed, "reason": result["reason"]})

        return VerifierResult(
            verifier_name=self.name,
            passed=all_passed,
            hard=True,
            confidence=1.0 if all_passed else 0.9,
            reason="all expected artifacts verified" if all_passed else "artifact verification failed",
            evidence={"checks": checks},
        )


def build_default_deterministic_verifiers() -> list[Verifier]:
    # Keep deterministic checks focused on runtime/process health.
    # Result/quality validation is delegated to verifier agent.
    return [StopReasonVerifier(), ToolFailureVerifier()]
