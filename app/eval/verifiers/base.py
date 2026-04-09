from abc import ABC, abstractmethod

from app.eval.schema import RunOutcome, TaskSpec, VerifierResult


class Verifier(ABC):
    name = "base_verifier"

    @abstractmethod
    def verify(self, task_spec: TaskSpec, run_outcome: RunOutcome) -> VerifierResult:
        raise NotImplementedError
