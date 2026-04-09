import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from app.core.skills.loaders import SkillLoader
from app.core.skills.skill import Skill
from app.core.skills.utils import is_safe_path, read_file_safe, run_script
from app.core.tools.decorator import ToolFunction


class Skills:
    """Agno-style skills manager: load skills, generate prompt snippet, expose access tools."""

    def __init__(self, loaders: List[SkillLoader]):
        self.loaders = loaders
        self._skills: Dict[str, Skill] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        for loader in self.loaders:
            skills = loader.load()
            for skill in skills:
                self._skills[skill.name] = skill

    def reload(self) -> None:
        self._skills.clear()
        self._load_skills()

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def get_skill_names(self) -> List[str]:
        return list(self._skills.keys())

    def get_all_skills(self) -> List[Skill]:
        return list(self._skills.values())

    def get_system_prompt_snippet(self) -> str:
        if not self._skills:
            return ""
        lines = [
            "<skills_system>",
            "Skills are reusable expertise packages. Skill names are NOT direct callable functions.",
            "Use skill access tools to load instructions/references/scripts on demand:",
            "1) get_skill_instructions(skill_name)",
            "2) get_skill_reference(skill_name, reference_path)",
            "3) get_skill_script(skill_name, script_path, execute=False)",
            "",
            "Available skills:",
        ]
        for skill in self._skills.values():
            lines.append("<skill>")
            lines.append(f"  <name>{skill.name}</name>")
            lines.append(f"  <description>{skill.description}</description>")
            lines.append(f"  <scripts>{', '.join(skill.scripts) if skill.scripts else 'none'}</scripts>")
            lines.append(f"  <references>{', '.join(skill.references) if skill.references else 'none'}</references>")
            lines.append("</skill>")
        lines.append("</skills_system>")
        return "\n".join(lines)

    def get_tools(self) -> List[ToolFunction]:
        return [
            ToolFunction(
                name="get_skill_instructions",
                description="Load full instructions for a skill.",
                entrypoint=self._get_skill_instructions,
                parameters={
                    "type": "object",
                    "properties": {"skill_name": {"type": "string"}},
                    "required": ["skill_name"],
                },
            ),
            ToolFunction(
                name="get_skill_reference",
                description="Load a reference document from a skill.",
                entrypoint=self._get_skill_reference,
                parameters={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "reference_path": {"type": "string"},
                    },
                    "required": ["skill_name", "reference_path"],
                },
            ),
            ToolFunction(
                name="get_skill_script",
                description="Read or execute a script from a skill.",
                entrypoint=self._get_skill_script,
                parameters={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "script_path": {"type": "string"},
                        "execute": {"type": "boolean"},
                        "args": {"type": "array", "items": {"type": "string"}},
                        "timeout": {"type": "integer", "minimum": 1, "maximum": 300},
                    },
                    "required": ["skill_name", "script_path"],
                },
            ),
        ]

    def _get_skill_instructions(self, skill_name: str) -> str:
        skill = self.get_skill(skill_name)
        if skill is None:
            return json.dumps({"error": f"Skill '{skill_name}' not found", "available_skills": self.get_skill_names()})
        return json.dumps(
            {
                "skill_name": skill.name,
                "description": skill.description,
                "instructions": skill.instructions,
                "available_scripts": skill.scripts,
                "available_references": skill.references,
            },
            ensure_ascii=False,
        )

    def _get_skill_reference(self, skill_name: str, reference_path: str) -> str:
        skill = self.get_skill(skill_name)
        if skill is None:
            return json.dumps({"error": f"Skill '{skill_name}' not found", "available_skills": self.get_skill_names()})
        if reference_path not in skill.references:
            return json.dumps({"error": f"Reference '{reference_path}' not found", "available_references": skill.references})

        refs_dir = Path(skill.source_path) / "references"
        if not is_safe_path(refs_dir, reference_path):
            return json.dumps({"error": f"Invalid reference path: '{reference_path}'"})
        try:
            content = read_file_safe(refs_dir / reference_path)
            return json.dumps(
                {"skill_name": skill_name, "reference_path": reference_path, "content": content},
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"error": f"Error reading reference file: {e}"}, ensure_ascii=False)

    def _get_skill_script(
        self,
        skill_name: str,
        script_path: str,
        execute: bool = False,
        args: Optional[List[str]] = None,
        timeout: int = 30,
    ) -> str:
        skill = self.get_skill(skill_name)
        if skill is None:
            return json.dumps({"error": f"Skill '{skill_name}' not found", "available_skills": self.get_skill_names()})
        if script_path not in skill.scripts:
            return json.dumps({"error": f"Script '{script_path}' not found", "available_scripts": skill.scripts})

        scripts_dir = Path(skill.source_path) / "scripts"
        if not is_safe_path(scripts_dir, script_path):
            return json.dumps({"error": f"Invalid script path: '{script_path}'"})
        target = scripts_dir / script_path

        if not execute:
            try:
                content = read_file_safe(target)
                return json.dumps(
                    {"skill_name": skill_name, "script_path": script_path, "content": content},
                    ensure_ascii=False,
                )
            except Exception as e:
                return json.dumps({"error": f"Error reading script file: {e}"}, ensure_ascii=False)

        try:
            result = run_script(script_path=target, args=args, timeout=timeout, cwd=Path(skill.source_path))
            return json.dumps(
                {
                    "skill_name": skill_name,
                    "script_path": script_path,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                },
                ensure_ascii=False,
            )
        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"Script execution timed out after {timeout} seconds"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Error executing script: {e}"}, ensure_ascii=False)
