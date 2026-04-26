import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.task_graph.models import NodeStatus, TaskGraphNode, TaskGraphState, TaskGraphStatus


class TaskGraphStateTests(unittest.TestCase):
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
