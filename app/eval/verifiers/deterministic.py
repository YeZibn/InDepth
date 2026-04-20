import os
from typing import Dict

from app.eval.schema import RunOutcome, VerifierResult
from app.eval.verifiers.base import Verifier


class StopReasonVerifier(Verifier):
    name = "stop_reason_verifier"

    def verify(self, run_outcome: RunOutcome) -> VerifierResult:
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

    def verify(self, run_outcome: RunOutcome) -> VerifierResult:
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

    def verify(self, run_outcome: RunOutcome) -> VerifierResult:
        handoff = run_outcome.verification_handoff if isinstance(run_outcome.verification_handoff, dict) else {}
        expected_artifacts = handoff.get("expected_artifacts", [])
        if not isinstance(expected_artifacts, list):
            expected_artifacts = []
        if not expected_artifacts:
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
        for expected in expected_artifacts:
            if not isinstance(expected, dict):
                all_passed = False
                checks.append({"path": "", "passed": False, "reason": "invalid_artifact_schema"})
                continue
            path = str(expected.get("path", "") or "").strip()
            must_exist = bool(expected.get("must_exist", True))
            non_empty = bool(expected.get("non_empty", False))
            contains = expected.get("contains")
            contains_text = str(contains).strip() if contains is not None else None

            if not path:
                all_passed = False
                checks.append({"path": "", "passed": False, "reason": "empty_path"})
                continue
            if not must_exist:
                checks.append({"path": path, "passed": True, "reason": "must_exist=false"})
                continue
            result = self._check_one(path, non_empty, contains_text)
            passed = result["passed"] == "true"
            all_passed = all_passed and passed
            checks.append({"path": path, "passed": passed, "reason": result["reason"]})

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
    # Artifact / evidence inspection is delegated to VerifierAgent.
    return [StopReasonVerifier(), ToolFailureVerifier()]
