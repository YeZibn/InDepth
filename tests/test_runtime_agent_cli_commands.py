import unittest

from app.agent.runtime_agent import handle_cli_command


class _FakeAgent:
    def __init__(self, task_id: str = "runtime_cli_task_old"):
        self.current_task_id = task_id
        self.start_calls = []

    def start_new_task(self, label: str = "") -> str:
        self.start_calls.append(label)
        self.current_task_id = f"runtime_cli_task_new_{label or 'next'}"
        return self.current_task_id


class RuntimeAgentCliCommandTests(unittest.TestCase):
    def test_non_command_is_not_handled(self):
        agent = _FakeAgent()
        mode, output, handled = handle_cli_command(agent, "hello", "chat")
        self.assertEqual(mode, "chat")
        self.assertEqual(output, "")
        self.assertFalse(handled)

    def test_mode_task_switches_mode_and_rotates_task(self):
        agent = _FakeAgent()
        mode, output, handled = handle_cli_command(agent, "/mode task", "chat")
        self.assertTrue(handled)
        self.assertEqual(mode, "task")
        self.assertEqual(agent.start_calls, ["task"])
        self.assertIn("已结束任务", output)
        self.assertIn("新任务", output)

    def test_mode_task_accepts_label(self):
        agent = _FakeAgent()
        mode, output, handled = handle_cli_command(agent, "/mode task notion kickoff", "chat")
        self.assertTrue(handled)
        self.assertEqual(mode, "task")
        self.assertEqual(agent.start_calls, ["notion kickoff"])
        self.assertIn("已进入 task 模式", output)

    def test_task_command_requires_task_mode(self):
        agent = _FakeAgent()
        mode, output, handled = handle_cli_command(agent, "/task notion", "chat")
        self.assertTrue(handled)
        self.assertEqual(mode, "chat")
        self.assertEqual(agent.start_calls, [])
        self.assertIn("请先使用 /mode task", output)

    def test_task_command_rotates_task_in_task_mode(self):
        agent = _FakeAgent("runtime_cli_task_active")
        mode, output, handled = handle_cli_command(agent, "/task notion_research", "task")
        self.assertTrue(handled)
        self.assertEqual(mode, "task")
        self.assertEqual(agent.start_calls, ["notion_research"])
        self.assertIn("已结束任务: runtime_cli_task_active", output)
        self.assertIn("新任务已启动", output)

    def test_newtask_alias_rotates_task_in_task_mode(self):
        agent = _FakeAgent("runtime_cli_task_active")
        mode, output, handled = handle_cli_command(agent, "/newtask sprint_2", "task")
        self.assertTrue(handled)
        self.assertEqual(mode, "task")
        self.assertEqual(agent.start_calls, ["sprint_2"])
        self.assertIn("已结束任务: runtime_cli_task_active", output)
        self.assertIn("新任务已启动", output)

    def test_status_returns_mode_and_task_id(self):
        agent = _FakeAgent("runtime_cli_task_xyz")
        mode, output, handled = handle_cli_command(agent, "/status", "task")
        self.assertTrue(handled)
        self.assertEqual(mode, "task")
        self.assertEqual(output, "mode=task, task_id=runtime_cli_task_xyz")

    def test_mode_chat_rotates_task_with_chat_label(self):
        agent = _FakeAgent("runtime_cli_task_active")
        mode, output, handled = handle_cli_command(agent, "/mode chat", "task")
        self.assertTrue(handled)
        self.assertEqual(mode, "chat")
        self.assertEqual(agent.start_calls, ["chat"])
        self.assertIn("已进入 chat 模式", output)
        self.assertIn("新任务: runtime_cli_task_new_chat", output)


if __name__ == "__main__":
    unittest.main()
