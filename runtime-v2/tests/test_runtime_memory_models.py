import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.memory import (
    ReflexionTrigger,
    ReplanSignal,
    RuntimeMemoryEntry,
    RuntimeMemoryEntryType,
    RuntimeMemoryQuery,
    RuntimeMemoryRole,
    RuntimeMemoryStore,
)
from rtv2.task_graph.models import ResultRef


class RuntimeMemoryStoreStub(RuntimeMemoryStore):
    def append_entry(self, entry: RuntimeMemoryEntry) -> RuntimeMemoryEntry:
        return entry

    def list_entries_for_run(self, *, task_id: str, run_id: str) -> list[RuntimeMemoryEntry]:
        return []

    def list_entries(self, query: RuntimeMemoryQuery) -> list[RuntimeMemoryEntry]:
        return []

    def get_latest_entries(self, query: RuntimeMemoryQuery) -> list[RuntimeMemoryEntry]:
        return []


class RuntimeMemoryModelsTests(unittest.TestCase):
    def test_context_entry_accepts_minimal_required_fields(self):
        entry = RuntimeMemoryEntry(
            entry_id="entry-1",
            task_id="task-1",
            run_id="run-1",
            step_id="step-1",
            node_id="node-1",
            entry_type=RuntimeMemoryEntryType.CONTEXT,
            role=RuntimeMemoryRole.ASSISTANT,
            content="observed current state",
            created_at="2026-04-28T20:00:00+08:00",
            related_result_refs=[ResultRef(ref_id="ref-1", ref_type="artifact")],
        )

        self.assertEqual(entry.entry_type, RuntimeMemoryEntryType.CONTEXT)
        self.assertEqual(entry.role, RuntimeMemoryRole.ASSISTANT)
        self.assertEqual(entry.replan_signal, ReplanSignal.NONE)
        self.assertEqual(entry.related_result_refs[0].ref_id, "ref-1")

    def test_reflexion_entry_requires_structured_reflexion_fields(self):
        entry = RuntimeMemoryEntry(
            entry_id="entry-1",
            task_id="task-1",
            run_id="run-1",
            step_id="step-1",
            node_id="node-1",
            entry_type=RuntimeMemoryEntryType.REFLEXION,
            role=RuntimeMemoryRole.SYSTEM,
            content="current approach failed due to missing prerequisite",
            reflexion_trigger=ReflexionTrigger.FAILED,
            reflexion_reason="missing prerequisite",
            next_try_hint="inspect dependency chain first",
            replan_signal=ReplanSignal.SUGGESTED,
            created_at="2026-04-28T20:00:00+08:00",
        )

        self.assertEqual(entry.entry_type, RuntimeMemoryEntryType.REFLEXION)
        self.assertEqual(entry.reflexion_trigger, ReflexionTrigger.FAILED)
        self.assertEqual(entry.replan_signal, ReplanSignal.SUGGESTED)

    def test_reflexion_entry_rejects_missing_trigger(self):
        with self.assertRaises(ValueError):
            RuntimeMemoryEntry(
                entry_id="entry-1",
                task_id="task-1",
                run_id="run-1",
                step_id="step-1",
                node_id="node-1",
                entry_type=RuntimeMemoryEntryType.REFLEXION,
                role=RuntimeMemoryRole.SYSTEM,
                content="need reflexion details",
                reflexion_reason="missing trigger",
                created_at="2026-04-28T20:00:00+08:00",
            )

    def test_context_entry_rejects_reflexion_only_fields(self):
        with self.assertRaises(ValueError):
            RuntimeMemoryEntry(
                entry_id="entry-1",
                task_id="task-1",
                run_id="run-1",
                step_id="step-1",
                node_id="node-1",
                entry_type=RuntimeMemoryEntryType.CONTEXT,
                role=RuntimeMemoryRole.ASSISTANT,
                content="normal context entry",
                reflexion_reason="should not exist here",
                created_at="2026-04-28T20:00:00+08:00",
            )

    def test_runtime_memory_query_rejects_non_positive_limit(self):
        with self.assertRaises(ValueError):
            RuntimeMemoryQuery(limit=0)

    def test_runtime_memory_store_contract_can_be_subclassed(self):
        store = RuntimeMemoryStoreStub()

        query = RuntimeMemoryQuery(run_id="run-1", limit=5)
        self.assertEqual(store.list_entries(query), [])
        self.assertEqual(store.get_latest_entries(query), [])


if __name__ == "__main__":
    unittest.main()
