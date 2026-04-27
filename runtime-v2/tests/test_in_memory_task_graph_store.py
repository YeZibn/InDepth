import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.task_graph.models import (
    NodePatch,
    NodeStatus,
    ResultRef,
    TaskGraphNode,
    TaskGraphPatch,
    TaskGraphState,
    TaskGraphStatus,
)
from rtv2.task_graph.store import InMemoryTaskGraphStore


class InMemoryTaskGraphStoreTests(unittest.TestCase):
    def test_save_graph_and_get_graph_use_snapshot_semantics(self):
        store = InMemoryTaskGraphStore()
        graph = TaskGraphState(
            graph_id="graph-1",
            nodes=[
                TaskGraphNode(
                    node_id="node-1",
                    graph_id="graph-1",
                    name="Inspect",
                    kind="analysis",
                )
            ],
            active_node_id="node-1",
        )

        store.save_graph(graph)
        graph.nodes[0].name = "Mutated outside store"

        saved_graph = store.get_graph("graph-1")
        self.assertIsNotNone(saved_graph)
        self.assertEqual(saved_graph.nodes[0].name, "Inspect")

    def test_apply_patch_updates_nodes_adds_new_nodes_and_bumps_version(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-2",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-2",
                        name="Execute",
                        kind="execution",
                        node_status=NodeStatus.RUNNING,
                    )
                ],
                active_node_id="node-1",
                graph_status=TaskGraphStatus.ACTIVE,
                version=2,
            )
        )

        updated_graph = store.apply_patch(
            "graph-2",
            TaskGraphPatch(
                node_updates=[
                    NodePatch(
                        node_id="node-1",
                        node_status=NodeStatus.COMPLETED,
                        notes=["Execution completed."],
                    )
                ],
                new_nodes=[
                    TaskGraphNode(
                        node_id="node-2",
                        graph_id="graph-2",
                        name="Verify",
                        kind="verification",
                        node_status=NodeStatus.READY,
                    )
                ],
                active_node_id="node-2",
                graph_status=TaskGraphStatus.ACTIVE,
            ),
        )

        self.assertEqual(updated_graph.version, 3)
        self.assertEqual(updated_graph.active_node_id, "node-2")
        self.assertEqual(updated_graph.nodes[0].node_status, NodeStatus.COMPLETED)
        self.assertEqual(updated_graph.nodes[0].notes, ["Execution completed."])
        self.assertEqual(updated_graph.nodes[1].node_id, "node-2")
        self.assertEqual(updated_graph.nodes[1].node_status, NodeStatus.READY)

    def test_apply_patch_merges_notes_artifacts_and_evidence_with_append_semantics(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-merge",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-merge",
                        name="Execute",
                        kind="execution",
                        notes=["Existing note"],
                        artifacts=[
                            ResultRef(ref_id="artifact-1", ref_type="file", title="Old artifact"),
                        ],
                        evidence=[
                            ResultRef(ref_id="evidence-1", ref_type="search", title="Old evidence"),
                        ],
                        block_reason="old block",
                        failure_reason="old failure",
                    )
                ],
            )
        )

        updated_graph = store.apply_patch(
            "graph-merge",
            TaskGraphPatch(
                node_updates=[
                    NodePatch(
                        node_id="node-1",
                        notes=["", "New note"],
                        artifacts=[
                            ResultRef(ref_id="artifact-1", ref_type="file", title="Duplicate artifact"),
                            ResultRef(ref_id="artifact-2", ref_type="file", title="New artifact"),
                        ],
                        evidence=[
                            ResultRef(ref_id="evidence-1", ref_type="search", title="Duplicate evidence"),
                            ResultRef(ref_id="evidence-2", ref_type="search", title="New evidence"),
                        ],
                        block_reason="new block",
                        failure_reason="new failure",
                    )
                ]
            ),
        )

        updated_node = updated_graph.nodes[0]
        self.assertEqual(updated_node.notes, ["Existing note", "New note"])
        self.assertEqual([item.ref_id for item in updated_node.artifacts], ["artifact-1", "artifact-2"])
        self.assertEqual([item.ref_id for item in updated_node.evidence], ["evidence-1", "evidence-2"])
        self.assertEqual(updated_node.block_reason, "new block")
        self.assertEqual(updated_node.failure_reason, "new failure")

    def test_apply_patch_treats_empty_patch_collections_as_noop_merge(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-empty-merge",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-empty-merge",
                        name="Execute",
                        kind="execution",
                        notes=["Existing note"],
                        artifacts=[ResultRef(ref_id="artifact-1", ref_type="file")],
                        evidence=[ResultRef(ref_id="evidence-1", ref_type="search")],
                    )
                ],
            )
        )

        updated_graph = store.apply_patch(
            "graph-empty-merge",
            TaskGraphPatch(
                node_updates=[
                    NodePatch(
                        node_id="node-1",
                        notes=[],
                        artifacts=[],
                        evidence=[],
                    )
                ]
            ),
        )

        updated_node = updated_graph.nodes[0]
        self.assertEqual(updated_node.notes, ["Existing note"])
        self.assertEqual([item.ref_id for item in updated_node.artifacts], ["artifact-1"])
        self.assertEqual([item.ref_id for item in updated_node.evidence], ["evidence-1"])

    def test_apply_patch_raises_when_blocked_node_patch_has_no_block_reason(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-blocked-patch",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-blocked-patch",
                        name="Execute",
                        kind="execution",
                        node_status=NodeStatus.RUNNING,
                    )
                ],
            )
        )

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-blocked-patch",
                TaskGraphPatch(
                    node_updates=[
                        NodePatch(
                            node_id="node-1",
                            node_status=NodeStatus.BLOCKED,
                        )
                    ]
                ),
            )

    def test_apply_patch_raises_when_failed_node_patch_has_no_failure_reason(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-failed-patch",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-failed-patch",
                        name="Execute",
                        kind="execution",
                        node_status=NodeStatus.RUNNING,
                    )
                ],
            )
        )

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-failed-patch",
                TaskGraphPatch(
                    node_updates=[
                        NodePatch(
                            node_id="node-1",
                            node_status=NodeStatus.FAILED,
                        )
                    ]
                ),
            )

    def test_apply_patch_raises_when_patch_artifact_ref_id_is_empty(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-invalid-artifact",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-invalid-artifact",
                        name="Execute",
                        kind="execution",
                    )
                ],
            )
        )

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-invalid-artifact",
                TaskGraphPatch(
                    node_updates=[
                        NodePatch(
                            node_id="node-1",
                            artifacts=[ResultRef(ref_id="", ref_type="file")],
                        )
                    ]
                ),
            )

    def test_apply_patch_raises_when_patch_evidence_ref_id_is_empty(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-invalid-evidence",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-invalid-evidence",
                        name="Execute",
                        kind="execution",
                    )
                ],
            )
        )

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-invalid-evidence",
                TaskGraphPatch(
                    node_updates=[
                        NodePatch(
                            node_id="node-1",
                            evidence=[ResultRef(ref_id="", ref_type="search")],
                        )
                    ]
                ),
            )

    def test_apply_patch_raises_when_new_blocked_node_has_no_block_reason(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(TaskGraphState(graph_id="graph-new-blocked"))

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-new-blocked",
                TaskGraphPatch(
                    new_nodes=[
                        TaskGraphNode(
                            node_id="node-1",
                            graph_id="graph-new-blocked",
                            name="Blocked",
                            kind="execution",
                            node_status=NodeStatus.BLOCKED,
                        )
                    ]
                ),
            )

    def test_apply_patch_raises_when_new_node_reference_has_empty_ref_id(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(TaskGraphState(graph_id="graph-new-ref"))

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-new-ref",
                TaskGraphPatch(
                    new_nodes=[
                        TaskGraphNode(
                            node_id="node-1",
                            graph_id="graph-new-ref",
                            name="New",
                            kind="execution",
                            artifacts=[ResultRef(ref_id="", ref_type="file")],
                        )
                    ]
                ),
            )

    def test_apply_patch_allows_pending_to_ready_transition(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-pending-ready",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-pending-ready",
                        name="Pending",
                        kind="execution",
                        node_status=NodeStatus.PENDING,
                    )
                ],
            )
        )

        updated_graph = store.apply_patch(
            "graph-pending-ready",
            TaskGraphPatch(
                node_updates=[NodePatch(node_id="node-1", node_status=NodeStatus.READY)]
            ),
        )

        self.assertEqual(updated_graph.nodes[0].node_status, NodeStatus.READY)

    def test_apply_patch_allows_running_to_blocked_transition_with_reason(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-running-blocked",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-running-blocked",
                        name="Running",
                        kind="execution",
                        node_status=NodeStatus.RUNNING,
                    )
                ],
            )
        )

        updated_graph = store.apply_patch(
            "graph-running-blocked",
            TaskGraphPatch(
                node_updates=[
                    NodePatch(
                        node_id="node-1",
                        node_status=NodeStatus.BLOCKED,
                        block_reason="waiting",
                    )
                ]
            ),
        )

        self.assertEqual(updated_graph.nodes[0].node_status, NodeStatus.BLOCKED)
        self.assertEqual(updated_graph.nodes[0].block_reason, "waiting")

    def test_apply_patch_allows_running_to_failed_transition_with_reason(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-running-failed",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-running-failed",
                        name="Running",
                        kind="execution",
                        node_status=NodeStatus.RUNNING,
                    )
                ],
            )
        )

        updated_graph = store.apply_patch(
            "graph-running-failed",
            TaskGraphPatch(
                node_updates=[
                    NodePatch(
                        node_id="node-1",
                        node_status=NodeStatus.FAILED,
                        failure_reason="tool_error",
                    )
                ]
            ),
        )

        self.assertEqual(updated_graph.nodes[0].node_status, NodeStatus.FAILED)
        self.assertEqual(updated_graph.nodes[0].failure_reason, "tool_error")

    def test_apply_patch_allows_blocked_to_ready_transition(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-blocked-ready",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-blocked-ready",
                        name="Blocked",
                        kind="execution",
                        node_status=NodeStatus.BLOCKED,
                        block_reason="waiting",
                    )
                ],
            )
        )

        updated_graph = store.apply_patch(
            "graph-blocked-ready",
            TaskGraphPatch(
                node_updates=[NodePatch(node_id="node-1", node_status=NodeStatus.READY)]
            ),
        )

        self.assertEqual(updated_graph.nodes[0].node_status, NodeStatus.READY)

    def test_apply_patch_raises_when_transition_is_not_allowed(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-illegal-transition",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-illegal-transition",
                        name="Ready",
                        kind="execution",
                        node_status=NodeStatus.READY,
                    )
                ],
            )
        )

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-illegal-transition",
                TaskGraphPatch(
                    node_updates=[NodePatch(node_id="node-1", node_status=NodeStatus.COMPLETED)]
                ),
            )

    def test_apply_patch_raises_when_failed_to_ready_transition_is_requested(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-failed-ready",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-failed-ready",
                        name="Failed",
                        kind="execution",
                        node_status=NodeStatus.FAILED,
                        failure_reason="old_failure",
                    )
                ],
            )
        )

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-failed-ready",
                TaskGraphPatch(
                    node_updates=[NodePatch(node_id="node-1", node_status=NodeStatus.READY)]
                ),
            )

    def test_get_node_get_active_node_and_list_nodes_read_saved_graph(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-3",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-3",
                        name="A",
                        kind="analysis",
                    ),
                    TaskGraphNode(
                        node_id="node-2",
                        graph_id="graph-3",
                        name="B",
                        kind="execution",
                    ),
                ],
                active_node_id="node-2",
            )
        )

        self.assertEqual(store.get_node("graph-3", "node-1").name, "A")
        self.assertEqual(store.get_active_node("graph-3").node_id, "node-2")
        self.assertEqual([node.node_id for node in store.list_nodes("graph-3")], ["node-1", "node-2"])

    def test_apply_patch_raises_when_graph_is_missing(self):
        store = InMemoryTaskGraphStore()

        with self.assertRaises(KeyError):
            store.apply_patch("missing", TaskGraphPatch())

    def test_apply_patch_raises_when_node_update_targets_missing_node(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(TaskGraphState(graph_id="graph-4"))

        with self.assertRaises(KeyError):
            store.apply_patch(
                "graph-4",
                TaskGraphPatch(node_updates=[NodePatch(node_id="missing", node_status=NodeStatus.READY)]),
            )

    def test_apply_patch_raises_when_new_node_id_already_exists(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(
            TaskGraphState(
                graph_id="graph-5",
                nodes=[
                    TaskGraphNode(
                        node_id="node-1",
                        graph_id="graph-5",
                        name="Existing",
                        kind="analysis",
                    )
                ],
            )
        )

        with self.assertRaises(ValueError):
            store.apply_patch(
                "graph-5",
                TaskGraphPatch(
                    new_nodes=[
                        TaskGraphNode(
                            node_id="node-1",
                            graph_id="graph-5",
                            name="Duplicate",
                            kind="analysis",
                        )
                    ]
                ),
            )

    def test_apply_patch_raises_when_active_node_id_does_not_exist_after_update(self):
        store = InMemoryTaskGraphStore()
        store.save_graph(TaskGraphState(graph_id="graph-6"))

        with self.assertRaises(KeyError):
            store.apply_patch(
                "graph-6",
                TaskGraphPatch(active_node_id="missing-node"),
            )


if __name__ == "__main__":
    unittest.main()
