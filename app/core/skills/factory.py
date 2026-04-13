from pathlib import Path
from typing import Iterable, List

from app.core.skills.loaders import LocalSkills
from app.core.skills.manager import Skills


def build_skills_manager(skill_paths: Iterable[str] | None, validate: bool = False) -> Skills:
    """Build a unified Skills manager from path-like inputs.

    This helper accepts skill directory paths, SKILL.md paths, or directories
    containing multiple skills. Missing paths are skipped.
    """
    loaders: List[LocalSkills] = []
    for raw in skill_paths or []:
        path = str(raw).strip()
        if not path:
            continue

        resolved = Path(path)
        if resolved.name == "SKILL.md":
            resolved = resolved.parent
        if not resolved.exists():
            continue

        loaders.append(LocalSkills(path=str(resolved), validate=validate))
    return Skills(loaders=loaders)


def build_skill_prompt_summary(
    skill_paths: Iterable[str] | None,
    validate: bool = False,
) -> str:
    return build_skills_manager(skill_paths, validate=validate).get_summary_prompt_snippet()
