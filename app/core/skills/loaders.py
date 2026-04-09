import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.skills.skill import Skill


class SkillLoader(ABC):
    @abstractmethod
    def load(self) -> List[Skill]:
        pass


class LocalSkills(SkillLoader):
    """Load one skill dir or a directory containing multiple skills."""

    def __init__(self, path: str, validate: bool = True):
        self.path = Path(path).resolve()
        self.validate = validate

    def load(self) -> List[Skill]:
        if not self.path.exists():
            raise FileNotFoundError(f"Skills path does not exist: {self.path}")

        skills: List[Skill] = []
        if (self.path / "SKILL.md").exists():
            skill = self._load_skill_from_folder(self.path)
            if skill:
                skills.append(skill)
            return skills

        for item in self.path.iterdir():
            if not item.is_dir() or item.name.startswith("."):
                continue
            if not (item / "SKILL.md").exists():
                continue
            skill = self._load_skill_from_folder(item)
            if skill:
                skills.append(skill)
        return skills

    def _load_skill_from_folder(self, folder: Path) -> Optional[Skill]:
        content = (folder / "SKILL.md").read_text(encoding="utf-8")
        frontmatter, instructions = self._parse_skill_md(content)

        name = str(frontmatter.get("name") or folder.name).strip()
        description = str(frontmatter.get("description") or "").strip()

        if self.validate:
            errors = self._validate(frontmatter=frontmatter, name=name, description=description, folder=folder)
            if errors:
                raise ValueError(f"Skill validation failed for '{folder.name}': {'; '.join(errors)}")

        return Skill(
            name=name,
            description=description,
            instructions=instructions,
            source_path=str(folder),
            scripts=self._discover_files(folder / "scripts"),
            references=self._discover_files(folder / "references"),
            metadata=frontmatter.get("metadata"),
            license=frontmatter.get("license"),
            compatibility=frontmatter.get("compatibility"),
            allowed_tools=frontmatter.get("allowed-tools"),
        )

    def _parse_skill_md(self, content: str) -> Tuple[Dict[str, Any], str]:
        frontmatter: Dict[str, Any] = {}
        instructions = content
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
        if not match:
            return frontmatter, content.strip()

        frontmatter_text = match.group(1)
        instructions = match.group(2).strip()
        try:
            import yaml

            frontmatter = yaml.safe_load(frontmatter_text) or {}
            if not isinstance(frontmatter, dict):
                frontmatter = {}
        except Exception:
            frontmatter = self._parse_simple_frontmatter(frontmatter_text)
        return frontmatter, instructions

    def _parse_simple_frontmatter(self, text: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
        return result

    def _discover_files(self, directory: Path) -> List[str]:
        if not directory.exists() or not directory.is_dir():
            return []
        out = []
        for item in directory.iterdir():
            if item.is_file() and not item.name.startswith("."):
                out.append(item.name)
        return sorted(out)

    def _validate(self, frontmatter: Dict[str, Any], name: str, description: str, folder: Path) -> List[str]:
        errors: List[str] = []
        if not name:
            errors.append("missing name")
        if name != name.lower():
            errors.append("name must be lowercase")
        if folder.name != name:
            errors.append("directory name must match skill name")
        if not description:
            errors.append("missing description")
        if "allowed-tools" in frontmatter and not isinstance(frontmatter["allowed-tools"], list):
            errors.append("allowed-tools must be list")
        return errors
