from abc import ABC, abstractmethod

from app.eval.schema import RunOutcome, VerifierResult


class Verifier(ABC):
    name = "base_verifier"

    @abstractmethod
    def verify(self, run_outcome: RunOutcome) -> VerifierResult:
        raise NotImplementedError
