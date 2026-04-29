"""Finalize and verification models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VerificationResultStatus(StrEnum):
    """Minimal final verification verdict."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(slots=True)
class FinalizeGenerationResult:
    """Minimal finalize generator output."""

    final_output: str
    graph_summary: str


@dataclass(slots=True)
class Handoff:
    """Minimal final verification handoff."""

    goal: str
    user_input: str
    graph_summary: str
    final_output: str


@dataclass(slots=True)
class VerificationResult:
    """Minimal final verification output."""

    result_status: VerificationResultStatus
    summary: str
    issues: list[str]
