import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.task_graph.models import TaskGraphState, TaskGraphStatus


class TaskGraphStateTests(unittest.TestCase):
    def test_task_graph_state_keeps_minimal_formal_fields(self):
        graph_state = TaskGraphState(
            graph_id="graph-1",
            nodes=[{"node_id": "node-1"}],
            active_node_id="node-1",
            graph_status=TaskGraphStatus.BLOCKED,
            version=3,
        )

        self.assertEqual(graph_state.graph_id, "graph-1")
        self.assertEqual(graph_state.nodes[0]["node_id"], "node-1")
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
