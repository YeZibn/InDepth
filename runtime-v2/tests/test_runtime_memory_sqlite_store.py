import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.memory import (
    ReflexionAction,
    ReflexionTrigger,
    RuntimeMemoryEntry,
    RuntimeMemoryEntryType,
    RuntimeMemoryQuery,
    RuntimeMemoryRole,
)
from rtv2.memory.sqlite_store import SQLiteRuntimeMemoryStore
from rtv2.task_graph.models import ResultRef


class SQLiteRuntimeMemoryStoreTests(unittest.TestCase):
    def create_store(self) -> SQLiteRuntimeMemoryStore:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_file = str(Path(tmpdir.name) / "runtime_memory.db")
        return SQLiteRuntimeMemoryStore(db_file=db_file)

    def make_context_entry(
        self,
        *,
        entry_id: str,
        task_id: str = "task-1",
        run_id: str = "run-1",
        step_id: str = "step-1",
        node_id: str = "node-1",
        role: RuntimeMemoryRole = RuntimeMemoryRole.ASSISTANT,
        content: str = "assistant observed state",
        tool_name: str = "",
        tool_call_id: str = "",
        created_at: str = "2026-04-28T21:00:00+08:00",
    ) -> RuntimeMemoryEntry:
        return RuntimeMemoryEntry(
            entry_id=entry_id,
            task_id=task_id,
            run_id=run_id,
            step_id=step_id,
            node_id=node_id,
            entry_type=RuntimeMemoryEntryType.CONTEXT,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            related_result_refs=[ResultRef(ref_id="ref-1", ref_type="artifact")],
            created_at=created_at,
        )

    def test_append_entry_persists_and_assigns_seq(self):
        store = self.create_store()

        stored = store.append_entry(self.make_context_entry(entry_id="entry-1"))

        self.assertEqual(stored.seq, 1)
        loaded = store.list_entries_for_run(task_id="task-1", run_id="run-1")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].entry_id, "entry-1")
        self.assertEqual(loaded[0].seq, 1)
        self.assertEqual(loaded[0].related_result_refs[0].ref_id, "ref-1")

    def test_list_entries_for_run_returns_stable_ascending_order(self):
        store = self.create_store()
        store.append_entry(self.make_context_entry(entry_id="entry-1", step_id="step-1"))
        store.append_entry(self.make_context_entry(entry_id="entry-2", step_id="step-2"))

        entries = store.list_entries_for_run(task_id="task-1", run_id="run-1")

        self.assertEqual([entry.entry_id for entry in entries], ["entry-1", "entry-2"])

    def test_list_entries_filters_by_step_node_type_and_tool_name(self):
        store = self.create_store()
        store.append_entry(
            self.make_context_entry(
                entry_id="entry-1",
                step_id="step-1",
                node_id="node-1",
                tool_name="echo_text",
            )
        )
        store.append_entry(
            RuntimeMemoryEntry(
                entry_id="entry-2",
                task_id="task-1",
                run_id="run-1",
                step_id="step-2",
                node_id="node-2",
                entry_type=RuntimeMemoryEntryType.REFLEXION,
                role=RuntimeMemoryRole.SYSTEM,
                content="need to re-check dependencies",
                reflexion_trigger=ReflexionTrigger.BLOCKED,
                reflexion_reason="dependency unresolved",
                next_attempt_hint="inspect dependency chain",
                reflexion_action=ReflexionAction.REQUEST_REPLAN,
                created_at="2026-04-28T21:00:01+08:00",
            )
        )

        entries = store.list_entries(
            RuntimeMemoryQuery(
                run_id="run-1",
                node_id="node-1",
                step_id="step-1",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                tool_name="echo_text",
            )
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_id, "entry-1")

    def test_get_latest_entries_returns_latest_slice_in_ascending_order(self):
        store = self.create_store()
        store.append_entry(self.make_context_entry(entry_id="entry-1", step_id="step-1"))
        store.append_entry(self.make_context_entry(entry_id="entry-2", step_id="step-2"))
        store.append_entry(self.make_context_entry(entry_id="entry-3", step_id="step-3"))

        latest = store.get_latest_entries(RuntimeMemoryQuery(run_id="run-1", limit=2))

        self.assertEqual([entry.entry_id for entry in latest], ["entry-2", "entry-3"])
        self.assertEqual([entry.seq for entry in latest], [2, 3])

    def test_list_entries_honors_limit_in_ascending_order(self):
        store = self.create_store()
        store.append_entry(self.make_context_entry(entry_id="entry-1"))
        store.append_entry(self.make_context_entry(entry_id="entry-2", step_id="step-2"))
        store.append_entry(self.make_context_entry(entry_id="entry-3", step_id="step-3"))

        entries = store.list_entries(RuntimeMemoryQuery(run_id="run-1", limit=2))

        self.assertEqual([entry.entry_id for entry in entries], ["entry-1", "entry-2"])
