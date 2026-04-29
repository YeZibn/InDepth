"""Local skill loader for runtime-v2."""

from __future__ import annotations

import re
from pathlib import Path

from rtv2.skills.models import RuntimeSkill, SkillManifest, SkillStatus


class LocalSkillLoader:
    """Load local directory-based skills into runtime skill objects."""

    def load(self, path: str) -> list[RuntimeSkill]:
        root = Path(path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Skill path does not exist: {root}")

        if (root / "SKILL.md").exists():
            return [self._load_skill_from_folder(root)]

        loaded_skills: list[RuntimeSkill] = []
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if not (child / "SKILL.md").exists():
                continue
            loaded_skills.append(self._load_skill_from_folder(child))
        return loaded_skills

    def _load_skill_from_folder(self, folder: Path) -> RuntimeSkill:
        skill_md_path = folder / "SKILL.md"
        if not skill_md_path.exists():
            raise FileNotFoundError(f"SKILL.md not found in skill folder: {folder}")

        frontmatter, instructions = self._parse_skill_md(skill_md_path.read_text(encoding="utf-8"))
        name = str(frontmatter.get("name", "") or "").strip()
        description = str(frontmatter.get("description", "") or "").strip()

        self._validate_required_fields(name=name, description=description, folder=folder)

        manifest = SkillManifest(
            name=name,
            description=description,
            references=self._discover_relative_files(folder / "references"),
            scripts=self._discover_relative_files(folder / "scripts"),
            assets=self._discover_relative_files(folder / "assets"),
        )
        return RuntimeSkill(
            manifest=manifest,
            source_path=str(folder),
            instructions=instructions,
            status=SkillStatus.LOADED,
        )

    @staticmethod
    def _parse_skill_md(content: str) -> tuple[dict[str, object], str]:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
        if match is None:
            return {}, content.strip()

        frontmatter_text = match.group(1)
        instructions = match.group(2).strip()
        try:
            import yaml

            loaded = yaml.safe_load(frontmatter_text) or {}
            if isinstance(loaded, dict):
                return loaded, instructions
        except Exception:
            pass
        return LocalSkillLoader._parse_simple_frontmatter(frontmatter_text), instructions

    @staticmethod
    def _parse_simple_frontmatter(text: str) -> dict[str, object]:
        result: dict[str, object] = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
        return result

    @staticmethod
    def _validate_required_fields(*, name: str, description: str, folder: Path) -> None:
        errors: list[str] = []
        if not name:
            errors.append("missing required frontmatter field: name")
        if not description:
            errors.append("missing required frontmatter field: description")
        if name and folder.name != name:
            errors.append("skill folder name must match frontmatter name")
        if errors:
            raise ValueError(f"Skill validation failed for '{folder}': {'; '.join(errors)}")

    @staticmethod
    def _discover_relative_files(directory: Path) -> list[str]:
        if not directory.exists() or not directory.is_dir():
            return []

        paths: list[str] = []
        for path in sorted(directory.rglob("*")):
            if path.is_dir() or path.name.startswith("."):
                continue
            paths.append(path.relative_to(directory).as_posix())
        return paths

