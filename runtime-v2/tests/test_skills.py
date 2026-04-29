import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json

from rtv2.skills import LocalSkillLoader, SkillRegistry, SkillStatus, build_skill_tools
from rtv2.tools import LocalToolExecutor, ToolCall, ToolRegistry


class LocalSkillLoaderTests(unittest.TestCase):
    def create_skill_dir(
        self,
        root: Path,
        *,
        folder_name: str,
        frontmatter_name: str | None = None,
        description: str = "When to use this skill.",
        include_references: bool = True,
        include_scripts: bool = True,
        include_assets: bool = True,
    ) -> Path:
        skill_dir = root / folder_name
        skill_dir.mkdir(parents=True, exist_ok=False)
        skill_md = skill_dir / "SKILL.md"
        frontmatter_name = frontmatter_name if frontmatter_name is not None else folder_name
        skill_md.write_text(
            "\n".join(
                [
                    "---",
                    f"name: {frontmatter_name}",
                    f"description: {description}",
                    "---",
                    "",
                    "# Skill Body",
                    "Detailed instructions here.",
                ]
            ),
            encoding="utf-8",
        )
        if include_references:
            refs_dir = skill_dir / "references"
            refs_dir.mkdir()
            (refs_dir / "guide.md").write_text("guide", encoding="utf-8")
        if include_scripts:
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "run.py").write_text("print('ok')", encoding="utf-8")
        if include_assets:
            assets_dir = skill_dir / "assets"
            assets_dir.mkdir()
            (assets_dir / "logo.txt").write_text("asset", encoding="utf-8")
        return skill_dir

    def test_load_single_skill_folder_returns_runtime_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = self.create_skill_dir(root, folder_name="demo-skill")

            skills = LocalSkillLoader().load(str(skill_dir))

            self.assertEqual(len(skills), 1)
            skill = skills[0]
            self.assertEqual(skill.manifest.name, "demo-skill")
            self.assertEqual(skill.manifest.description, "When to use this skill.")
            self.assertEqual(skill.manifest.references, ["guide.md"])
            self.assertEqual(skill.manifest.scripts, ["run.py"])
            self.assertEqual(skill.manifest.assets, ["logo.txt"])
            self.assertEqual(skill.source_path, str(skill_dir.resolve()))
            self.assertIn("Detailed instructions here.", skill.instructions)
            self.assertEqual(skill.status, SkillStatus.LOADED)

    def test_load_parent_directory_returns_all_skill_subfolders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.create_skill_dir(root, folder_name="skill-a")
            self.create_skill_dir(root, folder_name="skill-b")

            skills = LocalSkillLoader().load(str(root))

            self.assertEqual([skill.manifest.name for skill in skills], ["skill-a", "skill-b"])

    def test_load_raises_when_name_and_folder_name_do_not_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = self.create_skill_dir(
                root,
                folder_name="skill-a",
                frontmatter_name="skill-b",
            )

            with self.assertRaises(ValueError):
                LocalSkillLoader().load(str(skill_dir))

    def test_load_raises_when_required_frontmatter_fields_are_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\nbody", encoding="utf-8")

            with self.assertRaises(ValueError):
                LocalSkillLoader().load(str(skill_dir))

    def test_load_allows_missing_resource_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = self.create_skill_dir(
                root,
                folder_name="demo-skill",
                include_references=False,
                include_scripts=False,
                include_assets=False,
            )

            skills = LocalSkillLoader().load(str(skill_dir))

            self.assertEqual(skills[0].manifest.references, [])
            self.assertEqual(skills[0].manifest.scripts, [])
            self.assertEqual(skills[0].manifest.assets, [])


class SkillRegistryTests(unittest.TestCase):
    def test_registry_enable_disable_and_list_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = LocalSkillLoaderTests().create_skill_dir(root, folder_name="demo-skill")
            skill = LocalSkillLoader().load(str(skill_dir))[0]
            registry = SkillRegistry()

            registry.register(skill)
            self.assertEqual(len(registry.list_enabled()), 0)

            registry.enable("demo-skill")
            self.assertEqual(registry.get("demo-skill").status, SkillStatus.ENABLED)
            self.assertEqual([skill.manifest.name for skill in registry.list_enabled()], ["demo-skill"])

            registry.disable("demo-skill")
            self.assertEqual(registry.get("demo-skill").status, SkillStatus.DISABLED)
            self.assertEqual(registry.list_enabled(), [])


class SkillToolsTests(unittest.TestCase):
    def build_registry_with_skill(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        skill_dir = LocalSkillLoaderTests().create_skill_dir(root, folder_name="demo-skill")
        skill = LocalSkillLoader().load(str(skill_dir))[0]
        registry = SkillRegistry()
        registry.register(skill)
        registry.enable("demo-skill")
        return registry

    def build_executor(self, registry: SkillRegistry) -> LocalToolExecutor:
        tool_registry = ToolRegistry()
        for spec in build_skill_tools(registry):
            tool_registry.register(spec)
        return LocalToolExecutor(tool_registry=tool_registry)

    def test_get_skill_instructions_returns_json_payload(self):
        registry = self.build_registry_with_skill()
        executor = self.build_executor(registry)

        result = executor.execute(ToolCall(tool_name="get_skill_instructions", arguments={"skill_name": "demo-skill"}))

        payload = json.loads(result.output_text)
        self.assertTrue(result.success)
        self.assertEqual(payload["skill_name"], "demo-skill")
        self.assertIn("Detailed instructions here.", payload["instructions"])

    def test_get_skill_reference_reads_registered_reference(self):
        registry = self.build_registry_with_skill()
        executor = self.build_executor(registry)

        result = executor.execute(
            ToolCall(
                tool_name="get_skill_reference",
                arguments={"skill_name": "demo-skill", "reference_path": "guide.md"},
            )
        )

        payload = json.loads(result.output_text)
        self.assertTrue(result.success)
        self.assertEqual(payload["reference_path"], "guide.md")
        self.assertEqual(payload["content"], "guide")

    def test_get_skill_script_reads_registered_script_without_execution(self):
        registry = self.build_registry_with_skill()
        executor = self.build_executor(registry)

        result = executor.execute(
            ToolCall(
                tool_name="get_skill_script",
                arguments={"skill_name": "demo-skill", "script_path": "run.py"},
            )
        )

        payload = json.loads(result.output_text)
        self.assertTrue(result.success)
        self.assertEqual(payload["script_path"], "run.py")
        self.assertIn("print('ok')", payload["content"])

    def test_get_skill_asset_reads_registered_asset(self):
        registry = self.build_registry_with_skill()
        executor = self.build_executor(registry)

        result = executor.execute(
            ToolCall(
                tool_name="get_skill_asset",
                arguments={"skill_name": "demo-skill", "asset_path": "logo.txt"},
            )
        )

        payload = json.loads(result.output_text)
        self.assertTrue(result.success)
        self.assertEqual(payload["asset_path"], "logo.txt")
        self.assertEqual(payload["content"], "asset")

    def test_skill_tools_return_json_error_for_unknown_skill_or_path(self):
        registry = self.build_registry_with_skill()
        executor = self.build_executor(registry)

        missing_skill = executor.execute(
            ToolCall(tool_name="get_skill_instructions", arguments={"skill_name": "missing"})
        )
        missing_path = executor.execute(
            ToolCall(
                tool_name="get_skill_reference",
                arguments={"skill_name": "demo-skill", "reference_path": "missing.md"},
            )
        )

        missing_skill_payload = json.loads(missing_skill.output_text)
        missing_path_payload = json.loads(missing_path.output_text)
        self.assertTrue(missing_skill.success)
        self.assertEqual(missing_skill_payload["error"], "skill_not_found")
        self.assertTrue(missing_path.success)
        self.assertEqual(missing_path_payload["error"], "resource_not_found")


if __name__ == "__main__":
    unittest.main()
