import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.observability.events import (
    emit_event,
    emit_memory_decision_made,
    emit_memory_retrieved,
    emit_memory_triggered,
)
from app.observability.store import EventStore, SystemMemoryEventStore


class MemoryObservabilityEventsTests(unittest.TestCase):
    def test_memory_events_are_persisted_to_sqlite(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            event_store = EventStore(events_path=str(base / "events.jsonl"))
            memory_store = SystemMemoryEventStore(db_path=str(base / "system_memory.db"))

            triggered = emit_event(
                task_id="task_1",
                run_id="run_1",
                actor="main",
                role="general",
                event_type="memory_triggered",
                payload={"stage": "pull_request", "context_id": "pr_123", "risk_level": "P1"},
                store=event_store,
                system_memory_store=memory_store,
            )
            emit_event(
                task_id="task_1",
                run_id="run_1",
                actor="main",
                role="general",
                event_type="memory_retrieved",
                payload={"trigger_event_id": triggered["event_id"], "memory_id": "mem_abc", "score": 0.93},
                store=event_store,
                system_memory_store=memory_store,
            )
            emit_event(
                task_id="task_1",
                run_id="run_1",
                actor="reviewer",
                role="reviewer",
                event_type="memory_decision_made",
                payload={
                    "trigger_event_id": triggered["event_id"],
                    "memory_id": "mem_abc",
                    "decision": "accepted",
                    "reason": "matched current risk",
                },
                store=event_store,
                system_memory_store=memory_store,
            )

            conn = sqlite3.connect(str(base / "system_memory.db"))
            try:
                trigger_cnt = conn.execute("SELECT COUNT(*) FROM memory_trigger_event").fetchone()[0]
                retrieval_cnt = conn.execute("SELECT COUNT(*) FROM memory_retrieval_event").fetchone()[0]
                decision_cnt = conn.execute("SELECT COUNT(*) FROM memory_decision_event").fetchone()[0]
                self.assertEqual(trigger_cnt, 1)
                self.assertEqual(retrieval_cnt, 1)
                self.assertEqual(decision_cnt, 1)

                row = conn.execute(
                    "SELECT stage, context_id, risk_level FROM memory_trigger_event LIMIT 1"
                ).fetchone()
                self.assertEqual(row, ("pull_request", "pr_123", "P1"))
            finally:
                conn.close()

    def test_non_memory_event_does_not_write_memory_tables(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            event_store = EventStore(events_path=str(base / "events.jsonl"))
            memory_store = SystemMemoryEventStore(db_path=str(base / "system_memory.db"))

            emit_event(
                task_id="task_2",
                run_id="run_2",
                actor="main",
                role="general",
                event_type="task_started",
                store=event_store,
                system_memory_store=memory_store,
            )

            conn = sqlite3.connect(str(base / "system_memory.db"))
            try:
                trigger_cnt = conn.execute("SELECT COUNT(*) FROM memory_trigger_event").fetchone()[0]
                self.assertEqual(trigger_cnt, 0)
            finally:
                conn.close()

    def test_memory_helper_apis_write_expected_rows(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            event_store = EventStore(events_path=str(base / "events.jsonl"))
            memory_store = SystemMemoryEventStore(db_path=str(base / "system_memory.db"))

            triggered = emit_memory_triggered(
                task_id="task_3",
                run_id="run_3",
                actor="main",
                role="general",
                stage="pre_release",
                context_id="release_42",
                risk_level="P0",
                store=event_store,
                system_memory_store=memory_store,
            )
            emit_memory_retrieved(
                task_id="task_3",
                run_id="run_3",
                actor="main",
                role="general",
                trigger_event_id=triggered["event_id"],
                memory_id="mem_release_guard_1",
                score=0.88,
                store=event_store,
                system_memory_store=memory_store,
            )
            emit_memory_decision_made(
                task_id="task_3",
                run_id="run_3",
                actor="release_owner",
                role="reviewer",
                trigger_event_id=triggered["event_id"],
                memory_id="mem_release_guard_1",
                decision="rejected",
                reason="already covered by change window policy",
                store=event_store,
                system_memory_store=memory_store,
            )

            conn = sqlite3.connect(str(base / "system_memory.db"))
            try:
                decision = conn.execute(
                    "SELECT decision, reason FROM memory_decision_event LIMIT 1"
                ).fetchone()
                self.assertEqual(decision, ("rejected", "already covered by change window policy"))
            finally:
                conn.close()

    def test_task_finished_does_not_auto_emit_memory_trigger(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            event_store = EventStore(events_path=str(base / "events.jsonl"))
            memory_store = SystemMemoryEventStore(db_path=str(base / "system_memory.db"))

            with patch(
                "app.observability.postmortem.generate_postmortem",
                return_value={"success": True, "output_path": "/tmp/postmortem_x.md"},
            ):
                emit_event(
                    task_id="task_4",
                    run_id="run_4",
                    actor="main",
                    role="general",
                    event_type="task_finished",
                    status="error",
                    store=event_store,
                    system_memory_store=memory_store,
                )

            conn = sqlite3.connect(str(base / "system_memory.db"))
            try:
                trigger_cnt = conn.execute("SELECT COUNT(*) FROM memory_trigger_event").fetchone()[0]
                self.assertEqual(trigger_cnt, 0)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
