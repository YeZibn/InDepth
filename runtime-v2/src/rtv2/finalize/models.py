"""Finalize and verification models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rtv2.judge import JudgeResultStatus


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

    result_status: JudgeResultStatus
    summary: str
    issues: list[str]


class RunReflexionAction(StrEnum):
    REQUEST_REPLAN = "request_replan"
    FINISH_FAILED = "finish_failed"


@dataclass(slots=True)
class RunReflexionInput:
    """Minimal input consumed by run-level reflexion after verification failure."""

    trigger_type: str
    latest_summary: str
    issues: list[str]


@dataclass(slots=True)
class RunReflexionResult:
    """Minimal run-level reflexion output used by finalize closeout."""

    summary: str
    action: RunReflexionAction
