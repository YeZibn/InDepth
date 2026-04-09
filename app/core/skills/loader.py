import os
from typing import Dict, List


class SkillLoader:
    def load_skill(self, skill_path: str) -> Dict[str, str]:
        skill_md = self._resolve_skill_md(skill_path)
        if not skill_md or not os.path.exists(skill_md):
            return {}
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return {}

        title = self._extract_title(content) or os.path.basename(os.path.dirname(skill_md))
        summary = self._extract_summary(content)
        return {"name": title, "summary": summary, "path": os.path.dirname(skill_md)}

    def build_skill_prompt(self, skill_paths: List[str]) -> str:
        skills = []
        for path in skill_paths:
            loaded = self.load_skill(path)
            if loaded:
                skills.append(loaded)
        if not skills:
            return ""

        lines = ["已加载技能（执行时可参考）："]
        for idx, skill in enumerate(skills, 1):
            lines.append(f"{idx}. {skill['name']}: {skill['summary']}")
            lines.append(f"   - path: {skill['path']}")
        return "\n".join(lines)

    def _resolve_skill_md(self, skill_path: str) -> str:
        if skill_path.endswith("SKILL.md"):
            return skill_path
        return os.path.join(skill_path, "SKILL.md")

    def _extract_title(self, content: str) -> str:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    def _extract_summary(self, content: str) -> str:
        for line in content.splitlines():
            text = line.strip()
            if text and not text.startswith("#") and not text.startswith("---"):
                return text[:140]
        return "Skill loaded."
