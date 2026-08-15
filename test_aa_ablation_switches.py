import unittest

import networkx as nx

import single_path_routing as spr


class APlanningAblationSwitchTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.DiGraph()
        self.graph.add_node("u", type="passageway", people=0, area=10)
        self.graph.add_node("v", type="passageway", people=0, area=10)
        self.graph.add_edge("u", "v", length=1.0, capacity=10.0)
        self.resource = spr.edge_resource_id(self.graph, "u", "v")
        self.graph.graph["_resource_queues"] = {self.resource: 8.0}

    def test_resource_wait_ablation_returns_zero_without_changing_physical_queue(self):
        self.graph.graph["aa_resource_wait_enabled"] = False
        self.assertEqual(
            spr.aa_planning_resource_queue(
                self.graph, self.resource, target_time=10.0, predictive=True
            ),
            0.0,
        )
        self.assertEqual(spr.current_resource_queue(self.graph, self.resource), 8.0)

    def test_prediction_ablation_uses_current_queue(self):
        self.graph.graph["aa_resource_queue_prediction_enabled"] = False
        self.assertEqual(
            spr.aa_planning_resource_queue(
                self.graph, self.resource, target_time=10.0, predictive=True
            ),
            8.0,
        )

    def test_spatial_wait_ablation_does_not_call_bound_predictor(self):
        self.graph.graph["aa_spatial_wait_enabled"] = False
        original = spr._AA_PREDICTED_SPATIAL_WAIT
        spr._AA_PREDICTED_SPATIAL_WAIT = lambda *args, **kwargs: 99.0
        try:
            self.assertEqual(
                spr.aa_planning_spatial_wait(
                    self.graph, "v", eta=10.0, amount=1
                ),
                0.0,
            )
        finally:
            spr._AA_PREDICTED_SPATIAL_WAIT = original


if __name__ == "__main__":
    unittest.main()
