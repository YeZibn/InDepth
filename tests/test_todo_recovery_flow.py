import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tool.todo_tool.todo_tool import (
    _parse_task_file,
    append_followup_subtasks,
    plan_task,
    plan_task_recovery,
    prepare_task,
    record_task_fallback,
    reopen_subtask,
    update_subtask,
    update_task_status,
)


def _create_todo(**kwargs):
    result = plan_task.entrypoint(**kwargs)
    assert result["success"], result
    execution = result["execution_result"]
    return {
        "result": result,
        "todo_id": execution["todo_id"],
        "filepath": execution["filepath"],
    }


def _append_subtasks(todo_id: str, split_reason: str, subtasks):
    return plan_task.entrypoint(
        task_name="Follow-up Task",
        context="Append structured work to the active todo",
        split_reason=split_reason,
        subtasks=subtasks,
        active_todo_id=todo_id,
    )


class TodoRecoveryFlowTests(unittest.TestCase):
    def test_prepare_task_returns_bootstrap_plan_when_no_active_todo(self):
        result = prepare_task.entrypoint(
            task_name="Draft Paper",
            context="Read the provided outline and write a structured paper draft.",
            active_todo_exists=False,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["should_use_todo"])
        self.assertEqual(len(result["subtasks"]), 1)
        self.assertIn("澄清上下文", result["subtasks"][0]["name"])
        self.assertIn("recommended_plan_task_args", result)
        self.assertEqual(result["recommended_plan_task_args"]["active_todo_id"], "")

    def test_prepare_task_prefers_plan_task_with_active_todo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="todo_123"),
            ):
                _create_todo(
                    task_name="Base Task",
                    context="Create the original tracked todo",
                    split_reason="Need a shared todo first.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                result = prepare_task.entrypoint(
                    task_name="Continue Paper",
                    context="Extend the existing tracked todo with the next writing steps",
                    active_todo_id="todo_123",
                    active_todo_exists=True,
                    active_subtask_number=1,
                    active_subtask_status="in-progress",
                )

        self.assertTrue(result["success"])
        self.assertTrue(result["should_use_todo"])
        self.assertEqual(result["active_todo_id"], "todo_123")
        self.assertIn("todo_123", result["active_todo_summary"])
        self.assertIn("recommended_plan_task_args", result)
        self.assertEqual(result["recommended_plan_task_args"]["active_todo_id"], "todo_123")
        self.assertTrue(result["recommended_plan_task_args"]["subtasks"])
        self.assertIn("current_state_summary", result)
        self.assertIn("当前 todo 进度", result["current_state_summary"])
        self.assertEqual(result["current_state_scan"]["progress"], "0/1 (0%)")

    def test_plan_task_normalizes_create_style_envelope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_plan_create_demo"),
            ):
                result = plan_task.entrypoint(
                    task_name="Draft Paper",
                    context="Write the next section based on approved outline",
                    split_reason="Need tracked writing steps for the next phase.",
                    subtasks=[
                        {
                            "title": "Draft introduction",
                            "description": "Write the introduction section",
                            "acceptance_criteria": ["Introduction saved"],
                        }
                    ],
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "create")
        self.assertEqual(result["subtask_count"], 1)
        self.assertEqual(result["task_plan"]["subtasks"][0]["name"], "Draft introduction")
        self.assertEqual(result["execution_result"]["todo_id"], "20260416_plan_create_demo")

    def test_plan_task_switches_to_update_mode_when_active_todo_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="todo_123"),
            ):
                _create_todo(
                    task_name="Base Task",
                    context="Create the original tracked todo",
                    split_reason="Need a shared todo first.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                result = plan_task.entrypoint(
                    task_name="Continue Paper",
                    context="Extend the existing tracked todo with the next steps",
                    split_reason="Need the next structured writing steps.",
                    subtasks=[
                        {
                            "name": "Draft analysis",
                            "description": "Write the analysis section",
                            "acceptance_criteria": ["Analysis saved"],
                        }
                    ],
                    active_todo_id="todo_123",
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "update")
        self.assertEqual(result["active_todo_id"], "todo_123")
        self.assertEqual(result["execution_result"]["todo_id"], "todo_123")
        self.assertEqual(result["execution_result"]["results"][0]["type"], "append_subtasks")

    def test_update_task_status_accepts_richer_unfinished_states(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000001_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Exercise richer todo states",
                    split_reason="Need multiple states for unfinished work.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                result = update_task_status.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    status="failed",
                )

                parsed = _parse_task_file(Path(created["filepath"]))

        self.assertTrue(result["success"])
        self.assertEqual(parsed["subtasks"][0]["status"], "failed")

    def test_record_task_fallback_persists_structured_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000002_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Record fallback metadata",
                    split_reason="Need explicit recovery metadata.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                result = record_task_fallback.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    state="failed",
                    reason_code="tool_error",
                    reason_detail="Command exited with status 1",
                    impact_scope="Blocks only this implementation step",
                    retryable=True,
                    required_input=["stderr log"],
                    suggested_next_action="retry_with_fix",
                    evidence=["work/error.log"],
                    owner="main",
                    retry_count=1,
                    retry_budget_remaining=1,
                    failure_facts={"stop_reason": "tool_failed_before_stop", "signal_tags": ["timeout"]},
                    failure_interpretation={"reason_code": "execution_environment_error", "confidence": 0.8},
                    retry_guidance=["retry with smaller batch"],
                )

                parsed = _parse_task_file(Path(created["filepath"]))

        self.assertTrue(result["success"])
        self.assertEqual(parsed["subtasks"][0]["status"], "pending")
        fallback = parsed["subtasks"][0]["fallback_record"]
        self.assertEqual(fallback["reason_code"], "tool_error")
        self.assertEqual(fallback["retry_count"], 1)
        self.assertEqual(fallback["required_input"], ["stderr log"])
        self.assertEqual(fallback["failure_facts"]["stop_reason"], "tool_failed_before_stop")
        self.assertEqual(fallback["failure_interpretation"]["reason_code"], "execution_environment_error")
        self.assertEqual(fallback["retry_guidance"], ["retry with smaller batch"])

    def test_plan_task_recovery_returns_structured_followups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000003_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Plan recovery for a failed task",
                    split_reason="Need a recovery plan.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing", "owner": "subagent:builder"}],
                )
                record_task_fallback.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    state="failed",
                    reason_code="validation_failed",
                    reason_detail="Tests failed after implementation",
                    impact_scope="Blocks delivery of the feature",
                    retryable=True,
                    suggested_next_action="repair",
                    evidence=["tests/output.txt"],
                    owner="subagent:builder",
                )
                decision = plan_task_recovery.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    retry_budget_remaining=2,
                    time_budget_remaining="15m",
                    available_roles=["builder", "verifier"],
                    allowed_degraded_delivery=False,
                    is_on_critical_path=True,
                )

        self.assertTrue(decision["success"])
        payload = decision["recovery_decision"]
        self.assertTrue(payload["can_resume_in_place"])
        self.assertFalse(payload["needs_derived_recovery_subtask"])
        self.assertEqual(payload["primary_action"], "repair")
        self.assertEqual(payload["decision_level"], "auto")
        self.assertEqual(payload["next_subtasks"], [])

    def test_plan_task_recovery_prefers_llm_suggested_next_action_for_generic_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000003a_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Plan recovery from LLM guidance",
                    split_reason="Need LLM-suggested action to drive recovery.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                record_task_fallback.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    state="failed",
                    reason_code="tool_invocation_error",
                    reason_detail="Command exited with a recoverable error",
                    impact_scope="Only this subtask is blocked",
                    retryable=True,
                    suggested_next_action="split",
                    evidence=["stderr.txt"],
                    owner="main",
                    retry_count=1,
                    retry_budget_remaining=1,
                )
                decision = plan_task_recovery.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    retry_budget_remaining=1,
                    time_budget_remaining="10m",
                    available_roles=["builder"],
                    allowed_degraded_delivery=False,
                    is_on_critical_path=False,
                )

        self.assertTrue(decision["success"])
        payload = decision["recovery_decision"]
        self.assertEqual(payload["primary_action"], "split")
        self.assertFalse(payload["can_resume_in_place"])
        self.assertTrue(payload["needs_derived_recovery_subtask"])
        self.assertGreaterEqual(len(payload["next_subtasks"]), 1)

    def test_append_followup_subtasks_adds_new_recovery_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000004_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Append recovery steps",
                    split_reason="Need follow-up tasks after failure.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                appended = append_followup_subtasks.entrypoint(
                    todo_id=created["todo_id"],
                    follow_up_subtasks=[
                        {
                            "name": "Diagnose the failure",
                            "goal": "Identify the root cause",
                            "description": "Inspect logs and isolate the problem",
                            "kind": "diagnose",
                            "owner": "main",
                            "depends_on": [1],
                            "acceptance_criteria": ["Root cause documented"],
                        },
                        {
                            "name": "Repair after diagnosis",
                            "goal": "Apply the targeted fix",
                            "description": "Use the diagnosis result to repair the task",
                            "kind": "repair",
                            "owner": "subagent:builder",
                            "depends_on": [2],
                            "acceptance_criteria": ["Repair implemented"],
                        },
                    ],
                )

                parsed = _parse_task_file(Path(created["filepath"]))

        self.assertTrue(appended["success"])
        self.assertEqual(len(parsed["subtasks"]), 3)
        self.assertEqual(parsed["subtasks"][1]["kind"], "diagnose")
        self.assertEqual(parsed["subtasks"][2]["dependencies"], ["2"])
        self.assertTrue(parsed["subtasks"][0]["subtask_id"].startswith("st_"))

    def test_append_followup_subtasks_supports_local_reference_aliases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000004b_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Append recovery steps with local references",
                    split_reason="Need follow-up tasks after failure.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                appended = append_followup_subtasks.entrypoint(
                    todo_id=created["todo_id"],
                    follow_up_subtasks=[
                        {
                            "name": "Diagnose the failure",
                            "goal": "Identify the root cause",
                            "description": "Inspect logs and isolate the problem",
                            "kind": "diagnose",
                            "owner": "main",
                            "depends_on": [1],
                            "acceptance_criteria": ["Root cause documented"],
                        },
                        {
                            "name": "Repair after diagnosis",
                            "goal": "Apply the targeted fix",
                            "description": "Use the diagnosis result to repair the task",
                            "kind": "repair",
                            "owner": "subagent:builder",
                            "depends_on": ["prev", "new:1"],
                            "acceptance_criteria": ["Repair implemented"],
                        },
                    ],
                )

                parsed = _parse_task_file(Path(created["filepath"]))

        self.assertTrue(appended["success"])
        self.assertEqual(len(parsed["subtasks"]), 3)
        self.assertEqual(parsed["subtasks"][1]["dependencies"], ["1"])
        self.assertEqual(parsed["subtasks"][2]["dependencies"], ["2"])

    def test_plan_task_recovery_marks_budget_exhausted_as_derived_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000005_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Plan recovery for budget exhaustion",
                    split_reason="Need explicit derived recovery.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                record_task_fallback.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    state="timed_out",
                    reason_code="budget_exhausted",
                    reason_detail="Runtime reached max steps",
                    impact_scope="Original task needs to be narrowed",
                    retryable=True,
                    suggested_next_action="split",
                    evidence=["runtime exceeded max steps"],
                    owner="main",
                    retry_count=1,
                    retry_budget_remaining=0,
                )
                decision = plan_task_recovery.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    retry_budget_remaining=0,
                    time_budget_remaining="",
                    available_roles=["builder"],
                    allowed_degraded_delivery=False,
                    is_on_critical_path=False,
                )

        self.assertTrue(decision["success"])
        payload = decision["recovery_decision"]
        self.assertFalse(payload["can_resume_in_place"])
        self.assertTrue(payload["needs_derived_recovery_subtask"])
        self.assertEqual(payload["primary_action"], "split")
        self.assertGreaterEqual(len(payload["next_subtasks"]), 1)
        self.assertEqual(payload["next_subtasks"][0]["kind"], "diagnose")

    def test_plan_task_recovery_treats_oversized_generation_request_as_split(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000006_demo"),
            ):
                created = _create_todo(
                    task_name="Long-form Writing",
                    context="Plan recovery for oversized generation",
                    split_reason="Need explicit split recovery for large generation tasks.",
                    subtasks=[{"name": "Draft full paper", "description": "Generate the whole paper body"}],
                )
                record_task_fallback.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    state="failed",
                    reason_code="oversized_generation_request",
                    reason_detail="Long-form generation overloaded a single model request",
                    impact_scope="Original writing step should be narrowed",
                    retryable=True,
                    suggested_next_action="split",
                    evidence=["HTTP 504", "long-form generation in one shot"],
                    owner="main",
                    retry_count=1,
                    retry_budget_remaining=1,
                )
                decision = plan_task_recovery.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    retry_budget_remaining=1,
                    time_budget_remaining="",
                    available_roles=["builder"],
                    allowed_degraded_delivery=False,
                    is_on_critical_path=False,
                )

        self.assertTrue(decision["success"])
        payload = decision["recovery_decision"]
        self.assertFalse(payload["can_resume_in_place"])
        self.assertTrue(payload["needs_derived_recovery_subtask"])
        self.assertEqual(payload["primary_action"], "split")
        self.assertGreaterEqual(len(payload["next_subtasks"]), 1)
        self.assertEqual(payload["next_subtasks"][0]["kind"], "diagnose")

    def test_plan_task_appends_create_style_subtasks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000005a_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Update todo with new structured work",
                    split_reason="Need a shared tracked todo.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                result = _append_subtasks(
                    todo_id=created["todo_id"],
                    split_reason="Add the next planned writing steps",
                    subtasks=[
                        {
                            "title": "Draft introduction",
                            "description": "Write the introduction section",
                            "dependencies": [1],
                            "acceptance_criteria": ["Introduction saved"],
                        }
                    ],
                )

                parsed = _parse_task_file(Path(created["filepath"]))

        self.assertTrue(result["success"])
        self.assertEqual(len(parsed["subtasks"]), 2)
        self.assertEqual(parsed["subtasks"][1]["name"], "Draft introduction")
        self.assertEqual(parsed["subtasks"][1]["dependencies"], ["1"])

    def test_plan_task_append_subtasks_remaps_local_batch_dependencies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000005b_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Append a second local plan phase",
                    split_reason="Need a shared tracked todo.",
                    subtasks=[
                        {"name": "Base step 1", "description": "Do the first base action"},
                        {"name": "Base step 2", "description": "Do the second base action", "dependencies": [1]},
                        {"name": "Base step 3", "description": "Do the third base action", "dependencies": [2]},
                    ],
                )
                result = _append_subtasks(
                    todo_id=created["todo_id"],
                    split_reason="Add the next locally-numbered execution phase",
                    subtasks=[
                        {"title": "Phase 2 step 1", "description": "Start the next phase"},
                        {"title": "Phase 2 step 2", "description": "Continue phase 2", "dependencies": [1]},
                        {"title": "Phase 2 step 3", "description": "Finish phase 2", "dependencies": [2]},
                    ],
                )

                parsed = _parse_task_file(Path(created["filepath"]))

        self.assertTrue(result["success"])
        self.assertEqual(len(parsed["subtasks"]), 6)
        self.assertEqual(parsed["subtasks"][3]["dependencies"], [])
        self.assertEqual(parsed["subtasks"][4]["dependencies"], ["4"])
        self.assertEqual(parsed["subtasks"][5]["dependencies"], ["5"])

    def test_plan_task_rejects_incomplete_subtasks(self):
        result = plan_task.entrypoint(
            task_name="Demo Task",
            context="Update todo safely",
            split_reason="Need strict update validation.",
            subtasks=[],
        )

        self.assertFalse(result["success"])
        self.assertIn("subtasks", result["error"])

    def test_update_subtask_patches_by_subtask_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000006_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Patch a subtask",
                    split_reason="Need structured update support.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                parsed = _parse_task_file(Path(created["filepath"]))
                subtask_id = parsed["subtasks"][0]["subtask_id"]
                result = update_subtask.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_id=subtask_id,
                    fields_to_update={
                        "description": "Do the patched thing",
                        "owner": "main",
                        "acceptance_criteria": ["Patched output saved"],
                    },
                    update_reason="Refine execution details",
                )

                reparsed = _parse_task_file(Path(created["filepath"]))

        self.assertTrue(result["success"])
        self.assertEqual(reparsed["subtasks"][0]["subtask_id"], subtask_id)
        self.assertEqual(reparsed["subtasks"][0]["description"], "Do the patched thing")
        self.assertEqual(reparsed["subtasks"][0]["owner"], "main")
        self.assertEqual(reparsed["subtasks"][0]["acceptance_criteria"], ["Patched output saved"])

    def test_reopen_subtask_marks_it_in_progress_again(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("app.tool.todo_tool.todo_tool._get_todo_dir", return_value=tmpdir),
                patch("app.tool.todo_tool.todo_tool._emit_obs"),
                patch("app.tool.todo_tool.todo_tool._generate_todo_id", return_value="20260416_000007_demo"),
            ):
                created = _create_todo(
                    task_name="Demo Task",
                    context="Reopen failed subtask",
                    split_reason="Need explicit reopen semantics.",
                    subtasks=[{"name": "Main step", "description": "Do the main thing"}],
                )
                update_task_status.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_number=1,
                    status="failed",
                )
                parsed = _parse_task_file(Path(created["filepath"]))
                subtask_id = parsed["subtasks"][0]["subtask_id"]
                result = reopen_subtask.entrypoint(
                    todo_id=created["todo_id"],
                    subtask_id=subtask_id,
                    reason="Retry after targeted fix",
                )
                reparsed = _parse_task_file(Path(created["filepath"]))

        self.assertTrue(result["success"])
        self.assertEqual(reparsed["subtasks"][0]["status"], "in-progress")


if __name__ == "__main__":
    unittest.main()
