"""Skill models for runtime-v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SkillStatus(StrEnum):
    """Minimal runtime status for a loaded skill."""

    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass(slots=True)
class SkillManifest:
    """Minimal static manifest consumed by runtime-v2."""

    name: str
    description: str
    references: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuntimeSkill:
    """Minimal runtime skill object held by the skill registry."""

    manifest: SkillManifest
    source_path: str
    instructions: str
    status: SkillStatus = SkillStatus.LOADED

