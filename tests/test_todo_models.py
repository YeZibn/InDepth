import unittest

from app.core.todo import (
    TodoBindingState,
    TodoContext,
    TodoExecutionPhase,
    TodoSnapshot,
    TodoSubtask,
    TodoSubtaskStatus,
)


class TodoModelsTests(unittest.TestCase):
    def test_todo_context_defaults_to_unbound_planning_state(self):
        context = TodoContext()

        self.assertEqual(context.todo_id, "")
        self.assertEqual(context.execution_phase, TodoExecutionPhase.PLANNING)
        self.assertEqual(context.binding_state, TodoBindingState.BOUND)
        self.assertFalse(context.binding_required)
        self.assertFalse(context.is_bound)
        self.assertFalse(context.has_active_subtask)

    def test_todo_context_reports_bound_and_active_subtask(self):
        context = TodoContext(
            todo_id="todo-1",
            active_subtask_id="st_1",
            active_subtask_number=2,
            execution_phase=TodoExecutionPhase.EXECUTING,
            binding_required=True,
            binding_state=TodoBindingState.BOUND,
        )

        self.assertTrue(context.is_bound)
        self.assertTrue(context.has_active_subtask)
        self.assertEqual(context.execution_phase, TodoExecutionPhase.EXECUTING)

    def test_todo_subtask_keeps_core_and_extension_fields(self):
        subtask = TodoSubtask(
            subtask_id="st_1",
            number=1,
            name="Inspect runtime coupling",
            description="Review runtime references into todo tool internals.",
            status=TodoSubtaskStatus.IN_PROGRESS,
            dependencies=[2, 3],
            acceptance_criteria=["References documented"],
            origin_subtask_number=9,
        )

        self.assertEqual(subtask.status, TodoSubtaskStatus.IN_PROGRESS)
        self.assertEqual(subtask.dependencies, [2, 3])
        self.assertEqual(subtask.acceptance_criteria, ["References documented"])
        self.assertEqual(subtask.origin_subtask_number, 9)

    def test_todo_snapshot_exposes_subtask_ids(self):
        snapshot = TodoSnapshot(
            todo_id="todo-1",
            task_name="Refactor todo domain",
            context="Split runtime todo logic into domain service.",
            split_reason="Too many runtime/tool cross-layer references.",
            subtasks=[
                TodoSubtask(
                    subtask_id="st_1",
                    number=1,
                    name="Define models",
                    description="Create todo domain dataclasses.",
                ),
                TodoSubtask(
                    subtask_id="st_2",
                    number=2,
                    name="Extract service",
                    description="Move lifecycle rules into TodoService.",
                ),
            ],
        )

        self.assertEqual(snapshot.subtask_ids, ["st_1", "st_2"])


if __name__ == "__main__":
    unittest.main()
