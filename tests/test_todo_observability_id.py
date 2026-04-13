import unittest
from unittest.mock import patch

from app.tool.todo_tool.todo_tool import _emit_obs


class TodoObservabilityIdTests(unittest.TestCase):
    @patch("app.tool.todo_tool.todo_tool.emit_event")
    def test_emit_obs_prefixes_todo_id(self, mock_emit_event):
        _emit_obs(todo_id="20260413_154616_demo", event_type="task_started")
        mock_emit_event.assert_called_once()
        kwargs = mock_emit_event.call_args.kwargs
        self.assertEqual(kwargs["task_id"], "todo-id:20260413_154616_demo")
        self.assertEqual(kwargs["run_id"], "todo-id:20260413_154616_demo")

    @patch("app.tool.todo_tool.todo_tool.emit_event")
    def test_emit_obs_keeps_prefixed_id(self, mock_emit_event):
        _emit_obs(todo_id="todo-id:abc", event_type="task_started")
        mock_emit_event.assert_called_once()
        kwargs = mock_emit_event.call_args.kwargs
        self.assertEqual(kwargs["task_id"], "todo-id:abc")
        self.assertEqual(kwargs["run_id"], "todo-id:abc")


if __name__ == "__main__":
    unittest.main()
