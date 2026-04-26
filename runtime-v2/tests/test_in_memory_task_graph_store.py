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
