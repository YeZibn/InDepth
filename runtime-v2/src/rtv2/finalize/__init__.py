"""Finalize and verification hooks for runtime-v2."""

from rtv2.finalize.models import (
    FinalizeGenerationResult,
    Handoff,
    VerificationResult,
)
from rtv2.finalize.verifier import RuntimeVerifier
from rtv2.judge import JudgeResultStatus as VerificationResultStatus

__all__ = [
    "FinalizeGenerationResult",
    "Handoff",
    "RuntimeVerifier",
    "VerificationResult",
    "VerificationResultStatus",
]
