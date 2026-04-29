"""Finalize and verification models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass

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
