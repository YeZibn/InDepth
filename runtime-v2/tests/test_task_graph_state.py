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


class TaskGraphStateTests(unittest.TestCase):
    def test_node_patch_keeps_runtime_updatable_fields(self):
        patch = NodePatch(
            node_id="node-1",
            node_status=NodeStatus.RUNNING,
            owner="main",
            dependencies=["node-0"],
            order=3,
            artifacts=["artifact://plan"],
            evidence=["evidence://trace"],
            notes=["Execution resumed."],
            block_reason="awaiting_input",
            failure_reason="tool_error",
        )

        self.assertEqual(patch.node_id, "node-1")
        self.assertEqual(patch.node_status, NodeStatus.RUNNING)
        self.assertEqual(patch.owner, "main")
        self.assertEqual(patch.dependencies, ["node-0"])
        self.assertEqual(patch.order, 3)
        self.assertEqual(patch.artifacts, ["artifact://plan"])
        self.assertEqual(patch.evidence, ["evidence://trace"])
        self.assertEqual(patch.notes, ["Execution resumed."])
        self.assertEqual(patch.block_reason, "awaiting_input")
        self.assertEqual(patch.failure_reason, "tool_error")

    def test_node_patch_defaults_to_no_field_updates(self):
        patch = NodePatch(node_id="node-2")

        self.assertEqual(patch.node_id, "node-2")
        self.assertIsNone(patch.node_status)
        self.assertIsNone(patch.owner)
        self.assertIsNone(patch.dependencies)
        self.assertIsNone(patch.order)
        self.assertIsNone(patch.artifacts)
        self.assertIsNone(patch.evidence)
        self.assertIsNone(patch.notes)
        self.assertIsNone(patch.block_reason)
        self.assertIsNone(patch.failure_reason)

    def test_task_graph_patch_keeps_minimal_formal_fields(self):
        patch = TaskGraphPatch(
            node_updates=[NodePatch(node_id="node-1", node_status=NodeStatus.COMPLETED)],
            new_nodes=[
                TaskGraphNode(
                    node_id="node-2",
                    graph_id="graph-1",
                    name="Verify result",
                    kind="verification",
                    node_status=NodeStatus.READY,
                )
            ],
            active_node_id="node-2",
            graph_status=TaskGraphStatus.ACTIVE,
        )

        self.assertEqual(patch.node_updates[0].node_id, "node-1")
        self.assertEqual(patch.node_updates[0].node_status, NodeStatus.COMPLETED)
        self.assertEqual(patch.new_nodes[0].node_id, "node-2")
        self.assertEqual(patch.active_node_id, "node-2")
        self.assertEqual(patch.graph_status, TaskGraphStatus.ACTIVE)

    def test_task_graph_patch_defaults_to_no_graph_changes(self):
        patch = TaskGraphPatch()

        self.assertEqual(patch.node_updates, [])
        self.assertEqual(patch.new_nodes, [])
        self.assertIsNone(patch.active_node_id)
        self.assertIsNone(patch.graph_status)

    def test_task_graph_node_keeps_minimal_formal_fields(self):
        node = TaskGraphNode(
            node_id="node-1",
            graph_id="graph-1",
            name="Inspect runtime state",
            kind="analysis",
            description="Inspect the current runtime state model.",
            node_status=NodeStatus.READY,
            owner="main",
            dependencies=["node-0"],
            order=2,
            artifacts=["artifact://summary"],
            evidence=["evidence://state-scan"],
            notes=["Waiting for execution."],
            block_reason="",
            failure_reason="",
        )

        self.assertEqual(node.node_id, "node-1")
        self.assertEqual(node.graph_id, "graph-1")
        self.assertEqual(node.name, "Inspect runtime state")
        self.assertEqual(node.kind, "analysis")
        self.assertEqual(node.description, "Inspect the current runtime state model.")
        self.assertEqual(node.node_status, NodeStatus.READY)
        self.assertEqual(node.owner, "main")
        self.assertEqual(node.dependencies, ["node-0"])
        self.assertEqual(node.order, 2)
        self.assertEqual(node.artifacts, ["artifact://summary"])
        self.assertEqual(node.evidence, ["evidence://state-scan"])
        self.assertEqual(node.notes, ["Waiting for execution."])
        self.assertEqual(node.block_reason, "")
        self.assertEqual(node.failure_reason, "")

    def test_task_graph_node_defaults_to_pending_with_empty_outputs(self):
        node = TaskGraphNode(
            node_id="node-2",
            graph_id="graph-2",
            name="Continue task",
            kind="execution",
        )

        self.assertEqual(node.description, "")
        self.assertEqual(node.node_status, NodeStatus.PENDING)
        self.assertEqual(node.owner, "")
        self.assertEqual(node.dependencies, [])
        self.assertEqual(node.order, 0)
        self.assertEqual(node.artifacts, [])
        self.assertEqual(node.evidence, [])
        self.assertEqual(node.notes, [])
        self.assertEqual(node.block_reason, "")
        self.assertEqual(node.failure_reason, "")

    def test_task_graph_state_keeps_minimal_formal_fields(self):
        graph_state = TaskGraphState(
            graph_id="graph-1",
            nodes=[
                TaskGraphNode(
                    node_id="node-1",
                    graph_id="graph-1",
                    name="Inspect runtime state",
                    kind="analysis",
                )
            ],
            active_node_id="node-1",
            graph_status=TaskGraphStatus.BLOCKED,
            version=3,
        )

        self.assertEqual(graph_state.graph_id, "graph-1")
        self.assertEqual(graph_state.nodes[0].node_id, "node-1")
        self.assertEqual(graph_state.active_node_id, "node-1")
        self.assertEqual(graph_state.graph_status, TaskGraphStatus.BLOCKED)
        self.assertEqual(graph_state.version, 3)

    def test_task_graph_state_defaults_to_empty_active_graph(self):
        graph_state = TaskGraphState(graph_id="graph-2")

        self.assertEqual(graph_state.graph_id, "graph-2")
        self.assertEqual(graph_state.nodes, [])
        self.assertEqual(graph_state.active_node_id, "")
        self.assertEqual(graph_state.graph_status, TaskGraphStatus.ACTIVE)
        self.assertEqual(graph_state.version, 1)


if __name__ == "__main__":
    unittest.main()
