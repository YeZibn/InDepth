import sys
import unittest
from pathlib import Path
from typing import get_type_hints


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtv2.task_graph.models import TaskGraphNode, TaskGraphPatch, TaskGraphState
from rtv2.task_graph.store import TaskGraphStore


class TaskGraphStoreInterfaceTests(unittest.TestCase):
    def test_task_graph_store_exposes_minimal_protocol_methods(self):
        self.assertTrue(hasattr(TaskGraphStore, "get_graph"))
        self.assertTrue(hasattr(TaskGraphStore, "save_graph"))
        self.assertTrue(hasattr(TaskGraphStore, "apply_patch"))
        self.assertTrue(hasattr(TaskGraphStore, "get_node"))
        self.assertTrue(hasattr(TaskGraphStore, "get_active_node"))
        self.assertTrue(hasattr(TaskGraphStore, "list_nodes"))

    def test_task_graph_store_method_annotations_match_contract(self):
        get_graph_hints = get_type_hints(TaskGraphStore.get_graph)
        save_graph_hints = get_type_hints(TaskGraphStore.save_graph)
        apply_patch_hints = get_type_hints(TaskGraphStore.apply_patch)
        get_node_hints = get_type_hints(TaskGraphStore.get_node)
        get_active_node_hints = get_type_hints(TaskGraphStore.get_active_node)
        list_nodes_hints = get_type_hints(TaskGraphStore.list_nodes)

        self.assertEqual(get_graph_hints["graph_id"], str)
        self.assertEqual(get_graph_hints["return"], TaskGraphState | None)

        self.assertEqual(save_graph_hints["graph"], TaskGraphState)
        self.assertEqual(save_graph_hints["return"], type(None))

        self.assertEqual(apply_patch_hints["graph_id"], str)
        self.assertEqual(apply_patch_hints["patch"], TaskGraphPatch)
        self.assertEqual(apply_patch_hints["return"], TaskGraphState)

        self.assertEqual(get_node_hints["graph_id"], str)
        self.assertEqual(get_node_hints["node_id"], str)
        self.assertEqual(get_node_hints["return"], TaskGraphNode | None)

        self.assertEqual(get_active_node_hints["graph_id"], str)
        self.assertEqual(get_active_node_hints["return"], TaskGraphNode | None)

        self.assertEqual(list_nodes_hints["graph_id"], str)
        self.assertEqual(list_nodes_hints["return"], list[TaskGraphNode])


if __name__ == "__main__":
    unittest.main()
