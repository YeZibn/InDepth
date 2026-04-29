"""Minimal skill registry for runtime-v2."""

from __future__ import annotations

from rtv2.skills.models import RuntimeSkill, SkillStatus


class SkillRegistry:
    """Store loaded runtime skills and expose minimal enable/disable controls."""

    def __init__(self) -> None:
        self._skills: dict[str, RuntimeSkill] = {}

    def register(self, skill: RuntimeSkill) -> None:
        self._skills[skill.manifest.name] = skill

    def get(self, name: str) -> RuntimeSkill | None:
        return self._skills.get(name)

    def list_all(self) -> list[RuntimeSkill]:
        return list(self._skills.values())

    def list_enabled(self) -> list[RuntimeSkill]:
        return [skill for skill in self._skills.values() if skill.status is SkillStatus.ENABLED]

    def enable(self, name: str) -> None:
        skill = self._require_skill(name)
        skill.status = SkillStatus.ENABLED

    def disable(self, name: str) -> None:
        skill = self._require_skill(name)
        skill.status = SkillStatus.DISABLED

    def _require_skill(self, name: str) -> RuntimeSkill:
        skill = self.get(name)
        if skill is None:
            raise KeyError(f"Skill not found: {name}")
        return skill

