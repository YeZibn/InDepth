"""Minimal model abstractions for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ModelOutput:
    """Minimal raw model output wrapper."""

    content: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GenerationConfig:
    """Minimal generation config for OpenAI-compatible chat models."""

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: list[str] | str | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    """Minimal provider contract used by solver-side runners."""

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        config: GenerationConfig | None = None,
    ) -> ModelOutput:
        """Generate the next assistant turn."""
