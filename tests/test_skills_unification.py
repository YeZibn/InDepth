import tempfile
import unittest
from pathlib import Path

from app.core.skills import build_skill_prompt_summary, build_skills_manager


class SkillsUnificationTests(unittest.TestCase):
    def test_build_skills_manager_accepts_skill_dir_and_skill_md_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "# Demo Skill\n\nThis is a demo summary.\n",
                encoding="utf-8",
            )

            by_dir = build_skills_manager([str(skill_dir)], validate=False)
            by_md = build_skills_manager([str(skill_dir / "SKILL.md")], validate=False)

            self.assertEqual(by_dir.get_skill_names(), ["demo-skill"])
            self.assertEqual(by_md.get_skill_names(), ["demo-skill"])

    def test_summary_prompt_has_expected_format(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill_dir = root / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "# Demo Skill\n\nSummary line for users.\n\n## Details\nMore text.\n",
                encoding="utf-8",
            )

            prompt = build_skill_prompt_summary([str(skill_dir)])

            lines = prompt.splitlines()
            self.assertEqual(lines[0], "已加载技能（执行时可参考）：")
            self.assertEqual(lines[1], "1. Demo Skill: Summary line for users.")
            self.assertTrue(lines[2].strip().startswith("- path: "))

    def test_system_prompt_exposes_skill_tools_and_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill_dir = root / "demo-skill"
            refs_dir = skill_dir / "references"
            scripts_dir = skill_dir / "scripts"
            refs_dir.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: demo desc\n---\n\n# Demo\n\nUse it.\n",
                encoding="utf-8",
            )
            (refs_dir / "guide.md").write_text("guide", encoding="utf-8")
            (scripts_dir / "run.sh").write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")

            manager = build_skills_manager([str(skill_dir)], validate=False)
            snippet = manager.get_system_prompt_snippet()

            self.assertIn("<skills_system>", snippet)
            self.assertIn("get_skill_instructions(skill_name)", snippet)
            self.assertIn("<name>demo-skill</name>", snippet)
            self.assertIn("<references>guide.md</references>", snippet)
            self.assertIn("<scripts>run.sh</scripts>", snippet)

    def test_missing_skill_path_is_ignored(self):
        manager = build_skills_manager(["/tmp/not-exists-skill-xyz"], validate=False)
        self.assertEqual(manager.get_skill_names(), [])
        self.assertEqual(manager.get_summary_prompt_snippet(), "")

if __name__ == "__main__":
    unittest.main()
