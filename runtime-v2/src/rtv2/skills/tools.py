"""Skill resource access tools for runtime-v2."""

from __future__ import annotations

import json
from pathlib import Path

from rtv2.skills.registry import SkillRegistry
from rtv2.tools import ToolSpec, tool


def build_skill_tools(skill_registry: SkillRegistry) -> list[ToolSpec]:
    """Build the minimal read-only skill resource tools."""

    def _get_skill_instructions(skill_name: str) -> str:
        skill = skill_registry.get(skill_name)
        if skill is None:
            return _error("skill_not_found", skill_name=skill_name, available_skills=_list_skill_names(skill_registry))
        return json.dumps(
            {
                "skill_name": skill.manifest.name,
                "description": skill.manifest.description,
                "instructions": skill.instructions,
            },
            ensure_ascii=False,
        )

    def _get_skill_reference(skill_name: str, reference_path: str) -> str:
        return _read_skill_resource(
            skill_registry=skill_registry,
            skill_name=skill_name,
            relative_path=reference_path,
            allowed_paths=skill_registry.get(skill_name).manifest.references if skill_registry.get(skill_name) else [],
            resource_subdir="references",
            response_key="reference_path",
        )

    def _get_skill_script(skill_name: str, script_path: str) -> str:
        return _read_skill_resource(
            skill_registry=skill_registry,
            skill_name=skill_name,
            relative_path=script_path,
            allowed_paths=skill_registry.get(skill_name).manifest.scripts if skill_registry.get(skill_name) else [],
            resource_subdir="scripts",
            response_key="script_path",
        )

    def _get_skill_asset(skill_name: str, asset_path: str) -> str:
        return _read_skill_resource(
            skill_registry=skill_registry,
            skill_name=skill_name,
            relative_path=asset_path,
            allowed_paths=skill_registry.get(skill_name).manifest.assets if skill_registry.get(skill_name) else [],
            resource_subdir="assets",
            response_key="asset_path",
        )

    return [
        tool(
            name="get_skill_instructions",
            description="Load the full instructions body for a skill.",
            parameters={
                "type": "object",
                "properties": {"skill_name": {"type": "string"}},
                "required": ["skill_name"],
            },
        )(_get_skill_instructions),
        tool(
            name="get_skill_reference",
            description="Load a reference file from a skill.",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "reference_path": {"type": "string"},
                },
                "required": ["skill_name", "reference_path"],
            },
        )(_get_skill_reference),
        tool(
            name="get_skill_script",
            description="Load a script file from a skill without executing it.",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "script_path": {"type": "string"},
                },
                "required": ["skill_name", "script_path"],
            },
        )(_get_skill_script),
        tool(
            name="get_skill_asset",
            description="Load an asset file from a skill as text.",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "asset_path": {"type": "string"},
                },
                "required": ["skill_name", "asset_path"],
            },
        )(_get_skill_asset),
    ]


def _read_skill_resource(
    *,
    skill_registry: SkillRegistry,
    skill_name: str,
    relative_path: str,
    allowed_paths: list[str],
    resource_subdir: str,
    response_key: str,
) -> str:
    skill = skill_registry.get(skill_name)
    if skill is None:
        return _error("skill_not_found", skill_name=skill_name, available_skills=_list_skill_names(skill_registry))

    if relative_path not in allowed_paths:
        return _error(
            "resource_not_found",
            skill_name=skill_name,
            **{response_key: relative_path},
            available_paths=allowed_paths,
        )

    root = Path(skill.source_path).resolve()
    base_dir = (root / resource_subdir).resolve()
    target = (base_dir / relative_path).resolve()
    if not _is_within(target, base_dir):
        return _error(
            "path_escape_blocked",
            skill_name=skill_name,
            **{response_key: relative_path},
        )

    try:
        content = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _error(
            "resource_missing_on_disk",
            skill_name=skill_name,
            **{response_key: relative_path},
        )
    except Exception as exc:
        return _error(
            "resource_read_failed",
            skill_name=skill_name,
            **{response_key: relative_path},
            error=str(exc),
        )

    return json.dumps(
        {
            "skill_name": skill.manifest.name,
            response_key: relative_path,
            "content": content,
        },
        ensure_ascii=False,
    )


def _list_skill_names(skill_registry: SkillRegistry) -> list[str]:
    return [skill.manifest.name for skill in skill_registry.list_all()]


def _error(code: str, **payload: object) -> str:
    return json.dumps({"error": code, **payload}, ensure_ascii=False)


def _is_within(target: Path, base_dir: Path) -> bool:
    try:
        target.relative_to(base_dir)
        return True
    except ValueError:
        return False
