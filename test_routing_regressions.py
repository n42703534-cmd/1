import math
import inspect
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import networkx as nx

import network as net
import single_path_routing as spr
import algorithm_comparison as comparison


class GateServiceBacklogRegressionTests(unittest.TestCase):
    def _graph(self):
        graph = nx.DiGraph()
        graph.add_node("upstream", type="area", people=3, area=10)
        graph.add_node("gate", type="gate", people=2, area=1, capacity=1)
        graph.add_node("downstream", type="area", people=0, area=10)
        graph.add_edge("upstream", "gate", length=1, capacity=10)
        graph.add_edge("gate", "downstream", length=1, capacity=10)
        graph.graph["_transit_queue"] = [
            {"u": "upstream", "v": "gate", "amount": 2, "arrive_time": 10}
        ]
        return graph

    def test_gate_two_blocked_three_transit_two_is_five(self):
        graph = self._graph()
        graph.graph["_gate_backlog_test_records"] = {
            "gate": {"gate": [{"batch_id": "g", "amount": 2}]},
            "upstream": {"gate": [{"batch_id": "u", "amount": 3}]},
        }
        self.assertEqual(
            net.gate_service_backlog_state(graph, "gate")["backlog_people"],
            5,
        )

    def test_upstream_to_gate_migration_does_not_duplicate(self):
        graph = self._graph()
        graph.graph["_gate_backlog_test_records"] = {
            "gate": {"gate": [{"batch_id": "g", "amount": 2}]},
            "upstream": {"gate": [{"batch_id": "u", "amount": 3}]},
        }
        before = net.gate_service_backlog_state(graph, "gate")["backlog_people"]
        graph.graph["_gate_backlog_test_records"] = {
            "gate": {"gate": [
                {"batch_id": "g", "amount": 2},
                {"batch_id": "u", "amount": 3},
            ]},
            "upstream": {"gate": []},
        }
        after = net.gate_service_backlog_state(graph, "gate")["backlog_people"]
        self.assertEqual((before, after), (5, 5))

    def test_served_batch_is_removed_immediately(self):
        graph = self._graph()
        graph.graph["_gate_backlog_test_records"] = {
            "gate": {"gate": [{"batch_id": "served", "amount": 2}]},
            "upstream": {"gate": []},
        }
        self.assertEqual(
            net.gate_service_backlog_state(graph, "gate")["backlog_people"], 2
        )
        graph.graph["_gate_backlog_test_records"]["gate"]["gate"] = []
        graph.nodes["gate"]["people"] = 0
        self.assertEqual(
            net.gate_service_backlog_state(graph, "gate")["backlog_people"], 0
        )

    def test_gate_routing_queue_uses_resource_queue_not_node_people(self):
        graph = self._graph()
        graph.graph["_resource_queues"] = {("facility", "gate"): 15}
        graph.nodes["gate"]["people"] = 2
        graph.graph["_gate_backlog_test_records"] = {
            "gate": {"gate": [{"batch_id": "g", "amount": 2}]},
            "upstream": {"gate": []},
        }
        self.assertEqual(
            spr.current_resource_queue(graph, ("facility", "gate")), 15
        )

    def test_improved_gate_state_uses_same_routing_queue(self):
        graph = self._graph()
        graph.graph["_resource_queues"] = {("facility", "gate"): 15}
        graph.nodes["gate"]["people"] = 2
        state = net._paper_gate_effective_state(graph, "gate")
        self.assertEqual(state["queue_people"], 15)
        self.assertEqual(state["gate_node_occupancy"], 2)

    def test_gate_capacity_diagnostic_ignores_ordinary_outgoing_flow(self):
        graph = self._graph()
        graph.graph["_last_resource_step_capacity"] = {
            ("facility", "gate"): 1,
        }
        net._update_gate_service_diagnostics(
            graph,
            0.0,
            [
                {"u": "upstream", "v": "gate", "amount": 1},
                {"u": "gate", "v": "downstream", "amount": 2},
            ],
        )
        diagnostics = graph.graph["_gate_service_diagnostics"]["gate"]
        self.assertEqual(diagnostics["gate_service_people"], 1)
        self.assertEqual(diagnostics["scheduled_gate_entry_people"], 1)
        self.assertEqual(diagnostics["gate_capacity_violation_count"], 0)


class GateQueueAreaRegressionTests(unittest.TestCase):
    def test_gate_node_areas_are_explicitly_configured(self):
        graph = net.build_graph()

        self.assertEqual(graph.graph.get("default_gate_area_nodes"), [])
        for gate in (
            "Gate_L2_N_West",
            "Gate_L7_West_Vert",
            "Gate_L16_N1",
            "Gate_L18_E1",
            "Gate_Maglev_W1",
        ):
            data = graph.nodes[gate]
            self.assertEqual(data["area_source"], "configured")
            self.assertEqual(data["area"], data["width"] * 2.0)

    def test_formal_gate_storage_uses_corresponding_queue_area(self):
        graph = net.build_graph()
        jam_density = min(
            float(graph.graph.get("receiving_jam_density", net.HIGH_LOAD_JAM_DENSITY_P_PER_M2)),
            spr.PAPER_DENSITY_JAM,
        )
        for gate in (
            "Gate_L2_N_West",
            "Gate_L7_West_Vert",
            "Gate_L16_N1",
            "Gate_L18_E1",
            "Gate_Maglev_W1",
        ):
            queue_node = graph.graph["gate_queue_area_nodes"][gate]
            self.assertTrue(net.uses_spatial_storage(graph, gate))
            self.assertAlmostEqual(
                net.effective_node_area(graph, gate),
                net.effective_node_area(graph, queue_node),
            )
            self.assertAlmostEqual(
                net._node_storage_capacity(graph, gate),
                net.effective_node_area(graph, queue_node) * jam_density,
            )
            self.assertTrue(
                math.isfinite(net._node_storage_capacity(graph, gate))
            )

    def test_formal_gate_density_uses_queue_area_not_gate_bank_area(self):
        graph = net.build_graph()
        gate = "Gate_L7_West_Vert"
        queue_node = graph.graph["gate_queue_area_nodes"][gate]
        graph.nodes[gate]["people"] = 10
        expected_area = net.effective_node_area(graph, queue_node)
        self.assertAlmostEqual(
            spr.spatial_effective_density(graph, gate),
            10.0 / expected_area,
        )

    def test_l7_gate_queue_area_rewires_gate_approach(self):
        graph = net.build_graph(
            enable_l7_common_hall_vertical_integration=True
        )
        queue_node = "Gate_L7_N_West_Queue"

        self.assertIn(queue_node, graph.nodes)
        self.assertEqual(graph.nodes[queue_node]["type"], "queue_area")
        self.assertEqual(graph.nodes[queue_node]["queue_for_gate"], "Gate_L7_N_West")
        self.assertAlmostEqual(graph.nodes[queue_node]["queue_depth_m"], 5.5)
        self.assertAlmostEqual(graph.nodes[queue_node]["queue_width_m"], 2.77)
        self.assertAlmostEqual(
            graph.nodes[queue_node]["area"],
            graph.nodes[queue_node]["queue_width_m"] * 5.5,
        )
        self.assertEqual(
            graph.nodes[queue_node]["queue_width_source"],
            "configured:queue_width_m",
        )
        self.assertEqual(graph.nodes[queue_node]["gate_unit_count"], 3.0)
        self.assertAlmostEqual(
            graph[queue_node]["Gate_L7_N_West"]["width_limit"], 2.77
        )
        self.assertFalse(spr.is_capacity_service_node(graph, queue_node))
        self.assertTrue(net.uses_spatial_storage(graph, queue_node))

        self.assertFalse(graph.has_edge("Stair_L7_1", "Gate_L7_N_West"))
        self.assertFalse(graph.has_edge("Stair_L7_1", queue_node))
        self.assertTrue(graph.has_edge(
            "Stair_L7_1", "VN_L7_Hall_Arrival"
        ))
        self.assertTrue(graph.has_edge(queue_node, "Gate_L7_N_West"))
        self.assertFalse(graph.has_edge("VN_L7_Hall_Arrival", "Gate_L7_N_West"))
        self.assertTrue(graph.has_edge("VN_L7_Hall_Arrival", queue_node))
        self.assertEqual(
            net.edge_resource_id(graph, queue_node, "Gate_L7_N_West"),
            ("facility", "Gate_L7_N_West"),
        )

    def test_all_line_gate_queues_use_line_specific_depth_and_physical_width(self):
        graph = net.build_graph()
        self.assertEqual(
            graph.graph["gate_queue_area_depth_m_by_line"],
            {
                "L2": 7.0,
                "L7": 5.5,
                "L16": 8.0,
                "L18": 8.0,
                "Maglev": 8.0,
            },
        )
        for gate, expected_width_m, expected_depth_m in (
            ("Gate_L2_N_West", 5.1, 7.0),
            ("Gate_L2_S_West", 8.7, 7.0),
            ("Gate_L7_West_Vert", 5.1, 5.5),
            ("Gate_L16_N1", 3.9, 8.0),
            ("Gate_L18_E1", 7.5, 8.0),
            ("Gate_Maglev_W1", 6.3, 8.0),
            ("Gate_Maglev_E1", 3.9, 8.0),
        ):
            queue_node = f"{gate}_Queue"
            self.assertIn(queue_node, graph.nodes)
            self.assertAlmostEqual(
                graph.nodes[queue_node]["queue_depth_m"], expected_depth_m
            )
            self.assertAlmostEqual(
                graph.nodes[queue_node]["queue_width_m"], expected_width_m
            )
            self.assertAlmostEqual(
                graph.nodes[queue_node]["area"],
                expected_width_m * expected_depth_m,
            )

    def test_only_real_lateral_gate_links_are_active_replan_targets(self):
        graph = net.build_graph()
        l7_queues = {
            "Gate_L7_N_West_Queue",
            "Gate_L7_N_Mid_Queue",
            "Gate_L7_N_East_Queue",
            "Gate_L7_West_Vert_Queue",
        }
        for queue_node in l7_queues:
            current_gate = graph.nodes[queue_node]["queue_for_gate"]
            expected = {
                graph.nodes[other]["queue_for_gate"]
                for other in l7_queues
                if other != queue_node
            }
            self.assertEqual(
                set(graph.nodes[queue_node]["aa_alternative_target_resources"]),
                expected,
            )

        for queue_node in (
            "Gate_L2_N_West_Queue",
            "Gate_L16_N1_Queue",
            "Gate_L18_E1_Queue",
            "Gate_Maglev_W1_Queue",
        ):
            self.assertEqual(
                graph.nodes[queue_node]["aa_alternative_target_resources"],
                (),
            )
            self.assertEqual(
                len(
                    graph.nodes[queue_node][
                        "aa_configured_alternative_target_resources"
                    ]
                ),
                3,
            )

    def test_improved_gate_density_uses_physical_queue_area(self):
        graph = nx.DiGraph()
        graph.graph["gate_queue_area_nodes"] = {"gate": "gate_Queue"}
        graph.graph["_resource_queues"] = {}
        graph.add_node(
            "gate_Queue",
            type="queue_area",
            people=0,
            area=64.0,
            area_source="uniform_gate_queue_depth",
        )
        graph.add_node("gate", type="gate", people=25, area=8.0, capacity=1)
        state = net._paper_gate_effective_state(graph, "gate")
        self.assertAlmostEqual(state["effective_area"], 64.0)
        self.assertAlmostEqual(state["effective_density"], 25.0 / 64.0)
        self.assertFalse(state["exceeded"])

    def test_improved_gate_density_uses_the_more_crowded_physical_footprint(self):
        graph = nx.DiGraph()
        graph.graph["service_node_spatial_storage_mode"] = "queue_area"
        graph.graph["gate_queue_area_nodes"] = {"gate": "gate_Queue"}
        graph.add_node(
            "gate_Queue",
            type="queue_area",
            people=20,
            area=10.0,
            area_source="line_specific_gate_queue_depth",
        )
        graph.add_node("gate", type="gate", people=40, area=2.0, capacity=1)
        state = net._paper_gate_effective_state(graph, "gate")
        self.assertAlmostEqual(state["gate_density"], 4.0)
        self.assertAlmostEqual(state["queue_density"], 2.0)
        self.assertAlmostEqual(state["effective_density"], 4.0)
        self.assertEqual(
            state["density_basis"], "max(gate_density,queue_density)"
        )

    def test_improved_high_cost_uses_gate_queue_area_density(self):
        graph = nx.DiGraph()
        graph.graph["service_node_spatial_storage_mode"] = "queue_area"
        graph.graph["gate_queue_area_nodes"] = {"gate": "q"}
        graph.add_node("u", type="area", people=0, area=10, capacity=10)
        graph.add_node(
            "q",
            type="queue_area",
            people=31,
            area=10,
            capacity=10,
            queue_for_gate="gate",
        )
        graph.add_node("gate", type="gate", people=0, area=1, capacity=1)
        graph.add_node("exit", type="exit", people=0, area=10, capacity=10)
        graph.add_edge("u", "q", length=1, capacity=10)
        graph.add_edge("q", "gate", length=0.2, capacity=1)
        graph.add_edge("gate", "exit", length=1, capacity=10)

        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)

        self.assertIn(("u", "q"), active)
        self.assertNotIn(("q", "gate"), active)
        self.assertTrue(math.isfinite(graph["q"]["gate"]["sim_weight"]))

        graph.nodes["q"]["people"] = 0
        active_after_drain, _ = net._paper_refresh_temporary_high_cost_weights(
            graph
        )
        self.assertNotIn(("u", "q"), active_after_drain)

    def test_improved_high_cost_blocks_upstream_flow_when_gate_is_overloaded(self):
        graph = nx.DiGraph()
        graph.graph["service_node_spatial_storage_mode"] = "queue_area"
        graph.graph["gate_queue_area_nodes"] = {"gate": "q"}
        graph.add_node("u", type="area", people=0, area=10, capacity=10)
        graph.add_node(
            "q",
            type="queue_area",
            people=0,
            area=10,
            capacity=10,
            queue_for_gate="gate",
        )
        graph.add_node("gate", type="gate", people=31, area=10, capacity=1)
        graph.add_node("exit", type="exit", people=0, area=10, capacity=10)
        graph.add_edge("u", "q", length=1, capacity=10)
        graph.add_edge("q", "gate", length=0.2, capacity=1)
        graph.add_edge("gate", "exit", length=1, capacity=10)

        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)

        self.assertIn(("u", "q"), active)
        self.assertNotIn(("q", "gate"), active)
        self.assertEqual(
            graph.graph["_paper_high_cost_control_densities"][("u", "q")],
            3.1,
        )


class L7HallCommonDecisionTests(unittest.TestCase):
    HALL = "VN_L7_Hall_Arrival"
    QUEUES = (
        "Gate_L7_N_West_Queue",
        "Gate_L7_N_Mid_Queue",
        "Gate_L7_N_East_Queue",
        "Gate_L7_West_Vert_Queue",
    )

    def test_hall_and_gate_queues_support_lateral_gate_switching(self):
        graph = net.build_graph()
        successors = tuple(graph.successors(self.HALL))
        self.assertEqual(set(successors), set(self.QUEUES))
        self.assertGreaterEqual(len(successors), 2)
        for queue in self.QUEUES:
            gate = graph.nodes[queue]["queue_for_gate"]
            self.assertEqual(
                set(graph.successors(queue)),
                {gate, *(other for other in self.QUEUES if other != queue)},
            )
            self.assertTrue(graph.nodes[queue]["aa_active_replan_allowed"])
            self.assertEqual(
                set(graph.nodes[queue]["aa_replan_successors"]),
                {gate, *(other for other in self.QUEUES if other != queue)},
            )
            self.assertTrue(all(
                graph.has_edge(queue, other)
                for other in self.QUEUES if other != queue
            ))

    def test_all_l7_verticals_reach_queues_only_through_common_hall(self):
        graph = net.build_graph(
            enable_l7_common_hall_vertical_integration=True
        )
        for upstream in net.L7_HALL_COMMON_DECISION_UPSTREAMS:
            self.assertTrue(graph.has_edge(upstream, self.HALL))
            self.assertGreater(
                float(graph[upstream][self.HALL]["length"]), 0.0
            )
            for queue in self.QUEUES:
                self.assertFalse(graph.has_edge(upstream, queue))
                path = nx.shortest_path(graph, upstream, queue)
                self.assertIn(self.HALL, path)
        audit = graph.graph["l7_common_hall_topology_audit"]
        self.assertEqual(len(audit), 5)
        self.assertTrue(all(
            row["removed_direct_target_count"] == 4
            for row in audit
        ))

    def test_default_full_station_graph_keeps_original_l7_approaches(self):
        graph = net.build_graph()
        self.assertFalse(graph.graph[
            "l7_common_hall_vertical_integration_enabled"
        ])
        self.assertEqual(graph.graph["l7_common_hall_topology_audit"], [])
        for upstream in net.L7_HALL_COMMON_DECISION_UPSTREAMS:
            self.assertFalse(graph.has_edge(upstream, self.HALL))
            self.assertEqual(
                sum(graph.has_edge(upstream, queue) for queue in self.QUEUES),
                len(self.QUEUES),
            )

    def test_explicit_real_l7_integration_trial_conserves_population(self):
        base = net.build_graph(
            enable_l7_common_hall_vertical_integration=True
        )
        line_state = {line_id: 0 for line_id in net.ALL_LINE_IDS}
        for data in base.nodes.values():
            data["people"] = 0
            data["people_dict"] = dict(line_state)
            data["source_group_dict"] = {}

        total_people = 60
        for upstream in net.L7_HALL_COMMON_DECISION_UPSTREAMS:
            base.nodes[upstream]["people"] = 10
            base.nodes[upstream]["people_dict"]["L7"] = 10
            base.nodes[upstream]["source_group_dict"] = {
                "L7_trial": 10
            }
        base.nodes[self.HALL]["people"] = 10
        base.nodes[self.HALL]["people_dict"]["L7"] = 10
        base.nodes[self.HALL]["source_group_dict"] = {
            "L7_trial_hall": 10
        }

        self.assertEqual(
            len(base.graph["l7_common_hall_topology_audit"]), 5
        )
        self.assertTrue(all(
            base.has_edge(upstream, self.HALL)
            for upstream in net.L7_HALL_COMMON_DECISION_UPSTREAMS
        ))

        for method in (
            spr.PAPER_SINGLE_PATH_METHOD,
            spr.OUR_SINGLE_PATH_METHOD,
        ):
            graph = copy.deepcopy(base)
            metrics = net._run_simulation_for_metrics_core(
                graph,
                method,
                {"L7": total_people},
                stop_at_time=60.0,
            )
            evacuated = total_people - float(
                metrics["remaining_people"]
            )
            in_nodes = sum(
                float(data.get("people", 0.0))
                for data in graph.nodes.values()
            )
            in_transit = sum(
                float(item.get("amount", 0.0))
                for item in graph.graph.get("_transit_queue", [])
            )
            self.assertAlmostEqual(
                in_nodes + in_transit + evacuated,
                total_people,
            )
            self.assertGreater(
                len(metrics["l7_hall_common_decision_diagnostics"]),
                0,
            )
            self.assertEqual(
                metrics["l7_hall_common_decision_summary"][
                    "gate_queue_replan_attempt_count"
                ],
                0.0,
            )

    def test_improved_density_only_avoids_over_threshold_west_queue(self):
        graph = net.build_graph()
        graph.graph["improved_gate_queue_term"] = False
        west = self.QUEUES[0]
        west_area = float(graph.nodes[west]["area"])
        graph.nodes[west]["people"] = math.floor(west_area * 3.0) + 1
        for queue in self.QUEUES[1:]:
            graph.nodes[queue]["people"] = 0
        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertIn((self.HALL, west), active)
        for queue in self.QUEUES[1:]:
            self.assertNotIn((self.HALL, queue), active)
        selected = min(
            self.QUEUES,
            key=lambda queue: graph[self.HALL][queue]["sim_weight"],
        )
        self.assertNotEqual(selected, west)

    def test_improved_density_only_recovers_west_edge_next_refresh(self):
        graph = net.build_graph()
        graph.graph["improved_gate_queue_term"] = False
        west = self.QUEUES[0]
        west_area = float(graph.nodes[west]["area"])
        graph.nodes[west]["people"] = math.floor(west_area * 3.0) + 1
        net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertEqual(
            graph[self.HALL][west]["sim_weight"],
            spr.PAPER_TEMPORARY_HIGH_COST,
        )
        graph.nodes[west]["people"] = math.floor(west_area * 3.0)
        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertNotIn((self.HALL, west), active)
        self.assertNotEqual(
            graph[self.HALL][west]["sim_weight"],
            spr.PAPER_TEMPORARY_HIGH_COST,
        )

    def test_improved_keeps_ordinary_l7_off_l2_branch_until_l7_is_congested(self):
        graph = net.build_graph()
        crossline = ("VN_7to2_Entrance", "Transfer_L7-L2_Z")
        self.assertTrue(graph.has_edge(*crossline))

        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertIn(crossline, active)
        self.assertTrue(
            math.isinf(graph[crossline[0]][crossline[1]]["sim_weight"])
        )

        for gate, queue in graph.graph["gate_queue_area_nodes"].items():
            if str(gate).startswith("Gate_L7_"):
                area = float(graph.nodes[queue]["area"])
                graph.nodes[queue]["people"] = math.floor(area * 3.0) + 1
            elif str(gate).startswith("Gate_L2_"):
                graph.nodes[queue]["people"] = 0

        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertNotIn(crossline, active)
        self.assertFalse(
            graph.graph["_improved_ordinary_l7_crossline_blocked"]
        )
        self.assertTrue(
            math.isfinite(graph[crossline[0]][crossline[1]]["sim_weight"])
        )

        west_queue = graph.graph["gate_queue_area_nodes"]["Gate_L2_N_West"]
        graph.nodes[west_queue]["people"] = (
            math.floor(float(graph.nodes[west_queue]["area"]) * 3.0) + 1
        )
        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertNotIn(crossline, active)
        self.assertIn(
            "Gate_L2_N_West",
            graph.graph["_improved_ordinary_l7_crossline_blocked_target_gates"],
        )
        self.assertEqual(
            graph["VN_L7toL2_Hall_Arrival"][west_queue]["sim_weight"],
            spr.PAPER_TEMPORARY_HIGH_COST,
        )
        east_queue = graph.graph["gate_queue_area_nodes"]["Gate_L2_N_East"]
        self.assertTrue(
            math.isfinite(
                graph["VN_L7toL2_Hall_Arrival"][east_queue]["sim_weight"]
            )
        )
        graph.nodes[west_queue]["people"] = 0

        graph.graph.setdefault("_resource_queues", {})[
            ("facility", "Gate_L2_N_West")
        ] = 1.0e6

        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertNotIn(crossline, active)
        self.assertFalse(
            graph.graph["_improved_ordinary_l7_crossline_blocked"]
        )
        self.assertIn(
            "Gate_L2_N_West",
            graph.graph["_improved_ordinary_l7_crossline_blocked_target_gates"],
        )
        self.assertIn(
            "Gate_L2_N_East",
            graph.graph["_improved_ordinary_l7_crossline_target_gates"],
        )
        self.assertTrue(
            math.isinf(
                graph["VN_L7toL2_Hall_Arrival"][west_queue]["sim_weight"]
            )
        )

        for gate, _queue in graph.graph["gate_queue_area_nodes"].items():
            if str(gate).startswith("Gate_L2_"):
                graph.graph["_resource_queues"][("facility", gate)] = 1.0e6
        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertIn(crossline, active)
        self.assertTrue(
            graph.graph["_improved_ordinary_l7_crossline_blocked"]
        )

    def test_improved_crossline_controls_cover_all_transfer_line_pairs(self):
        graph = net.build_graph()
        net._paper_refresh_temporary_high_cost_weights(graph)
        controls = graph.graph["_improved_ordinary_crossline_controls"]
        entry_edges = {
            tuple(row["entry_edge"])
            for row in controls
        }
        pairs = {
            (row["source_line"], row["target_line"])
            for row in controls
        }
        covered_lines = {
            line
            for pair in pairs
            for line in pair
        }
        self.assertTrue({"L2", "L7", "L16", "L18", "Maglev"} <= covered_lines)
        self.assertIn(("L7", "L2"), pairs)
        self.assertIn(("L2", "L7"), pairs)
        self.assertEqual(
            net._crossline_source_line_id(
                graph, "VN_L16_to_Maglev_Entrance"
            ),
            "L16",
        )
        self.assertNotIn(
            (
                "VN_L16_to_Maglev_Entrance",
                "Transfer_L16_Maglev_Passageway",
            ),
            graph.graph["_improved_ordinary_crossline_active_edges"],
        )
        self.assertNotIn(
            (
                "VN_L16_to_Maglev_Arrival",
                "VN_Maglev_to_L2_Entrance",
            ),
            entry_edges,
        )
        self.assertGreater(len(pairs), 2)
        for row in controls:
            self.assertNotEqual(row["source_line"], row["target_line"])
            self.assertTrue(row["target_gates"])

    def test_improved_l16_maglev_transfer_continues_after_entry(self):
        graph = net.build_graph()
        net.init_people(graph, {}, apply_noise=False)
        start = "Transfer_L16_Maglev_Passageway"
        graph.nodes[start]["people"] = 21
        graph.nodes[start]["people_dict"] = {"L16": 21}
        graph.nodes[start]["source_group_dict"] = {
            "L16_Maglev_transfer": 21
        }

        moves = net._get_paper_step_moves(graph, [start])

        self.assertIn(
            (start, "VN_L16_to_Maglev_Arrival", 10),
            moves,
            msg=(
                f"moves={moves}; "
                f"active_edges={sorted(graph.graph.get('_paper_high_cost_active_edges', set()), key=str)}; "
                f"path={graph.graph.get('_paper_path_by_node', {}).get(start)}; "
                f"topological_exit_reachable={sum(1 for exit_node in graph if graph.nodes[exit_node].get('type') == 'exit' and nx.has_path(graph, start, exit_node))}; "
                f"successors={list(graph.successors(start))}"
            ),
        )

    def test_improved_l16_maglev_continues_after_arrival_node(self):
        graph = net.build_graph()
        net.init_people(graph, {}, apply_noise=False)
        start = "VN_L16_to_Maglev_Arrival"
        graph.nodes[start]["people"] = 21
        graph.nodes[start]["people_dict"] = {"L16": 21}
        graph.nodes[start]["source_group_dict"] = {
            "L16_Maglev_transfer": 21
        }

        moves = net._get_paper_step_moves(graph, [start])

        self.assertTrue(
            any(
                u == start
                and v == "VN_Maglev_to_L2_Entrance"
                and amount > 0
                for u, v, amount in moves
            )
        )

    def test_improved_transfer_does_not_force_same_line_exit_coverage(self):
        graph = net.build_graph()
        net.init_people(graph, {}, apply_noise=False)
        start = "Transfer_L18_L16_F1_Esc1"
        graph.nodes[start]["people"] = 19
        graph.nodes[start]["people_dict"] = {"L18": 19}
        graph.nodes[start]["source_group_dict"] = {
            "L18_L16_transfer": 19
        }

        net._get_paper_step_moves(graph, [start])
        path = graph.graph["_paper_path_by_node"][start]

        self.assertEqual(path[-1], "Exit_L16_11_east")
        self.assertNotIn(
            "Exit_L18_17",
            graph.graph.get("_paper_exit_coverage_used", {}).get("L18", []),
        )

    def test_improved_continues_people_already_inside_closed_crossline_branch(self):
        graph = net.build_graph()
        entry = "VN_7to2_Entrance"
        transfer = "Transfer_L7-L2_Z"
        graph.nodes[entry]["people"] = 5
        graph.nodes[entry].setdefault("people_dict", {})["L7"] = 5

        moves = net._get_paper_step_moves(graph, [entry])

        self.assertIn((entry, transfer, 5), moves)
        self.assertIn(
            (entry, transfer),
            graph.graph["_paper_high_cost_active_edges"],
        )
        self.assertTrue(
            math.isinf(graph[entry][transfer]["sim_weight"])
        )
        diagnostics = graph.graph["_improved_temporary_high_cost_diagnostics"]
        self.assertEqual(
            diagnostics["crossline_committed_continuation_people"], 5.0
        )

    def test_improved_q_term_is_disabled_by_default_but_can_be_enabled(self):
        graph = net.build_graph()
        self.assertFalse(graph.graph.get(
            "improved_gate_queue_term", net.IMPROVED_GATE_QUEUE_TERM
        ))
        self.assertFalse(graph.graph.get(
            "improved_shared_travel_time", net.IMPROVED_SHARED_TRAVEL_TIME
        ))
        graph.graph["improved_gate_queue_term"] = True
        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)
        self.assertIsInstance(active, set)

    def test_improved_and_aa_share_identical_l7_physical_state(self):
        improved_graph = net.build_graph()
        aa_graph = net.build_graph()
        for node in (self.HALL, *self.QUEUES):
            for field in ("type", "area", "capacity", "queue_for_gate"):
                self.assertEqual(
                    improved_graph.nodes[node].get(field),
                    aa_graph.nodes[node].get(field),
                )
        for queue in self.QUEUES:
            gate = improved_graph.nodes[queue]["queue_for_gate"]
            for u, v in ((self.HALL, queue), (queue, gate)):
                for field in ("length", "capacity"):
                    self.assertEqual(
                        improved_graph[u][v].get(field),
                        aa_graph[u][v].get(field),
                    )

    def _aa_hall_graph(self, *, people=10, west_capacity=10):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_resource_flow_credit"] = {}
        graph.graph["_resource_queues"] = {}
        graph.graph["density_dependent_flow"] = False
        graph.graph["spillback_enabled"] = False
        graph.graph["aa_reroute_gain_min"] = 0.20
        graph.add_node(
            self.HALL, type="virtual", people=people, area=90,
            source_group_dict={"L7_train1": people},
            people_dict={"L7": people},
        )
        for suffix, capacity in (("West", west_capacity), ("Mid", 10)):
            queue = f"Gate_L7_{suffix}_Queue"
            gate = f"Gate_L7_{suffix}"
            exit_node = f"Exit_L7_{suffix}"
            graph.add_node(
                queue, type="queue_area", people=0, area=24,
                queue_for_gate=gate, source_group_dict={},
                people_dict={"L7": 0},
            )
            graph.add_node(
                gate, type="gate", people=0, area=4, capacity=capacity
            )
            graph.add_node(exit_node, type="exit", people=0, area=100)
            graph.add_edge(
                self.HALL, queue, length=1, capacity=capacity,
                aa_parallel_choice_group=f"{self.HALL}:parallel_choices",
            )
            graph.add_edge(queue, gate, length=1, capacity=capacity)
            graph.add_edge(gate, exit_node, length=1, capacity=capacity)
        net._annotate_aa_evacuation_stages_and_replan_scope(graph)
        west_queue = "Gate_L7_West_Queue"
        graph.nodes[self.HALL]["_aa_batches"] = [{
            "batch_id": "l7_hall_batch",
            "source_group": "L7_train1",
            "arrival_time": 0.0,
            "amount": people,
            "current_node": self.HALL,
            "current_path": [
                self.HALL, west_queue, "Gate_L7_West", "Exit_L7_West",
            ],
            "waiting_resource": None,
            "queue_enter_time": None,
            "last_reroute_step": None,
            "previous_waiting_resource": None,
            "path_predictions": [],
            "planned_selection_node": self.HALL,
            "step4b2_opportunity_best": {},
            "plan_history_node": self.HALL,
            "selected_first_hops": [west_queue],
            "has_rerouted": False,
        }]
        return graph

    def _patch_hall_costs(self, west_cost, mid_cost):
        def path_cost(_graph, path, _now, amount=1):
            cost = west_cost if path[1].endswith("West_Queue") else mid_cost
            return float(cost), []

        def lower_bound(
            _graph, _node, _now, _amount, predictive=True,
            allowed_successors=None,
        ):
            successor = next(iter(allowed_successors))
            return float(
                west_cost if successor.endswith("West_Queue") else mid_cost
            )

        def astar(
            _graph, node, _now, amount=1, predictive=True,
            objective_cutoff=None, edge_allowed=None, **_kwargs,
        ):
            path = [
                node, "Gate_L7_Mid_Queue",
                "Gate_L7_Mid", "Exit_L7_Mid",
            ]
            return path, float(mid_cost), []

        return patch.multiple(
            spr,
            evaluate_time_dependent_path=path_cost,
            aa_one_step_objective_lower_bound=lower_bound,
            time_dependent_astar=astar,
        )

    def test_aa_prediction_switches_hall_batch_at_twenty_percent_gain(self):
        graph = self._aa_hall_graph()
        with self._patch_hall_costs(100, 80):
            moves = net._get_predictive_aa_step_moves(
                graph, [self.HALL], predictive=True
            )
        self.assertEqual(moves[0][:2], (self.HALL, "Gate_L7_Mid_Queue"))
        diagnostics = graph.graph["_aa_diagnostics"]
        self.assertEqual(diagnostics["hall_gate_switch_decision_people"], 10)
        self.assertEqual(diagnostics["hall_gate_switch_executed_people"], 10)
        self.assertEqual(diagnostics["aa_prediction_triggered_switch_count"], 1)
        row = graph.graph["_l7_hall_decision_diagnostics"][0]
        self.assertEqual(row["decision_people"], 10)
        self.assertEqual(row["accepted_people"], 10)
        self.assertEqual(row["residual_people"], 0)
        self.assertIn(
            "Gate_L7_Mid_Queue",
            json.loads(row["candidate_path_costs"]),
        )

    def test_aa_keeps_west_when_gain_is_below_twenty_percent(self):
        graph = self._aa_hall_graph()
        with self._patch_hall_costs(100, 81):
            moves = net._get_predictive_aa_step_moves(
                graph, [self.HALL], predictive=True
            )
        self.assertEqual(moves[0][:2], (self.HALL, "Gate_L7_West_Queue"))
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["hall_gate_switch_decision_count"],
            0,
        )

    def test_queue_without_configured_lateral_targets_keeps_current_gate(self):
        graph = self._aa_hall_graph()
        queue = "Gate_L7_West_Queue"
        graph.nodes[queue]["people"] = 1
        graph.nodes[queue]["source_group_dict"] = {"L7_train1": 1}
        graph.nodes[queue]["people_dict"] = {"L7": 1}
        graph.nodes[queue]["_aa_batches"] = [{
            **graph.nodes[self.HALL]["_aa_batches"][0],
            "batch_id": "locked",
            "amount": 1,
            "current_node": queue,
            "current_path": [queue, "Gate_L7_West", "Exit_L7_West"],
        }]
        moves = net._get_predictive_aa_step_moves(
            graph, [queue], predictive=True
        )
        self.assertEqual(moves[0][:2], (queue, "Gate_L7_West"))
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_queue_replan_attempt_count"],
            0,
        )

    def test_partial_acceptance_keeps_residual_people_at_hall(self):
        graph = self._aa_hall_graph(people=10, west_capacity=3)
        original_capacity = net.resource_capacity_per_second
        with self._patch_hall_costs(100, 81):
            with patch.object(
                net,
                "resource_capacity_per_second",
                side_effect=lambda current_graph, resource_id: (
                    3.0
                    if resource_id == (
                        "edge", self.HALL, "Gate_L7_West_Queue"
                    )
                    else original_capacity(current_graph, resource_id)
                ),
            ):
                graph.graph.pop("_resource_capacity_cache", None)
                moves = net._get_predictive_aa_step_moves(
                    graph, [self.HALL], predictive=True
                )
        scheduled = net._schedule_aa_batch_moves_as_transit(
            graph, moves, graph.graph["_aa_accepted_allocations"]
        )
        self.assertEqual(sum(item["amount"] for item in scheduled), 3)
        self.assertEqual(graph.nodes[self.HALL]["people"], 7)
        self.assertEqual(
            sum(item["amount"] for item in graph.graph["_transit_queue"]), 3
        )
        self.assertEqual(
            graph.nodes[self.HALL]["people"]
            + sum(item["amount"] for item in graph.graph["_transit_queue"]),
            10,
        )
        self.assertEqual(
            graph.nodes[self.HALL]["_aa_batches"][0]["current_node"],
            self.HALL,
        )
        row = graph.graph["_l7_hall_decision_diagnostics"][0]
        self.assertEqual(row["accepted_people"], 3)
        self.assertEqual(row["residual_people"], 7)

    def test_l7_small_scale_two_step_dynamic_trial(self):
        initial_hall = 100
        initial_west = 73
        initial_total = initial_hall + initial_west

        improved = self._aa_hall_graph(people=initial_hall)
        improved.graph["improved_gate_queue_term"] = False
        west = "Gate_L7_West_Queue"
        improved.nodes[west]["people"] = initial_west
        improved.nodes[west]["source_group_dict"] = {
            "L7_train1": initial_west
        }
        improved.nodes[west]["people_dict"] = {"L7": initial_west}
        active, _ = net._paper_refresh_temporary_high_cost_weights(improved)
        selected_improved = min(
            ("Gate_L7_West_Queue", "Gate_L7_Mid_Queue"),
            key=lambda queue: improved[self.HALL][queue]["sim_weight"],
        )
        self.assertIn((self.HALL, west), active)
        self.assertEqual(selected_improved, "Gate_L7_Mid_Queue")
        improved_moves = net._integerize_moves(
            improved, [(self.HALL, selected_improved, initial_hall)]
        )
        net._schedule_moves_as_transit(improved, improved_moves)
        net._process_transit_arrivals(improved, 10.0)
        improved_total = sum(
            int(data.get("people", 0))
            for _, data in improved.nodes(data=True)
        ) + sum(
            int(item.get("amount", 0))
            for item in improved.graph.get("_transit_queue", [])
        )

        aa = self._aa_hall_graph(people=initial_hall)
        aa.nodes[west]["people"] = initial_west
        aa.nodes[west]["source_group_dict"] = {"L7_train1": initial_west}
        aa.nodes[west]["people_dict"] = {"L7": initial_west}
        with self._patch_hall_costs(100, 70):
            aa_moves = net._get_predictive_aa_step_moves(
                aa, [self.HALL], predictive=True
            )
        selected_aa = aa_moves[0][1]
        net._schedule_aa_batch_moves_as_transit(
            aa, aa_moves, aa.graph["_aa_accepted_allocations"]
        )
        net._process_transit_arrivals(aa, 10.0)
        aa_total = sum(
            int(data.get("people", 0))
            for _, data in aa.nodes(data=True)
        ) + sum(
            int(item.get("amount", 0))
            for item in aa.graph.get("_transit_queue", [])
        )

        self.assertEqual(selected_aa, "Gate_L7_Mid_Queue")
        self.assertEqual(improved_total, initial_total)
        self.assertEqual(aa_total, initial_total)
        self.assertTrue(aa.nodes[west]["aa_active_replan_allowed"])
        self.assertEqual(
            aa.graph["_aa_diagnostics"][
                "gate_approach_replan_evaluation_count"
            ],
            0,
        )
        print(
            "L7_SMALL_TRIAL",
            {
                "initial_total": initial_total,
                "west_density": initial_west / 24.0,
                "improved_selected_queue": selected_improved,
                "improved_hall_remaining": improved.nodes[self.HALL]["people"],
                "aa_selected_queue": selected_aa,
                "aa_hall_remaining": aa.nodes[self.HALL]["people"],
                "aa_switch_decision_people": aa.graph["_aa_diagnostics"][
                    "hall_gate_switch_decision_people"
                ],
                "aa_switch_executed_people": aa.graph["_aa_diagnostics"][
                    "hall_gate_switch_executed_people"
                ],
                "improved_conserved": improved_total == initial_total,
                "aa_conserved": aa_total == initial_total,
            },
        )


class GateApproachAARerouteTests(unittest.TestCase):
    def _gate_switch_graph(self, *, people=10, switch_capacity=10):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_resource_flow_credit"] = {}
        graph.graph["_resource_queues"] = {}
        graph.graph["density_dependent_flow"] = False
        graph.graph["spillback_enabled"] = False
        graph.graph["aa_reroute_gain_min"] = 0.20
        graph.graph["gate_queue_area_nodes"] = {
            "Gate_A": "Gate_A_Queue",
            "Gate_B": "Gate_B_Queue",
        }
        for node, data in {
            "Stair": {"type": "stair", "people": 0, "area": 100},
            "Gate_A_Queue": {
                "type": "queue_area", "people": people, "area": 100,
                "queue_for_gate": "Gate_A",
                "source_group_dict": {"L7_train1": people},
                "people_dict": {"L7": people},
            },
            "Switch_Corridor": {
                "type": "area", "people": 0, "area": 100,
                "source_group_dict": {}, "people_dict": {"L7": 0},
            },
            "Gate_B_Queue": {
                "type": "queue_area", "people": 0, "area": 100,
                "queue_for_gate": "Gate_B",
                "source_group_dict": {},
                "people_dict": {"L7": 0},
            },
            "Gate_A": {
                "type": "gate", "people": 0, "area": 10, "capacity": 1,
                "source_group_dict": {}, "people_dict": {"L7": 0},
            },
            "Gate_B": {
                "type": "gate", "people": 0, "area": 10, "capacity": 10,
                "source_group_dict": {}, "people_dict": {"L7": 0},
            },
            "Exit_A": {"type": "exit", "people": 0, "area": 100},
            "Exit_B": {"type": "exit", "people": 0, "area": 100},
        }.items():
            graph.add_node(node, **data)
        graph.add_edge("Stair", "Gate_A_Queue", length=1, capacity=10)
        graph.add_edge("Gate_A_Queue", "Gate_A", length=1, capacity=10)
        graph.add_edge("Gate_A", "Exit_A", length=1, capacity=10)
        graph.add_edge("Gate_A_Queue", "Switch_Corridor", length=5, capacity=switch_capacity)
        graph.add_edge("Switch_Corridor", "Gate_B_Queue", length=5, capacity=switch_capacity)
        graph.add_edge("Gate_B_Queue", "Gate_B", length=1, capacity=10)
        graph.add_edge("Gate_B", "Exit_B", length=1, capacity=10)
        graph.nodes["Gate_A_Queue"]["_aa_batches"] = [{
            "batch_id": "batch_old",
            "source_group": "L7_train1",
            "arrival_time": 0.0,
            "amount": people,
            "current_node": "Gate_A_Queue",
            "current_path": ["Gate_A_Queue", "Gate_A", "Exit_A"],
            "waiting_resource": None,
            "queue_enter_time": None,
            "last_reroute_step": None,
            "previous_waiting_resource": None,
            "path_predictions": [],
            "planned_selection_node": None,
            "step4b2_opportunity_best": {},
            "plan_history_node": "Gate_A_Queue",
            "selected_first_hops": ["Gate_A"],
            "has_rerouted": False,
        }]
        net._annotate_aa_evacuation_stages_and_replan_scope(graph)
        return graph

    def _patch_aa_costs(self, queue_a, queue_b):
        def queue_at(G, resource_id, eta):
            if resource_id == ("facility", "Gate_A"):
                return float(queue_a)
            if resource_id == ("facility", "Gate_B"):
                return float(queue_b)
            return 0.0
        return patch.multiple(
            spr,
            physical_edge_travel_time=lambda G, u, v: float(G[u][v]["length"]),
            predicted_resource_queue_at_time=queue_at,
            predicted_spatial_wait=lambda G, node, eta, amount=1: 0.0,
            predicted_spatial_density=lambda G, node, eta, amount=0: 0.0,
        )

    def _retained_path_cache_graph(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_resource_flow_credit"] = {}
        graph.graph["_resource_queues"] = {}
        graph.graph["density_dependent_flow"] = False
        graph.graph["spillback_enabled"] = False
        graph.add_node(
            "Source",
            type="area",
            people=1,
            area=100,
            source_group_dict={"L7_train1": 1},
            people_dict={"L7": 1},
        )
        graph.add_node("Mid", type="area", people=0, area=100)
        graph.add_node("Exit", type="exit", people=0, area=100)
        graph.add_edge("Source", "Mid", length=1, capacity=10)
        graph.add_edge("Mid", "Exit", length=1, capacity=10)
        graph.nodes["Source"]["_aa_batches"] = [{
            "batch_id": "retained",
            "source_group": "L7_train1",
            "arrival_time": 0.0,
            "amount": 1,
            "current_node": "Source",
            "current_path": ["Source", "Mid", "Exit"],
            "waiting_resource": None,
            "queue_enter_time": None,
            "last_reroute_step": None,
            "previous_waiting_resource": None,
            "path_predictions": [],
            "planned_selection_node": None,
            "step4b2_opportunity_best": {},
            "plan_history_node": None,
            "selected_first_hops": [],
            "has_rerouted": False,
            "service_committed": False,
            "precommit_pending": False,
        }]
        return graph

    def _retained_path_evaluator(self, calls):
        def evaluate_path(graph, path, now, amount=1):
            calls["count"] += 1
            first_resource = net.edge_resource_id(graph, path[0], path[1])
            second_resource = net.edge_resource_id(graph, path[1], path[2])
            return 2.0, [
                {
                    "u": path[0],
                    "v": path[1],
                    "resource_id": first_resource,
                    "resource_entry_time": float(now),
                    "arrival_time": float(now) + 1.0,
                    "predicted_queue": spr.current_resource_queue(
                        graph, first_resource
                    ),
                    "predicted_wait": 0.0,
                    "spatial_wait": 0.0,
                    "objective_cost": 1.0,
                },
                {
                    "u": path[1],
                    "v": path[2],
                    "resource_id": second_resource,
                    "resource_entry_time": float(now) + 1.0,
                    "arrival_time": float(now) + 2.0,
                    "predicted_queue": spr.current_resource_queue(
                        graph, second_resource
                    ),
                    "predicted_wait": 0.0,
                    "spatial_wait": 0.0,
                    "objective_cost": 2.0,
                },
            ]
        return evaluate_path

    def test_retained_path_prediction_is_reused_when_state_signature_matches(self):
        graph = self._retained_path_cache_graph()
        calls = {"count": 0}

        def integerize(_graph, requests):
            return [
                (item["u"], item["v"], int(item["requested"]))
                for item in requests
            ]

        with patch.object(
            spr,
            "evaluate_time_dependent_path",
            self._retained_path_evaluator(calls),
        ), patch.object(net, "_integerize_aa_batch_requests", integerize):
            net._get_predictive_aa_step_moves(graph, ["Source"], predictive=True)
            graph.graph["_sim_time"] = 1.0
            net._get_predictive_aa_step_moves(graph, ["Source"], predictive=True)

        batch = graph.nodes["Source"]["_aa_batches"][0]
        diagnostics = graph.graph["_aa_diagnostics"]
        self.assertEqual(calls["count"], 1)
        self.assertEqual(diagnostics["old_path_evaluation_count"], 1)
        self.assertEqual(diagnostics["same_path_reuse_count"], 1)
        self.assertEqual(
            batch["path_predictions"][0]["resource_entry_time"],
            1.0,
        )
        self.assertEqual(batch["path_predictions"][0]["arrival_time"], 2.0)

    def test_retained_path_prediction_refreshes_when_queue_signature_changes(self):
        graph = self._retained_path_cache_graph()
        calls = {"count": 0}
        first_resource = net.edge_resource_id(graph, "Source", "Mid")

        def integerize(_graph, requests):
            return [
                (item["u"], item["v"], int(item["requested"]))
                for item in requests
            ]

        with patch.object(
            spr,
            "evaluate_time_dependent_path",
            self._retained_path_evaluator(calls),
        ), patch.object(net, "_integerize_aa_batch_requests", integerize):
            net._get_predictive_aa_step_moves(graph, ["Source"], predictive=True)
            graph.graph["_resource_queues"][first_resource] = 3
            graph.graph["_sim_time"] = 1.0
            net._get_predictive_aa_step_moves(graph, ["Source"], predictive=True)

        diagnostics = graph.graph["_aa_diagnostics"]
        self.assertEqual(calls["count"], 2)
        self.assertEqual(diagnostics["old_path_evaluation_count"], 2)
        self.assertEqual(diagnostics["same_path_reuse_count"], 0)

    def _set_gate_queue_batches(self, graph, specs):
        queue = "Gate_A_Queue"
        total = sum(int(amount) for _, amount, _ in specs)
        graph.nodes[queue]["people"] = total
        graph.nodes[queue]["source_group_dict"] = {"L7_train1": total}
        graph.nodes[queue]["people_dict"] = {"L7": total}
        batches = []
        for batch_id, amount, queue_enter_time in specs:
            batches.append({
                "batch_id": batch_id,
                "source_group": "L7_train1",
                "arrival_time": 0.0,
                "amount": int(amount),
                "current_node": queue,
                "current_path": [queue, "Gate_A", "Exit_A"],
                "waiting_resource": ("facility", "Gate_A"),
                "queue_enter_time": float(queue_enter_time),
                "last_reroute_step": None,
                "previous_waiting_resource": None,
                "path_predictions": [],
                "planned_selection_node": None,
                "step4b2_opportunity_best": {},
                "plan_history_node": queue,
                "selected_first_hops": ["Gate_A"],
                "has_rerouted": False,
                "service_committed": False,
                "precommit_pending": False,
            })
        graph.nodes[queue]["_aa_batches"] = batches

    def test_gate_approach_is_physical_location_not_stair_after_arrival(self):
        graph = self._gate_switch_graph(people=0)
        graph.nodes["Stair"]["people"] = 3
        graph.nodes["Stair"]["source_group_dict"] = {"L7_train1": 3}
        graph.nodes["Stair"]["people_dict"] = {"L7": 3}
        net._schedule_moves_as_transit(graph, [("Stair", "Gate_A_Queue", 3)])
        net._process_transit_arrivals(graph, 10.0)
        self.assertEqual(graph.nodes["Stair"]["people"], 0)
        self.assertEqual(graph.nodes["Gate_A_Queue"]["people"], 3)

    def test_gate_switch_occurs_when_gain_exceeds_twenty_percent(self):
        graph = self._gate_switch_graph(people=10)
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        self.assertEqual(moves[0][:2], ("Gate_A_Queue", "Switch_Corridor"))
        allocation = graph.graph["_aa_accepted_allocations"][
            ("Gate_A_Queue", "Switch_Corridor")
        ][0]
        self.assertEqual(allocation["current_path"][:4], [
            "Gate_A_Queue", "Switch_Corridor", "Gate_B_Queue", "Gate_B",
        ])
        self.assertNotIn("Stair", allocation["current_path"])
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_switch_event_count"], 1
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_evaluation_count"
            ],
            1,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_accept_count"
            ],
            1,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_replan_qualified_switch_count"],
            1,
        )
        diagnostic = graph.graph["_aa_gate_replan_diagnostics"][0]
        self.assertEqual(diagnostic["no_switch_reason"], "qualified_switch")
        self.assertTrue(diagnostic["directed_path_exists"])
        self.assertIn("Gate_B", diagnostic["found_alternative_path"])

    def test_gate_switch_stays_when_gain_is_below_threshold(self):
        graph = self._gate_switch_graph(people=10)
        with self._patch_aa_costs(queue_a=1, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        self.assertEqual(moves[0][:2], ("Gate_A_Queue", "Gate_A"))
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_switch_event_count"], 0
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_replan_gain_below_threshold_count"],
            1,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_rejected_count"
            ],
            1,
        )

    def test_gate_switch_stays_when_shorter_queue_is_too_far(self):
        graph = self._gate_switch_graph(people=10)
        graph["Gate_A_Queue"]["Switch_Corridor"]["length"] = 500.0
        graph["Switch_Corridor"]["Gate_B_Queue"]["length"] = 500.0
        with self._patch_aa_costs(queue_a=5, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        self.assertEqual(moves[0][:2], ("Gate_A_Queue", "Gate_A"))
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_evaluation_count"
            ],
            1,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_accept_count"
            ],
            0,
        )

    def test_gate_switch_is_not_evaluated_without_congestion_trigger(self):
        graph = self._gate_switch_graph(people=1)
        graph.nodes["Gate_A_Queue"]["area"] = 100.0
        with self._patch_aa_costs(queue_a=0, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        self.assertEqual(moves[0][:2], ("Gate_A_Queue", "Gate_A"))
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_evaluation_count"
            ],
            0,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_trigger_not_met_count"
            ],
            0,
        )

    def test_gate_switch_reports_no_real_path_separately(self):
        graph = self._gate_switch_graph(people=10)
        graph.remove_edge("Gate_A_Queue", "Switch_Corridor")
        net._annotate_aa_evacuation_stages_and_replan_scope(graph)
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        self.assertEqual(moves[0][:2], ("Gate_A_Queue", "Gate_A"))
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_evaluation_count"
            ],
            1,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_replan_no_real_path_count"
            ],
            1,
        )

    def test_gate_approach_connectivity_report_uses_real_directed_paths(self):
        graph = self._gate_switch_graph(people=0)
        rows = net._build_gate_approach_connectivity_report(graph)
        row = next(
            item for item in rows
            if item["from_gate_approach"] == "Gate_A_Queue"
            and item["to_gate_approach"] == "Gate_B_Queue"
        )
        self.assertTrue(row["directed_path_exists"])
        self.assertEqual(
            row["path_nodes"],
            "Gate_A_Queue -> Switch_Corridor -> Gate_B_Queue",
        )
        self.assertFalse(row["contains_stair_or_platform"])

    def test_gate_switch_does_not_use_zero_length_direct_shortcut(self):
        graph = self._gate_switch_graph(people=10)
        graph.remove_edge("Gate_A_Queue", "Switch_Corridor")
        graph.add_edge("Gate_A_Queue", "Gate_B", length=0, capacity=10)
        net._annotate_aa_evacuation_stages_and_replan_scope(graph)
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        self.assertEqual(moves[0][:2], ("Gate_A_Queue", "Gate_A"))
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_accept_count"
            ],
            0,
        )

    def test_gate_switch_only_edges_are_hidden_from_normal_aa_search(self):
        graph = self._gate_switch_graph(people=10)
        graph["Gate_A_Queue"]["Switch_Corridor"][
            "gate_switch_only"
        ] = True
        graph["Switch_Corridor"]["Gate_B_Queue"][
            "gate_switch_only"
        ] = True
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            normal_path, _, _ = spr.time_dependent_astar(
                graph, "Gate_A_Queue", amount=10
            )
            switch_path, _, _ = spr.time_dependent_astar(
                graph,
                "Gate_A_Queue",
                amount=10,
                allow_gate_switch_edges=True,
            )
        self.assertEqual(normal_path[:2], ["Gate_A_Queue", "Gate_A"])
        self.assertEqual(switch_path[:4], [
            "Gate_A_Queue",
            "Switch_Corridor",
            "Gate_B_Queue",
            "Gate_B",
        ])

    def test_gate_switch_scope_rejects_paths_through_multiple_queues(self):
        graph = self._gate_switch_graph(people=0)
        graph.add_node(
            "Gate_C_Queue",
            type="queue_area",
            people=0,
            area=100,
            queue_for_gate="Gate_C",
        )
        graph.add_node(
            "Gate_C", type="gate", people=0, area=10, capacity=10
        )
        graph.add_edge(
            "Gate_B_Queue", "Gate_C_Queue", length=1, capacity=10
        )
        graph.add_edge("Gate_C_Queue", "Gate_C", length=1, capacity=10)
        graph.add_edge("Gate_C", "Exit_B", length=1, capacity=10)
        graph.graph["gate_queue_area_nodes"]["Gate_C"] = "Gate_C_Queue"
        net._annotate_aa_evacuation_stages_and_replan_scope(graph)
        path = [
            "Gate_A_Queue",
            "Switch_Corridor",
            "Gate_B_Queue",
            "Gate_C_Queue",
            "Gate_C",
            "Exit_B",
        ]
        self.assertFalse(net._aa_gate_switch_path_respects_scope(
            graph, "Gate_A_Queue", path, {"Gate_B", "Gate_C"}
        ))

    def test_accepted_gate_switch_people_enter_transit_and_rejected_remain(self):
        graph = self._gate_switch_graph(people=5, switch_capacity=1)
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        scheduled = net._schedule_moves_as_transit(graph, moves)
        accepted = sum(item["amount"] for item in scheduled)
        self.assertEqual(accepted, 2)
        self.assertEqual(
            sum(item["amount"] for item in graph.graph["_transit_queue"]),
            accepted,
        )
        self.assertEqual(graph.nodes["Gate_A_Queue"]["people"], 3)
        remaining = graph.nodes["Gate_A_Queue"]["_aa_batches"][0]
        self.assertEqual(remaining["amount"], 3)
        self.assertEqual(remaining["queued_for_gate"], "Gate_A")
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_approach_rerouted_people"],
            1,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_switch_people"],
            1,
        )

    def test_committed_gate_people_are_not_rerouted_and_total_is_conserved(self):
        graph = self._gate_switch_graph(people=15, switch_capacity=10)
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        scheduled = net._schedule_moves_as_transit(graph, moves)
        lateral_people = sum(item["amount"] for item in scheduled)
        committed_people = sum(
            item["amount"]
            for item in graph.graph["_transit_queue"]
            if item["v"] == "Gate_A"
        )
        waiting_people = graph.nodes["Gate_A_Queue"]["people"]
        self.assertEqual(lateral_people, 11)
        self.assertEqual(committed_people, 1)
        self.assertEqual(waiting_people, 4)
        self.assertEqual(
            waiting_people
            + sum(item["amount"] for item in graph.graph["_transit_queue"]),
            15,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_approach_rerouted_people"],
            10,
        )

    def test_committed_gate_batch_continues_from_gate_to_exit(self):
        graph = self._gate_switch_graph(people=1, switch_capacity=10)
        with self._patch_aa_costs(queue_a=0, queue_b=0):
            first_moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        self.assertEqual(first_moves, [("Gate_A_Queue", "Gate_A", 1)])
        net._schedule_moves_as_transit(graph, first_moves)
        net._process_transit_arrivals(graph, 10.0)

        gate_batch = graph.nodes["Gate_A"]["_aa_batches"][0]
        self.assertFalse(gate_batch["service_committed"])
        self.assertEqual(gate_batch["current_path"], ["Gate_A", "Exit_A"])
        astar_calls_before = graph.graph["_aa_diagnostics"][
            "astar_call_count"
        ]
        next_moves = net._get_predictive_aa_step_moves(
            graph, ["Gate_A"], predictive=True
        )
        self.assertEqual(next_moves, [("Gate_A", "Exit_A", 1)])
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["astar_call_count"],
            astar_calls_before,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["committed_replan_skip_count"],
            1,
        )

    def test_formal_l16_gate_precommit_preserves_exit_suffix(self):
        graph = net.build_graph()
        net.init_people(graph, {}, apply_noise=False)
        queue = "Gate_L16_S1_Queue"
        gate = "Gate_L16_S1"
        exit_node = "Exit_L16_11_west"
        graph.nodes[queue]["people"] = 1
        graph.nodes[queue]["source_group_dict"] = {"L16_train1": 1}
        graph.nodes[queue]["people_dict"] = {"L16": 1}
        graph.nodes[queue]["_aa_batches"] = [{
            "batch_id": "formal_l16_precommit",
            "source_group": "L16_train1",
            "arrival_time": 0.0,
            "amount": 1,
            "current_node": queue,
            "current_path": [queue, gate, exit_node],
            "waiting_resource": ("facility", gate),
            "queue_enter_time": 0.0,
            "last_reroute_step": None,
            "previous_waiting_resource": None,
            "path_predictions": [],
            "planned_selection_node": None,
            "step4b2_opportunity_best": {},
            "plan_history_node": queue,
            "selected_first_hops": [gate],
            "has_rerouted": False,
            "service_committed": False,
            "precommit_pending": False,
        }]

        moves = net._get_predictive_aa_step_moves(
            graph, [queue], predictive=True
        )
        self.assertEqual(moves, [(queue, gate, 1)])
        net._schedule_moves_as_transit(graph, moves)
        net._process_transit_arrivals(graph, 10.0)

        gate_batch = graph.nodes[gate]["_aa_batches"][0]
        self.assertEqual(gate_batch["current_path"], [gate, exit_node])
        self.assertEqual(
            net._get_predictive_aa_step_moves(
                graph, [gate], predictive=True
            ),
            [(gate, exit_node, 1)],
        )

    def test_completed_gate_switch_cannot_switch_back(self):
        graph = self._gate_switch_graph(people=5, switch_capacity=10)
        graph.add_edge(
            "Gate_B_Queue", "Gate_A_Queue", length=5, capacity=10
        )
        net._annotate_aa_evacuation_stages_and_replan_scope(graph)
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            first_moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )
        net._schedule_moves_as_transit(graph, first_moves)
        net._process_transit_arrivals(graph, 10.0)
        corridor_moves = net._get_predictive_aa_step_moves(
            graph, ["Switch_Corridor"], predictive=True
        )
        net._schedule_moves_as_transit(graph, corridor_moves)
        net._process_transit_arrivals(graph, 20.0)
        batch = graph.nodes["Gate_B_Queue"]["_aa_batches"][0]
        self.assertTrue(batch["gate_switch_completed"])
        evaluations = graph.graph["_aa_diagnostics"][
            "gate_approach_replan_evaluation_count"
        ]
        with self._patch_aa_costs(queue_a=0, queue_b=100):
            final_moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_B_Queue"], predictive=True
            )
        self.assertEqual(final_moves[0][:2], ("Gate_B_Queue", "Gate_B"))
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "gate_approach_replan_evaluation_count"
            ],
            evaluations,
        )

    def test_batch_merge_preserves_completed_gate_switch_state(self):
        graph = self._gate_switch_graph(people=0)
        base = {
            "source_group": "L7_train1",
            "arrival_time": 10.0,
            "amount": 2,
            "current_path": ["Gate_B_Queue", "Gate_B", "Exit_B"],
            "waiting_resource": ("facility", "Gate_B"),
            "queue_enter_time": 10.0,
            "planned_selection_node": None,
            "plan_history_node": "Gate_B_Queue",
            "selected_first_hops": ["Gate_B"],
            "has_rerouted": True,
            "step4b2_opportunity_best": {},
            "path_predictions": [],
        }
        unswitched = dict(base, batch_id="unswitched")
        switched = dict(
            base,
            batch_id="switched",
            gate_switch_completed=True,
        )
        graph.nodes["Gate_B_Queue"]["_aa_batches"] = []
        net._append_aa_batch(graph, "Gate_B_Queue", unswitched)
        net._append_aa_batch(graph, "Gate_B_Queue", switched)
        batches = graph.nodes["Gate_B_Queue"]["_aa_batches"]
        self.assertEqual(len(batches), 2)
        self.assertEqual(
            sorted(bool(item.get("gate_switch_completed")) for item in batches),
            [False, True],
        )

    def test_formal_l7_gate_queues_have_positive_lateral_paths(self):
        graph = net.build_graph()
        queues = [
            "Gate_L7_N_West_Queue",
            "Gate_L7_N_Mid_Queue",
            "Gate_L7_N_East_Queue",
            "Gate_L7_West_Vert_Queue",
        ]
        self.assertFalse(
            graph.graph["l7_common_hall_vertical_integration_enabled"]
        )
        self.assertFalse(
            graph.has_edge("Stair_L7_1", "VN_L7_Hall_Arrival")
        )
        rows = net._build_gate_approach_connectivity_report(graph)
        l7_rows = [
            row for row in rows
            if row["from_gate_approach"] in queues
            and row["to_gate_approach"] in queues
        ]
        self.assertEqual(len(l7_rows), 12)
        for row in l7_rows:
            self.assertTrue(row["directed_path_exists"])
            self.assertGreater(row["path_length"], 0.0)
            self.assertNotIn("VN_L7_Hall_Arrival", row["path_nodes"])
            self.assertFalse(row["contains_stair_or_platform"])
        for queue in queues:
            gate = graph.nodes[queue]["queue_for_gate"]
            self.assertTrue(graph.nodes[queue]["aa_active_replan_allowed"])
            self.assertFalse(graph.nodes[queue]["aa_replan_return_blocked"])
            self.assertIn(gate, graph.nodes[queue]["aa_replan_successors"])
            self.assertEqual(
                set(graph.nodes[queue]["aa_replan_successors"]),
                {gate, *(other for other in queues if other != queue)},
            )

    def test_aa_gate_request_fifo_priority_is_queue_enter_time(self):
        graph = self._gate_switch_graph(people=0)
        graph.nodes["Gate_A_Queue"]["people"] = 2
        graph.nodes["Gate_A_Queue"]["source_group_dict"] = {"L7_train1": 2}
        graph.nodes["Gate_A_Queue"]["people_dict"] = {"L7": 2}
        graph["Gate_A_Queue"]["Gate_A"]["capacity"] = 1
        requests = [
            {
                "u": "Gate_A_Queue", "v": "Gate_A", "requested": 1,
                "batch_id": "late", "source_group": "L7_train1",
                "arrival_time": 0.0, "queue_enter_time": 10.0,
                "current_path": ["Gate_A_Queue", "Gate_A", "Exit_A"],
                "waiting_resource": ("facility", "Gate_A"),
                "path_predictions": [], "rerouted_this_step": False,
            },
            {
                "u": "Gate_A_Queue", "v": "Gate_A", "requested": 1,
                "batch_id": "early", "source_group": "L7_train1",
                "arrival_time": 0.0, "queue_enter_time": 0.0,
                "current_path": ["Gate_A_Queue", "Gate_A", "Exit_A"],
                "waiting_resource": ("facility", "Gate_A"),
                "path_predictions": [], "rerouted_this_step": False,
            },
        ]
        moves = net._integerize_aa_batch_requests(graph, requests)
        self.assertEqual(moves, [("Gate_A_Queue", "Gate_A", 1)])
        accepted = graph.graph["_aa_accepted_allocations"][
            ("Gate_A_Queue", "Gate_A")
        ]
        self.assertEqual([item["batch_id"] for item in accepted], ["early"])

    def test_fifo_service_precommit_happens_before_gate_reroute(self):
        graph = self._gate_switch_graph(people=20, switch_capacity=20)
        graph.nodes["Gate_A"]["capacity"] = 5
        self._set_gate_queue_batches(
            graph,
            [("batch1", 5, 1.0), ("batch2", 15, 2.0)],
        )
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            moves = net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )

        diagnostics = graph.graph["_aa_diagnostics"]
        self.assertEqual(
            diagnostics["gate_approach_service_committed_people"], 5
        )
        self.assertEqual(
            diagnostics["gate_approach_reroutable_waiting_people"], 15
        )
        batches = graph.nodes["Gate_A_Queue"]["_aa_batches"]
        committed = next(item for item in batches if item["service_committed"])
        waiting = next(item for item in batches if not item["service_committed"])
        self.assertEqual(committed["amount"], 5)
        self.assertEqual(waiting["amount"], 15)
        self.assertEqual(committed["queue_enter_time"], 1.0)
        self.assertEqual(
            graph.graph["_aa_accepted_allocations"][("Gate_A_Queue", "Gate_A")][0]["amount"],
            5,
        )
        self.assertEqual(
            graph.graph["_aa_accepted_allocations"][("Gate_A_Queue", "Switch_Corridor")][0]["amount"],
            15,
        )
        self.assertEqual(
            diagnostics["gate_approach_replan_evaluation_count"], 1
        )
        self.assertEqual(
            [row["passenger_count"] for row in graph.graph["_aa_gate_replan_diagnostics"]],
            [15],
        )
        self.assertEqual(sum(amount for _, _, amount in moves), 20)

    def test_single_gate_batch_is_split_before_gate_reroute(self):
        graph = self._gate_switch_graph(people=20, switch_capacity=20)
        graph.nodes["Gate_A"]["capacity"] = 5
        self._set_gate_queue_batches(graph, [("only_batch", 20, 1.0)])
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )

        batches = graph.nodes["Gate_A_Queue"]["_aa_batches"]
        self.assertEqual(sum(item["amount"] for item in batches), 20)
        self.assertEqual(
            sorted(
                (item["amount"], bool(item["service_committed"]))
                for item in batches
            ),
            [(5, True), (15, False)],
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_approach_service_committed_people"],
            5,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_approach_reroutable_waiting_people"],
            15,
        )

    def test_fifo_partial_batch_commit_uses_stable_queue_order(self):
        graph = self._gate_switch_graph(people=16, switch_capacity=20)
        graph.nodes["Gate_A"]["capacity"] = 10
        self._set_gate_queue_batches(
            graph,
            [("batch_old", 8, 1.0), ("batch_new", 8, 2.0)],
        )
        with self._patch_aa_costs(queue_a=100, queue_b=0):
            net._get_predictive_aa_step_moves(
                graph, ["Gate_A_Queue"], predictive=True
            )

        batches = graph.nodes["Gate_A_Queue"]["_aa_batches"]
        self.assertEqual(
            sorted(
                (item["amount"], bool(item["service_committed"]), item["queue_enter_time"])
                for item in batches
            ),
            [(2, True, 2.0), (6, False, 2.0), (8, True, 1.0)],
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_approach_service_committed_people"],
            10,
        )
        self.assertEqual(
            graph.graph["_aa_diagnostics"]["gate_approach_reroutable_waiting_people"],
            6,
        )


class SpillbackRegressionTests(unittest.TestCase):
    def _merge_graph(self, *, spillback=True, reserved=0):
        graph = nx.DiGraph()
        graph.graph["density_dependent_flow"] = True
        graph.graph["spillback_enabled"] = spillback
        graph.graph["receiving_jam_density"] = 4.0
        graph.graph["_transit_queue"] = []
        graph.add_node("u1", type="area", people=10, area=10)
        graph.add_node("u2", type="area", people=10, area=10)
        graph.add_node("v", type="area", people=0, area=1)
        graph.add_edge("u1", "v", capacity=10, length=1)
        graph.add_edge("u2", "v", capacity=10, length=1)
        if reserved:
            graph.graph["_transit_queue"].append(
                {"v": "v", "amount": reserved, "arrive_time": 10}
            )
        return graph

    def test_merge_inflow_shares_one_destination_capacity(self):
        graph = self._merge_graph()
        moves = net._integerize_moves(graph, [("u1", "v", 5), ("u2", "v", 5)])
        self.assertEqual(sum(amount for _, _, amount in moves), 4)

    def test_in_transit_people_reserve_destination_space(self):
        graph = self._merge_graph(reserved=3)
        moves = net._integerize_moves(graph, [("u1", "v", 5), ("u2", "v", 5)])
        self.assertEqual(sum(amount for _, _, amount in moves), 1)

    def test_spillback_switch_restores_legacy_merge_behavior(self):
        graph = self._merge_graph(spillback=False)
        moves = net._integerize_moves(graph, [("u1", "v", 5), ("u2", "v", 5)])
        # Spillback-off is an explicit ablation: physical edge capacities still
        # apply, while shared destination storage is disabled.
        self.assertEqual(sum(amount for _, _, amount in moves), 10)

    def test_queue_density_uses_physical_occupancy_not_overflow(self):
        graph = nx.DiGraph()
        graph.graph["density_dependent_flow"] = True
        graph.graph["receiving_jam_density"] = 5.4
        graph.add_node("area", type="passageway", width=1, people=100, area=10, capacity=1)

        density, physical_people, overflow = net._evaluation_node_physical_state(
            graph, "area"
        )

        self.assertAlmostEqual(density, 4.0)
        self.assertAlmostEqual(physical_people, 40.0)
        self.assertAlmostEqual(overflow, 60.0)

    def test_high_load_hall_people_start_in_staging_area(self):
        graph = net.build_graph()
        graph.graph["density_dependent_flow"] = True
        population = {
            line: {"train_1": 0, "train_2": 0, "platform_waiting": 0,
                   "hall_people": 0, "transfer_people": 0}
            for line in net.ALL_LINE_IDS
        }
        population["L2"]["hall_people"] = 20

        net.init_people(graph, population)

        self.assertEqual(graph.nodes["VN_L2_Hall_Arrival"]["people"], 20)
        self.assertEqual(
            sum(graph.nodes[node]["people"] for node in net.NODES_DATA["L2_GATES"]),
            0,
        )

    def test_cad_hall_staging_edges_use_one_shared_unit_scale(self):
        graph = net.build_graph()

        for source, target in [
            ("VN_L2_Hall_Arrival", "Gate_L2_N_West"),
            ("VN_L7_Hall_Arrival", "Gate_L7_N_West"),
            ("VN_L16_Hall_Arrival", "Gate_L16_N1"),
        ]:
            edge_target = graph.graph.get("gate_queue_area_nodes", {}).get(
                target,
                target,
            )
            raw_distance = math.dist(
                graph.nodes[source]["pos"], graph.nodes[edge_target]["pos"]
            )
            self.assertAlmostEqual(
                graph[source][edge_target]["length"],
                max(raw_distance * 0.01, 4.0),
            )

        # L18's existing split edge is also a correctly scaled CAD distance.
        source, target = "VN_L18_Hall_Arrival_Base", "VN_L18_Hall_Split_A"
        raw_distance = math.dist(
            graph.nodes[source]["pos"], graph.nodes[target]["pos"]
        )
        self.assertAlmostEqual(
            graph[source][target]["length"], max(raw_distance * 0.01, 4.0)
        )


class GuidanceRegressionTests(unittest.TestCase):
    def test_l2_adaptive_execution_keeps_one_next_hop_per_source(self):
        graph = net.build_graph()
        graph.nodes["Platform_L2_Z1_Wait"]["people"] = 50
        graph.nodes["Platform_L2_Z2_Wait"]["people"] = 69
        shortest = dict(nx.all_pairs_dijkstra_path_length(graph, weight="length"))

        used_hops = set()
        # The escalator admits less than one whole passenger in the first
        # half-second step, so retain flow credit and inspect two decisions.
        for _ in range(2):
            moves = net.get_step_moves(graph, spr.OUR_SINGLE_PATH_METHOD, shortest)
            step_hops = {v for u, v, amount in moves if amount > 0}
            used_hops.update(step_hops)
            self.assertLessEqual(len(step_hops), 2)

        self.assertTrue(used_hops)

    def test_l18_does_not_use_hidden_parallel_split_override(self):
        self.assertEqual(net.L18_LOCAL_PARALLEL_GATES, {})

    def test_fractional_guidance_reservation_is_disabled(self):
        self.assertFalse(hasattr(net, "_reserve_guidance_path"))

    def test_degradation_reference_survives_hold_and_triggers_switch(self):
        graph = nx.DiGraph()
        graph.add_node("source", type="area", people=10, area=10)
        graph.add_node("old_exit", type="exit", people=0, area=100)
        graph.add_node("new_exit", type="exit", people=0, area=100)
        graph.add_edge("source", "old_exit", sim_weight=100, length=1)
        graph.add_edge("source", "new_exit", sim_weight=120, length=1)
        shortest = {}

        first = [{"target": "old_exit", "path": ["source", "old_exit"],
                  "next_hop": "old_exit", "cost": 100.0}]
        hold = [{"target": "new_exit", "path": ["source", "new_exit"],
                 "next_hop": "new_exit", "cost": 105.0}]
        degraded = [{"target": "new_exit", "path": ["source", "new_exit"],
                     "next_hop": "new_exit", "cost": 147.0}]

        with patch.object(spr, "enumerate_exit_paths", side_effect=[first, hold, degraded]), \
             patch.object(net, "_path_total_cost", side_effect=[110.0, 151.0]):
            graph.graph["_sim_time"] = 0.0
            net._choose_our_single_path_with_inertia(
                graph, "source", shortest, spr.OUR_SINGLE_PATH_METHOD
            )

            graph["source"]["old_exit"]["sim_weight"] = 110.0
            graph.graph["_sim_time"] = 0.5
            held_path = net._choose_our_single_path_with_inertia(
                graph, "source", shortest, spr.OUR_SINGLE_PATH_METHOD
            )
            state = graph.graph["_our_guidance_state"]["source"]
            self.assertEqual(held_path[-1], "old_exit")
            self.assertEqual(state["selected_cost"], 100.0)
            self.assertEqual(state["decision_reason"], "hold")

            graph["source"]["old_exit"]["sim_weight"] = 151.0
            graph.graph["_sim_time"] = 1.0
            switched_path = net._choose_our_single_path_with_inertia(
                graph, "source", shortest, spr.OUR_SINGLE_PATH_METHOD
            )
            state = graph.graph["_our_guidance_state"]["source"]
            self.assertEqual(switched_path[-1], "new_exit")
            self.assertEqual(state["decision_reason"], "degraded")

    def test_guidance_switch_restores_legacy_cost_reference(self):
        graph = nx.DiGraph()
        graph.graph["guidance_corrections_enabled"] = False
        graph.add_node("source", type="area", people=10, area=10)
        graph.add_node("old_exit", type="exit", people=0, area=100)
        graph.add_node("new_exit", type="exit", people=0, area=100)
        graph.add_edge("source", "old_exit", sim_weight=100, length=1)
        graph.add_edge("source", "new_exit", sim_weight=120, length=1)
        first = [{"target": "old_exit", "path": ["source", "old_exit"],
                  "next_hop": "old_exit", "cost": 100.0}]
        hold = [{"target": "new_exit", "path": ["source", "new_exit"],
                 "next_hop": "new_exit", "cost": 105.0}]

        with patch.object(spr, "enumerate_exit_paths", side_effect=[first, hold]), \
             patch.object(net, "_path_total_cost", return_value=110.0):
            graph.graph["_sim_time"] = 0.0
            net._choose_our_single_path_with_inertia(
                graph, "source", {}, spr.OUR_SINGLE_PATH_METHOD
            )
            graph["source"]["old_exit"]["sim_weight"] = 110.0
            graph.graph["_sim_time"] = 0.5
            net._choose_our_single_path_with_inertia(
                graph, "source", {}, spr.OUR_SINGLE_PATH_METHOD
            )

        state = graph.graph["_our_guidance_state"]["source"]
        self.assertEqual(state["selected_cost"], 110.0)


class PaperImprovedAStarRegressionTests(unittest.TestCase):
    def test_paper_edge_cost_uses_literature_density_speed_by_default(self):
        graph = nx.DiGraph()
        graph.add_node("u", type="area", people=0, area=100)
        graph.add_node("v", type="area", people=0, area=10)
        graph.add_edge("u", "v", length=10, capacity=10)

        density = 2.0
        expected_speed = min(
            spr.paper_speed_from_density(density),
            spr.paper_facility_speed_limit(graph, "u", "v"),
        )
        expected = (
            spr.PAPER_LENGTH_ALPHA * 10.0
            + spr.PAPER_SPEED_BETA * (10.0 / expected_speed)
        )
        self.assertAlmostEqual(
            spr.paper_edge_cost_from_density(graph, "u", "v", density),
            expected,
        )

    def test_paper_edge_cost_blocks_density_above_paper_threshold(self):
        graph = nx.DiGraph()
        graph.add_node("u", type="area", people=0, area=100)
        graph.add_node("v", type="area", people=35, area=10)
        graph.add_edge("u", "v", length=10, capacity=10, width_limit=1)

        cost = spr.paper_edge_cost_from_density(
            graph, "u", "v", 3.5
        )

        self.assertTrue(math.isinf(cost))
        self.assertGreater(cost, 0)

    def test_paper_plan_reads_current_step_sim_weight(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.add_node("s", type="area", people=1, area=10)
        graph.add_node(
            "crowded_gate", type="gate_wide", people=4, area=1
        )
        graph.add_node("open", type="area", people=0, area=10)
        graph.add_node("exit", type="exit", people=0, area=10)
        graph.add_edge("s", "crowded_gate", length=1, capacity=10)
        graph.add_edge(
            "crowded_gate", "exit", length=1, capacity=10
        )
        graph.add_edge("s", "open", length=2, capacity=10)
        graph.add_edge("open", "exit", length=2, capacity=10)

        net._paper_refresh_temporary_high_cost_weights(graph)
        path = net._paper_plan_path(graph, "s")

        self.assertEqual(path, ["s", "open", "exit"])
        self.assertTrue(graph.has_edge("s", "crowded_gate"))

    def test_paper_plan_returns_none_when_all_routes_are_density_blocked(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.add_node("s", type="area", people=1, area=10)
        graph.add_node(
            "crowded_gate", type="gate_wide", people=4, area=1
        )
        graph.add_node("exit", type="exit", people=0, area=10)
        graph.add_edge("s", "crowded_gate", length=1, capacity=10)
        graph.add_edge("crowded_gate", "exit", length=1, capacity=10)

        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)

        self.assertIn(("s", "crowded_gate"), active)
        self.assertIsNone(net._paper_plan_path(graph, "s"))

    def test_paper_refresh_keeps_gate_switch_edges_unavailable(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.add_node("queue_a", type="queue_area", people=0, area=10)
        graph.add_node("queue_b", type="queue_area", people=0, area=10)
        graph.add_node("gate", type="gate", people=0, area=1, capacity=10)
        graph.add_node("exit", type="exit", people=0, area=10)
        graph.add_edge("queue_a", "gate", length=1, capacity=10)
        graph.add_edge("gate", "exit", length=1, capacity=10)
        graph.add_edge(
            "queue_a",
            "queue_b",
            length=0.01,
            capacity=10,
            gate_switch_only=True,
        )
        graph.add_edge("queue_b", "exit", length=0.01, capacity=10)

        active, _ = net._paper_refresh_temporary_high_cost_weights(graph)

        self.assertNotIn(("queue_a", "queue_b"), active)
        self.assertTrue(
            math.isinf(graph["queue_a"]["queue_b"]["sim_weight"])
        )
        path = net._paper_plan_path(graph, "queue_a")
        self.assertEqual(path, ["queue_a", "gate", "exit"])

    def test_unaffected_cached_paper_path_is_not_replanned(self):
        graph = nx.DiGraph()
        graph.add_node("s", type="area", people=2, area=10)
        graph.add_node("a", type="area", people=0, area=10)
        graph.add_node("exit", type="exit", people=0, area=10)
        graph.add_node("unrelated", type="area", people=40, area=10)
        graph.add_edge("s", "a", length=1, capacity=10)
        graph.add_edge("a", "exit", length=1, capacity=10)
        graph.graph["_paper_path_by_node"] = {"s": ["s", "a", "exit"]}
        graph.graph["_paper_fixed_next_by_node"] = {"s": "a"}
        graph.graph["_paper_high_cost_signature"] = ()

        with patch.object(net, "_paper_plan_path") as plan:
            moves = net._get_paper_step_moves(graph, ["s"])

        plan.assert_not_called()
        self.assertEqual(moves, [("s", "a", 2)])


class EvaluationRegressionTests(unittest.TestCase):
    def test_deprecated_composite_score_has_no_congestion_component(self):
        total = 1000.0
        metrics = {
            "time": comparison.J_HIGH_LOAD_REFERENCES["t100_s"],
            "evacuation_curve": {},
            "queueing_time": comparison.J_HIGH_LOAD_REFERENCES["queue_s_per_person"] * total,
            "high_density_exposure_person_seconds": 1_000_000.0,
            "spatial_blocked_exposure_person_seconds": 1_000_000.0,
            "exit_usage": {f"exit_{idx}": total / 10.0 for idx in range(10)},
        }
        with patch.object(comparison, "MODE", 4), patch.object(
            comparison, "compute_R_area",
            return_value=comparison.J_HIGH_LOAD_REFERENCES["r_area_s_per_person"],
        ):
            result = comparison.compute_composite_J(metrics, total)

        self.assertEqual(result["j_version"], "high_load_v2")
        self.assertNotIn("severe", result["j_components"])
        self.assertNotIn("congestion", result["j_components"])
        self.assertAlmostEqual(result["j_score"], 0.8)
        self.assertAlmostEqual(sum(result["j_components"].values()), result["j_score"])


class PhysicalConsistencyRegressionTests(unittest.TestCase):
    def _shared_gate_graph(self, capacity=2.0):
        graph = nx.DiGraph()
        graph.graph["density_dependent_flow"] = False
        graph.graph["spillback_enabled"] = False
        graph.add_node("u1", type="area", people=10, area=10)
        graph.add_node("u2", type="area", people=10, area=10)
        graph.add_node("gate", type="gate", people=0, area=10, capacity=capacity)
        graph.add_edge("u1", "gate", capacity=capacity, length=1)
        graph.add_edge("u2", "gate", capacity=capacity, length=1)
        return graph

    def test_two_incoming_edges_share_one_gate_capacity(self):
        graph = self._shared_gate_graph(capacity=2.0)
        with patch.object(net, "DELTA_T", 1.0):
            moves = net._integerize_moves(
                graph, [("u1", "gate", 10), ("u2", "gate", 10)]
            )
        self.assertEqual(sum(amount for _, _, amount in moves), 2)

    def test_fractional_resource_credit_has_correct_long_run_average(self):
        graph = self._shared_gate_graph(capacity=1.5)
        totals = []
        with patch.object(net, "DELTA_T", 1.0):
            for _ in range(4):
                moves = net._integerize_moves(
                    graph, [("u1", "gate", 10), ("u2", "gate", 10)]
                )
                totals.append(sum(amount for _, _, amount in moves))
        self.assertEqual(totals, [1, 2, 1, 2])

    def test_shared_resource_rotates_equal_priority_sources(self):
        graph = self._shared_gate_graph(capacity=1.0)
        winners = []
        with patch.object(net, "DELTA_T", 1.0):
            for _ in range(2):
                moves = net._integerize_moves(
                    graph, [("u1", "gate", 10), ("u2", "gate", 10)]
                )
                winners.append(moves[0][0])
        self.assertEqual(winners, ["u1", "u2"])

    def test_routing_and_scheduler_share_physical_travel_time(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.add_node(
            "u", type="area", people=1, area=10,
            people_dict={"L2": 1}, source_group_dict={},
        )
        graph.add_node("v", type="area", people=0, area=10)
        graph.add_edge("u", "v", length=2.0, capacity=10, edge_type="hall_to_gate")
        spr.bind_physical_callbacks(net.physical_edge_travel_time, net._edge_effective_flow_capacity)
        expected = net.physical_edge_travel_time(graph, "u", "v")
        self.assertAlmostEqual(spr.physical_edge_travel_time(graph, "u", "v"), expected)
        scheduled = net._schedule_moves_as_transit(graph, [("u", "v", 1)])
        self.assertAlmostEqual(scheduled[0]["travel_time"], expected)

    def test_undefined_configured_node_raises(self):
        bad_edge = {
            "u": "missing_source", "v": "Exit_L2_2", "length": 1,
            "width_limit": 1, "edge_type": "gate_to_exit",
        }
        with patch.object(net, "EDGES_DATA", list(net.EDGES_DATA) + [bad_edge]):
            with self.assertRaises(ValueError):
                net.build_graph()

    def test_direction_is_stripped_and_validated(self):
        self.assertEqual(
            net.calculate_gb_capacity_per_second("stair", 2.0, " up"),
            net.calculate_gb_capacity_per_second("stair", 2.0, "up"),
        )
        with self.assertRaises(ValueError):
            net.calculate_gb_capacity_per_second("stair", 2.0, "sideways")

    def test_time_limit_is_not_reported_as_completion(self):
        graph = net.build_graph()
        metrics = net._run_simulation_for_metrics_core(
            graph, spr.PAPER_SINGLE_PATH_METHOD, {"L2": 1.0}, stop_at_time=0.0
        )
        self.assertFalse(metrics["completed"])
        self.assertEqual(metrics["termination_reason"], "time_limit")
        self.assertEqual(metrics["remaining_people"], 1.0)

    def test_integer_people_are_conserved_when_scheduled(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.add_node(
            "u", type="area", people=7, area=10,
            people_dict={"L2": 7}, source_group_dict={},
        )
        graph.add_node(
            "v", type="area", people=0, area=10,
            people_dict={"L2": 0}, source_group_dict={},
        )
        graph.add_edge("u", "v", length=1, capacity=10, edge_type="hall_to_gate")
        initial = sum(int(graph.nodes[n]["people"]) for n in graph.nodes)
        net._schedule_moves_as_transit(graph, [("u", "v", 3)])
        remaining = sum(int(graph.nodes[n]["people"]) for n in graph.nodes)
        in_transit = sum(int(item["amount"]) for item in graph.graph["_transit_queue"])
        self.assertEqual(remaining + in_transit, initial)

    def test_gate_area_is_not_spatial_storage_but_capacity_still_applies(self):
        graph = self._shared_gate_graph(capacity=2.0)
        graph.nodes["gate"].update(
            area=6.0,
            density_exempt=True,
            spatial_storage_enabled=False,
        )
        self.assertTrue(math.isinf(net._node_storage_capacity(graph, "gate")))
        self.assertEqual(net._evaluation_node_physical_state(graph, "gate"), (0.0, 0.0, 0.0))
        with patch.object(net, "DELTA_T", 1.0):
            moves = net._integerize_moves(
                graph, [("u1", "gate", 10), ("u2", "gate", 10)]
            )
        self.assertEqual(sum(amount for _, _, amount in moves), 2)

    def test_spatial_storage_uses_area_times_selected_jam_density(self):
        graph = nx.DiGraph()
        graph.graph["receiving_jam_density"] = 5.0
        graph.add_node("hall", type="area", people=0, area=10.0)
        with patch.object(spr, "PAPER_DENSITY_JAM", 5.0):
            self.assertEqual(net._node_storage_capacity(graph, "hall"), 50.0)

    def test_independent_gates_have_independent_capacity_buckets(self):
        graph = nx.DiGraph()
        graph.graph["density_dependent_flow"] = False
        graph.graph["spillback_enabled"] = False
        for source in ("u1", "u2"):
            graph.add_node(source, type="area", people=10, area=10)
        for gate in ("Gate_A", "Gate_B"):
            graph.add_node(gate, type="gate", people=0, area=2, capacity=2)
        graph.add_edge("u1", "Gate_A", capacity=2, length=1)
        graph.add_edge("u2", "Gate_B", capacity=2, length=1)
        with patch.object(net, "DELTA_T", 1.0):
            moves = net._integerize_moves(
                graph, [("u1", "Gate_A", 10), ("u2", "Gate_B", 10)]
            )
        self.assertEqual(sum(amount for _, _, amount in moves), 4)
        self.assertNotEqual(
            net.edge_resource_id(graph, "u1", "Gate_A"),
            net.edge_resource_id(graph, "u2", "Gate_B"),
        )

    def test_facility_capacity_is_not_consumed_again_on_exit_edge(self):
        graph = nx.DiGraph()
        graph.add_node("u", type="area", people=10, area=10)
        graph.add_node("gate", type="gate", people=0, area=2, capacity=2)
        graph.add_node("downstream", type="area", people=0, area=10)
        graph.add_edge("u", "gate", capacity=2, length=1)
        graph.add_edge("gate", "downstream", capacity=100, length=1)
        self.assertEqual(net.edge_resource_id(graph, "u", "gate"), ("facility", "gate"))
        self.assertEqual(
            net.edge_resource_id(graph, "gate", "downstream"),
            ("edge", "gate", "downstream"),
        )

        built = net.build_graph()
        self.assertGreater(
            built["Stair_L2_1"]["VN_L2_Corner_1"]["capacity"],
            built.nodes["Stair_L2_1"]["capacity"],
        )

    def test_exit_opening_width_is_separate_from_long_corridor_width(self):
        graph = net.build_graph()
        exit_l2_4 = graph.nodes["Exit_L2_4"]
        edge_l2_4 = graph["Gate_L2_S_West"]["Exit_L2_4"]
        self.assertAlmostEqual(float(exit_l2_4["width"]), 3.3)
        self.assertAlmostEqual(float(exit_l2_4["exit_opening_width_m"]), 3.3)
        self.assertFalse(spr.is_capacity_service_node(graph, "Exit_L2_4"))
        self.assertTrue(math.isinf(float(exit_l2_4["capacity"])))
        self.assertAlmostEqual(float(edge_l2_4["width_limit"]), 7.6)
        self.assertAlmostEqual(
            float(edge_l2_4["capacity"]),
            net.calculate_gb_capacity_per_second("passageway", 7.6),
        )

        exit_l2_6 = graph.nodes["Exit_L2_6"]
        edge_l2_6 = graph["Gate_L2_N_East"]["Exit_L2_6"]
        self.assertAlmostEqual(float(exit_l2_6["width"]), 7.6)
        self.assertAlmostEqual(float(edge_l2_6["width_limit"]), 5.2)
        self.assertAlmostEqual(
            float(edge_l2_6["capacity"]),
            net.calculate_gb_capacity_per_second("passageway", 5.2),
        )

    def test_final_exit_opening_does_not_become_aa_service_resource(self):
        graph = net.build_graph()
        self.assertEqual(
            net.edge_resource_id(graph, "Stair_Maglev_Exit18", "Exit_Maglev_18"),
            ("edge", "Stair_Maglev_Exit18", "Exit_Maglev_18"),
        )
        self.assertEqual(
            net.edge_resource_id(graph, "Escalator_Maglev_Exit18", "Exit_Maglev_18"),
            ("edge", "Escalator_Maglev_Exit18", "Exit_Maglev_18"),
        )

    def test_built_service_resources_are_independent_and_nonspatial(self):
        graph = net.build_graph()
        facility_resources = {
            net.edge_resource_id(graph, u, v)
            for u, v in graph.edges()
            if net.edge_resource_id(graph, u, v)[0] == "facility"
        }
        facility_nodes = {resource_id[1] for resource_id in facility_resources}
        self.assertEqual(len(facility_resources), len(facility_nodes))
        for resource_id in facility_resources:
            node = resource_id[1]
            if str(graph.nodes[node].get("type", "")).lower().startswith("gate"):
                self.assertTrue(net.uses_spatial_storage(graph, node))
                self.assertTrue(math.isfinite(net._node_storage_capacity(graph, node)))
            else:
                self.assertFalse(net.uses_spatial_storage(graph, node))
            self.assertTrue(all(v == node for u, v in net.resource_control_edges(graph, resource_id)))
            self.assertTrue(all(
                net.edge_resource_id(graph, u, v) != resource_id
                for u, v in graph.out_edges(node)
            ))

    def test_density_thresholds_are_ordered_and_severe_is_reachable(self):
        self.assertLess(
            net.MODERATE_CONGESTION_DENSITY_THRESHOLD,
            net.SEVERE_CONGESTION_DENSITY_THRESHOLD,
        )
        self.assertLessEqual(
            net.SEVERE_CONGESTION_DENSITY_THRESHOLD,
            net.HIGH_LOAD_JAM_DENSITY_P_PER_M2,
        )
        graph = nx.DiGraph()
        graph.graph["density_dependent_flow"] = True
        graph.add_node("hall", type="area", people=15, area=4)
        density, _, _ = net._evaluation_node_physical_state(graph, "hall")
        self.assertGreater(density, net.SEVERE_CONGESTION_DENSITY_THRESHOLD)
        self.assertLess(density, net.HIGH_LOAD_JAM_DENSITY_P_PER_M2)

    def test_euclidean_fallback_distance_is_retained(self):
        graph = net.build_graph()
        u, v, distance = next(
            row for row in graph.graph["euclidean_fallback_edges"]
            if graph.has_edge(row[0], row[1])
        )
        pos_u, pos_v = graph.nodes[u]["pos"], graph.nodes[v]["pos"]
        expected = math.hypot(pos_u[0] - pos_v[0], pos_u[1] - pos_v[1]) * 0.01
        self.assertAlmostEqual(distance, expected)
        self.assertEqual(
            graph[u][v]["distance_source"], "euclidean_fallback"
        )


class CumulativeEtaRegressionTests(unittest.TestCase):
    def test_later_resource_uses_full_cumulative_eta(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 100.0
        graph.graph["_resource_queues"] = {
            ("facility", "gate1"): 20.0,
            ("facility", "gate2"): 1.0,
        }
        graph.add_nodes_from([
            ("s", {"type": "area"}),
            ("a", {"type": "area"}),
            ("gate1", {"type": "gate", "capacity": 1}),
            ("gate2", {"type": "gate", "capacity": 1}),
        ])
        graph.add_edge("s", "a", length=1, capacity=100)
        graph.add_edge("a", "gate1", length=1, capacity=1)
        graph.add_edge("gate1", "gate2", length=1, capacity=1)
        travel_times = {("s", "a"): 10.0, ("a", "gate1"): 30.0, ("gate1", "gate2"): 0.0}
        observed = {}

        def predicted(_graph, resource_id, target_time):
            observed[resource_id] = target_time
            return 20.0 if resource_id == ("facility", "gate1") else 0.0

        with patch.object(spr, "physical_edge_travel_time", side_effect=lambda G, u, v: travel_times[(u, v)]), \
             patch.object(spr, "resource_capacity_per_second", return_value=1.0), \
             patch.object(spr, "predicted_resource_queue_at_time", side_effect=predicted):
            total, details = spr.evaluate_candidate_path_with_cumulative_eta(
                graph,
                ["s", "a", "gate1", "gate2"],
                spr.OUR_SINGLE_PATH_METHOD,
            )

        self.assertEqual(total, 61.0)
        self.assertEqual(observed[("facility", "gate2")], 160.5)
        self.assertEqual(details[-1]["resource_entry_time"], 160.5)

    def test_retained_and_new_paths_share_the_same_evaluator(self):
        graph = nx.DiGraph()
        graph.add_edge("a", "b")
        with patch.object(
            spr,
            "evaluate_candidate_path_with_cumulative_eta",
            return_value=(12.0, []),
        ) as evaluator:
            self.assertEqual(spr._aa_live_path_cost(graph, ["a", "b"], spr.OUR_SINGLE_PATH_METHOD), 12.0)
            self.assertEqual(net._path_total_cost(graph, ["a", "b"], spr.OUR_SINGLE_PATH_METHOD), 12.0)
        self.assertEqual(evaluator.call_count, 2)


class AAQueueAndBatchServiceCostRegressionTests(unittest.TestCase):
    def _single_gate_graph(self, *, queue=10.0, capacity=2.0, people=0):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_aa_round_prediction_events"] = []
        graph.graph["_aa_round_queue_adjustment"] = {}
        graph.graph["_aa_queue_adjustment_versions"] = {}
        graph.graph["density_dependent_flow"] = False
        graph.add_node(
            "Source",
            type="area",
            people=people,
            area=100,
            people_dict={"L2": people},
            source_group_dict={"L2_train_1": people} if people else {},
        )
        graph.add_node(
            "Gate",
            type="gate",
            people=0,
            area=10,
            capacity=capacity,
            people_dict={"L2": 0},
            source_group_dict={},
        )
        graph.add_node(
            "Exit",
            type="exit",
            people=0,
            area=100,
            people_dict={"L2": 0},
            source_group_dict={},
        )
        graph.add_edge("Source", "Gate", length=3.0, capacity=100.0)
        graph.add_edge("Gate", "Exit", length=0.0, capacity=100.0)
        resource = spr.edge_resource_id(graph, "Source", "Gate")
        graph.graph["_resource_queues"] = {resource: float(queue)}
        return graph, resource

    def _cost_patches(self):
        return patch.multiple(
            spr,
            physical_edge_travel_time=(
                lambda G, u, v: float(G[u][v]["length"])
            ),
            predicted_spatial_wait=lambda G, node, eta, amount=1: 0.0,
            predicted_spatial_density=lambda G, node, eta, amount=0: 0.0,
        )

    def test_facility_cost_includes_queue_and_current_batch_service(self):
        graph, resource = self._single_gate_graph()
        with self._cost_patches():
            total, details = spr.evaluate_candidate_path_with_cumulative_eta(
                graph,
                ["Source", "Gate", "Exit"],
                spr.OUR_SINGLE_PATH_METHOD,
                amount=20,
            )
        gate_detail = next(
            item for item in details if item["resource_id"] == resource
        )
        self.assertEqual(gate_detail["predicted_queue"], 10.0)
        self.assertEqual(gate_detail["predicted_wait"], 5.0)
        self.assertEqual(gate_detail["current_batch_gate_service_time"], 5.0)
        self.assertEqual(gate_detail["arrival_time"], 13.0)
        self.assertEqual(total, 13.0)

    def test_batch_size_changes_facility_service_cost(self):
        graph, resource = self._single_gate_graph()
        observed = []
        with self._cost_patches():
            for amount in (1, 20, 100):
                total, details = spr.evaluate_candidate_path_with_cumulative_eta(
                    graph,
                    ["Source", "Gate", "Exit"],
                    spr.OUR_SINGLE_PATH_METHOD,
                    amount=amount,
                )
                gate_detail = next(
                    item for item in details if item["resource_id"] == resource
                )
                observed.append((
                    gate_detail["predicted_wait"],
                    gate_detail["current_batch_gate_service_time"],
                    total,
                ))
        self.assertEqual(observed, [
            (5.0, 0.25, 8.25),
            (5.0, 5.0, 13.0),
            (5.0, 25.0, 33.0),
        ])

    def test_current_batch_is_removed_from_its_own_queue_ahead(self):
        graph, resource = self._single_gate_graph(queue=20.0)
        graph.graph["_aa_round_queue_adjustment"] = {resource: -20.0}
        with self._cost_patches():
            total, details = spr.evaluate_candidate_path_with_cumulative_eta(
                graph,
                ["Source", "Gate", "Exit"],
                spr.OUR_SINGLE_PATH_METHOD,
                amount=20,
            )
        gate_detail = next(
            item for item in details if item["resource_id"] == resource
        )
        self.assertEqual(gate_detail["predicted_queue"], 0.0)
        self.assertEqual(gate_detail["predicted_wait"], 0.0)
        self.assertEqual(gate_detail["current_batch_gate_service_time"], 5.0)
        self.assertEqual(total, 8.0)

    def test_earlier_batch_intent_is_seen_by_later_batch(self):
        graph, resource = self._single_gate_graph(queue=0.0)
        graph.graph["_aa_round_queue_adjustment"] = {resource: 10.0}
        with self._cost_patches():
            path, _, details = spr.time_dependent_astar(
                graph,
                "Source",
                amount=20,
            )
        gate_detail = next(
            item for item in details if item["resource_id"] == resource
        )
        self.assertEqual(path, ["Source", "Gate", "Exit"])
        self.assertEqual(gate_detail["predicted_queue"], 10.0)
        self.assertEqual(gate_detail["predicted_wait"], 5.0)
        self.assertEqual(gate_detail["current_batch_gate_service_time"], 5.0)

    def test_partial_acceptance_preserves_population_and_residual_batch(self):
        graph, resource = self._single_gate_graph(
            queue=0.0,
            capacity=2.0,
            people=20,
        )
        batch = net._ensure_node_aa_batches(graph, "Source")[0]
        batch["current_path"] = ["Source", "Gate", "Exit"]
        batch["waiting_resource"] = resource
        request = {
            "u": "Source",
            "v": "Gate",
            "requested": 20,
            "batch_id": batch["batch_id"],
            "source_group": batch["source_group"],
            "arrival_time": 0.0,
            "queue_enter_time": 0.0,
            "current_path": ["Source", "Gate", "Exit"],
            "waiting_resource": resource,
            "path_predictions": [],
            "rerouted_this_step": False,
        }
        moves = net._integerize_aa_batch_requests(graph, [request])
        scheduled = net._schedule_moves_as_transit(graph, moves)
        transit_people = sum(
            int(item["amount"])
            for item in graph.graph["_transit_queue"]
        )
        remaining_batch = graph.nodes["Source"]["_aa_batches"][0]
        self.assertEqual(sum(item["amount"] for item in scheduled), 2)
        self.assertEqual(transit_people, 2)
        self.assertEqual(graph.nodes["Source"]["people"], 18)
        self.assertEqual(remaining_batch["amount"], 18)
        self.assertFalse(remaining_batch.get("service_committed", False))
        self.assertEqual(graph.nodes["Source"]["people"] + transit_people, 20)

    def test_parallel_gate_ranking_accounts_for_batch_service_time(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_resource_queues"] = {}
        graph.graph["_aa_round_prediction_events"] = []
        graph.add_node("Decision", type="area", area=100)
        graph.add_node("Gate_A", type="gate", capacity=1.0, area=10)
        graph.add_node("Gate_B", type="gate", capacity=100.0, area=10)
        graph.add_node("Exit", type="exit", area=100)
        graph.add_edge("Decision", "Gate_A", length=1.0, capacity=100.0)
        graph.add_edge("Decision", "Gate_B", length=2.0, capacity=100.0)
        graph.add_edge("Gate_A", "Exit", length=0.0, capacity=100.0)
        graph.add_edge("Gate_B", "Exit", length=0.0, capacity=100.0)
        selected = []
        costs = []
        with self._cost_patches():
            for amount in (5, 50, 100):
                path, cost, _ = spr.time_dependent_astar(
                    graph,
                    "Decision",
                    amount=amount,
                )
                selected.append(path[1])
                costs.append(cost)
        self.assertEqual(selected, ["Gate_B", "Gate_B", "Gate_B"])
        for actual, expected in zip(costs, (2.025, 2.25, 2.5)):
            self.assertAlmostEqual(actual, expected)

    def test_all_capacity_facility_types_include_batch_service_time(self):
        graph = nx.DiGraph()
        graph.add_node("Gate", type="gate", capacity=2.0)
        graph.add_node("Stair", type="stair", capacity=2.0)
        graph.add_node("Escalator", type="escalator", capacity=2.0)
        for node in ("Gate", "Stair", "Escalator"):
            self.assertEqual(
                spr.aa_current_batch_gate_service_time(
                    graph,
                    ("facility", node),
                    100,
                ),
                25.0,
            )
        graph.add_node("Area", type="area")
        graph.add_edge("Area", "Gate", capacity=2.0)
        self.assertEqual(
            spr.aa_current_batch_gate_service_time(
                graph,
                ("edge", "Area", "Gate"),
                100,
            ),
            0.0,
        )
        graph.add_node("Source", type="area")
        graph.add_node("UnreachableExit", type="exit")
        diagnostic = spr.diagnose_time_dependent_exit_candidates(
            graph,
            "Source",
            0.0,
            100,
            ("UnreachableExit",),
        )[0]
        self.assertEqual(diagnostic["current_batch_gate_service_time"], 0.0)
        self.assertEqual(
            diagnostic["current_batch_gate_service_time_formula"],
            0.0,
        )

    def test_candidate_diagnostic_exposes_terminal_edge_discharge_gap(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_resource_queues"] = {}
        graph.add_node("Source", type="area", area=100)
        graph.add_node("Exit_slow", type="exit", area=100)
        graph.add_node("Exit_fast", type="exit", area=100)
        graph.add_edge("Source", "Exit_slow", length=1.0, capacity=2.0)
        graph.add_edge("Source", "Exit_fast", length=1.0, capacity=10.0)
        with self._cost_patches():
            rows = spr.diagnose_time_dependent_exit_candidates(
                graph,
                "Source",
                0.0,
                20,
                ("Exit_slow", "Exit_fast"),
            )
        by_exit = {row["candidate_exit"]: row for row in rows}
        self.assertAlmostEqual(
            by_exit["Exit_slow"]["terminal_edge_batch_mean_discharge_time"],
            5.0,
        )
        self.assertAlmostEqual(
            by_exit["Exit_fast"]["terminal_edge_batch_mean_discharge_time"],
            1.0,
        )
        for row in rows:
            self.assertAlmostEqual(
                row["objective_with_terminal_discharge_diagnostic"],
                row["objective_cost"]
                + row["terminal_edge_batch_mean_discharge_time"],
            )


class MesoscopicCohortRoutingTests(unittest.TestCase):
    def _base_graph(self, people=10, capacity=4.0):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_resource_flow_credit"] = {}
        graph.graph["density_dependent_flow"] = False
        graph.add_node(
            "u", type="area", people=people, area=100,
            people_dict={"L2": people}, source_group_dict={"L2_train_1": people},
        )
        graph.add_node(
            "v", type="area", people=0, area=100,
            people_dict={"L2": 0}, source_group_dict={},
        )
        graph.add_edge("u", "v", length=1, capacity=capacity)
        return graph

    def test_node_stock_is_bounded_by_real_departure_budget(self):
        graph = self._base_graph(people=1000, capacity=8.0)
        # The edge capacity is people/second and DELTA_T is one second. No
        # receiving or density limit is active in this isolated graph.
        self.assertEqual(net.node_integer_departure_budget(graph, "u"), 8)

    def test_no_fixed_cohort_size_parameter(self):
        source = inspect.getsource(net) + inspect.getsource(spr)
        for forbidden in ("COHORT_SIZE", "GROUP_SIZE", "MAX_BATCH_SIZE"):
            self.assertNotIn(forbidden, source)

    def test_only_physically_accepted_people_receive_commitment(self):
        graph = self._base_graph(people=10, capacity=4.0)
        cohorts = net._ensure_node_mesoscopic_cohorts(graph, "u")
        request = {
            "u": "u", "v": "v", "requested": 10,
            "cohort_id": cohorts[0]["cohort_id"], "source_group": "L2_train_1",
            "arrival_time": 0.0, "committed_segment": ["u", "v"],
            "segment_index": 0, "next_decision_node": "v",
        }
        moves = net._integerize_mesoscopic_requests(graph, [request])
        scheduled = net._schedule_moves_as_transit(graph, moves)
        self.assertEqual(sum(item["amount"] for item in scheduled), 4)
        self.assertEqual(graph.nodes["u"]["people"], 6)
        self.assertEqual(sum(item["amount"] for item in graph.graph["_transit_queue"]), 4)
        self.assertTrue(graph.graph["_transit_queue"][0]["cohort_state"]["committed"])

    def test_committed_cohort_does_not_replan_at_intermediate_node(self):
        graph = self._base_graph(people=1, capacity=10.0)
        graph = nx.relabel_nodes(graph, {"u": "middle", "v": "decision"})
        graph.nodes["middle"]["_mesoscopic_cohorts"] = [{
            "cohort_id": "c", "source_group": "L2_train_1", "arrival_time": 0.0,
            "amount": 1, "committed_segment": ["start", "middle", "decision"],
            "segment_index": 1, "next_decision_node": "decision", "committed": True,
        }]
        with patch.object(spr, "mesoscopic_full_graph_path", side_effect=AssertionError("replanned")):
            moves = net._get_mesoscopic_step_moves(
                graph, ["middle"], {}, spr.MESOSCOPIC_PHYSICAL_TIME_METHOD
            )
        self.assertEqual(moves[0][:2], ("middle", "decision"))
        self.assertEqual(graph.graph.get("_mesoscopic_diagnostics", {}).get("nondecision_replan_count", 0), 0)

    def test_uncommitted_batch_can_plan_again_next_step(self):
        graph = self._base_graph(people=1, capacity=10.0)
        graph.add_node("exit", type="exit", people=0, people_dict={"L2": 0}, source_group_dict={})
        graph.add_edge("v", "exit", length=1, capacity=10)
        with patch.object(spr, "mesoscopic_full_graph_path", return_value=["u", "v", "exit"]) as planner:
            net._get_mesoscopic_step_moves(
                graph, ["u"], {}, spr.MESOSCOPIC_PHYSICAL_TIME_METHOD
            )
        planner.assert_called_once()

    def test_full_graph_current_queue_search_can_choose_fourth_route(self):
        graph = nx.DiGraph()
        graph.graph["_resource_queues"] = {}
        graph.add_node("s", type="area")
        graph.add_node("exit", type="exit")
        for index in range(4):
            gate = f"gate{index}"
            graph.add_node(gate, type="gate", capacity=1)
            graph.add_edge("s", gate, length=1 if index < 3 else 2, capacity=1)
            graph.add_edge(gate, "exit", length=1, capacity=10)
            if index < 3:
                graph.graph["_resource_queues"][spr.edge_resource_id(graph, "s", gate)] = 20
        with patch.object(spr, "physical_edge_travel_time", side_effect=lambda G, u, v: G[u][v]["length"]), \
             patch.object(spr, "resource_capacity_per_second", return_value=1.0):
            path = spr.mesoscopic_full_graph_path(
                graph, "s", spr.MESOSCOPIC_CURRENT_QUEUE_METHOD, {}
            )
        self.assertEqual(path[1], "gate3")

    def test_formal_mesoscopic_methods_do_not_call_legacy_inertia(self):
        source = inspect.getsource(net._get_mesoscopic_step_moves)
        self.assertNotIn("_choose_our_single_path_with_inertia", source)
        self.assertNotIn("K_CANDIDATE_PATHS", inspect.getsource(spr.mesoscopic_full_graph_path))

    def test_arrival_at_decision_node_clears_old_segment(self):
        graph = self._base_graph(people=0, capacity=10)
        graph.nodes["v"]["routing_decision"] = True
        graph.graph["_transit_queue"] = [{
            "arrive_time": 1.0, "u": "u", "v": "v", "amount": 1,
            "line_shares": {"L2": 1}, "source_group_shares": {"L2_train_1": 1},
            "cohort_state": {
                "cohort_id": "child", "source_group": "L2_train_1", "amount": 1,
                "arrival_time": 0.0, "committed_segment": ["u", "v"],
                "segment_index": 1, "next_decision_node": "v", "committed": True,
            },
        }]
        net._process_transit_arrivals(graph, 1.0)
        arrived = graph.nodes["v"]["_mesoscopic_cohorts"][0]
        self.assertFalse(arrived["committed"])
        self.assertEqual(arrived["committed_segment"], [])

    def test_different_natural_batches_may_choose_different_next_hops(self):
        graph = self._base_graph(people=2, capacity=10)
        graph.add_node("w", type="area", people=0, area=100,
                       people_dict={"L2": 0}, source_group_dict={})
        graph.add_node("exit", type="exit", people=0,
                       people_dict={"L2": 0}, source_group_dict={})
        graph.add_edge("u", "w", length=1, capacity=10)
        graph.add_edge("v", "exit", length=1, capacity=10)
        graph.add_edge("w", "exit", length=1, capacity=10)
        graph.nodes["u"]["source_group_dict"] = {"L2_train_1": 1, "L2_train_2": 1}
        graph.nodes["u"]["_mesoscopic_cohorts"] = [
            {"cohort_id": "a", "source_group": "L2_train_1", "arrival_time": 0,
             "amount": 1, "committed_segment": [], "segment_index": 0,
             "next_decision_node": None, "committed": False},
            {"cohort_id": "b", "source_group": "L2_train_2", "arrival_time": 1,
             "amount": 1, "committed_segment": [], "segment_index": 0,
             "next_decision_node": None, "committed": False},
        ]
        with patch.object(
            spr, "mesoscopic_full_graph_path",
            side_effect=[["u", "v", "exit"], ["u", "w", "exit"]],
        ):
            first = net._mesoscopic_path_for_step(
                graph, "u", spr.MESOSCOPIC_PHYSICAL_TIME_METHOD, {}
            )
            graph.graph["_sim_time"] = 0.5
            second = net._mesoscopic_path_for_step(
                graph, "u", spr.MESOSCOPIC_PHYSICAL_TIME_METHOD, {}
            )
        self.assertEqual(first[1], "v")
        self.assertEqual(second[1], "w")

    def test_one_natural_batch_produces_one_next_hop(self):
        graph = self._base_graph(people=5, capacity=20)
        graph.add_node("w", type="area", people=0, area=100,
                       people_dict={"L2": 0}, source_group_dict={})
        graph.add_edge("u", "w", length=1, capacity=20)
        with patch.object(spr, "mesoscopic_full_graph_path", return_value=["u", "v"]):
            net._get_mesoscopic_step_moves(
                graph, ["u"], {}, spr.MESOSCOPIC_PHYSICAL_TIME_METHOD
            )
        allocations = graph.graph["_mesoscopic_accepted_allocations"]
        cohort_edges = [edge for edge, rows in allocations.items() if any(r["cohort_id"] for r in rows)]
        self.assertEqual(cohort_edges, [("u", "v")])

    def test_rejected_batch_remains_uncommitted(self):
        graph = self._base_graph(people=10, capacity=0)
        cohort = net._ensure_node_mesoscopic_cohorts(graph, "u")[0]
        request = {
            "u": "u", "v": "v", "requested": 10,
            "cohort_id": cohort["cohort_id"], "source_group": cohort["source_group"],
            "arrival_time": 0, "committed_segment": ["u", "v"],
            "segment_index": 0, "next_decision_node": "v",
        }
        moves = net._integerize_mesoscopic_requests(graph, [request])
        net._schedule_moves_as_transit(graph, moves)
        self.assertEqual(graph.nodes["u"]["people"], 10)
        self.assertFalse(cohort["committed"])


class PredictiveAASmallNetworkTests(unittest.TestCase):
    def _parallel_graph(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_resource_queues"] = {}
        graph.graph["_aa_round_prediction_events"] = []
        graph.add_node("S", type="area")
        graph.add_node("A", type="gate", capacity=1)
        graph.add_node("B", type="gate", capacity=10)
        graph.add_node("E", type="exit")
        graph.add_edge("S", "A", length=1, capacity=1)
        graph.add_edge("A", "E", length=1, capacity=10)
        graph.add_edge("S", "B", length=3, capacity=10)
        graph.add_edge("B", "E", length=1, capacity=10)
        return graph

    def _capacity(self, graph, resource_id):
        return 1.0 if resource_id == spr.edge_resource_id(graph, "S", "A") else 10.0

    def test_first_assigned_batch_updates_second_batch_prediction(self):
        graph = self._parallel_graph()
        with patch.object(spr, "physical_edge_travel_time", side_effect=lambda G, u, v: G[u][v]["length"]), \
             patch.object(spr, "resource_capacity_per_second", side_effect=lambda G, r: self._capacity(G, r)), \
             patch.object(spr, "predicted_spatial_wait", return_value=0.0):
            first, _, first_details = spr.time_dependent_astar(graph, "S")
            spr.register_round_prediction_events(graph, first_details, 10, "g1", "b1")
            second, _, _ = spr.time_dependent_astar(graph, "S")
        self.assertEqual(first[1], "A")
        self.assertEqual(second[1], "B")

    def test_current_queue_and_predictive_search_differ_on_future_arrival(self):
        graph = self._parallel_graph()
        resource_a = spr.edge_resource_id(graph, "S", "A")
        graph.graph["_aa_round_prediction_events"] = [{
            "resource_id": resource_a, "predicted_arrival_time": 0.0,
            "amount": 10, "source_group": "g", "batch_id": "future",
        }]
        with patch.object(spr, "physical_edge_travel_time", side_effect=lambda G, u, v: G[u][v]["length"]), \
             patch.object(spr, "resource_capacity_per_second", side_effect=lambda G, r: self._capacity(G, r)), \
             patch.object(spr, "predicted_spatial_wait", return_value=0.0):
            current = spr.mesoscopic_full_graph_path(
                graph, "S", spr.MESOSCOPIC_CURRENT_QUEUE_METHOD, {}
            )
            predictive, _, _ = spr.time_dependent_astar(graph, "S")
        self.assertEqual(current[1], "A")
        self.assertEqual(predictive[1], "B")

    def test_predicted_spatial_blocking_changes_route(self):
        graph = self._parallel_graph()
        with patch.object(spr, "physical_edge_travel_time", side_effect=lambda G, u, v: G[u][v]["length"]), \
             patch.object(spr, "resource_capacity_per_second", return_value=10.0), \
             patch.object(spr, "predicted_spatial_wait", side_effect=lambda G, n, eta, amount: 20.0 if n == "A" else 0.0):
            path, _, details = spr.time_dependent_astar(graph, "S")
        self.assertEqual(path[1], "B")
        self.assertTrue(all(detail["spatial_wait"] == 0 for detail in details))

    def test_formal_predictive_search_has_no_dynamic_path_cache_or_fixed_k(self):
        source = inspect.getsource(spr.time_dependent_astar)
        self.assertNotIn("K_CANDIDATE_PATHS", source)
        self.assertNotIn("_mesoscopic_step_path_cache", source)

    def test_round_queue_reassignment_is_conservative(self):
        graph = self._parallel_graph()
        resource = spr.edge_resource_id(graph, "S", "A")
        graph.graph["_resource_queues"] = {resource: 10}
        graph.graph["_aa_round_queue_adjustment"] = {resource: -4}
        self.assertEqual(spr.current_resource_queue(graph, resource), 6)
        graph.graph["_aa_round_queue_adjustment"][resource] += 4
        self.assertEqual(spr.current_resource_queue(graph, resource), 10)

    def test_formal_aa_does_not_replan_on_committed_intermediate_node(self):
        source = inspect.getsource(net._get_predictive_aa_step_moves)
        self.assertIn("may_replan = not old_path", source)
        self.assertNotIn(
            "may_replan = not old_path or _is_explicit_aa_selection_stage",
            source,
        )


class MultilabelTimeDependentAStarTests(unittest.TestCase):
    def _base_graph(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_resource_queues"] = {}
        for node in ("S", "A", "B", "N", "E"):
            graph.add_node(node, type="exit" if node == "E" else "area", area=100)
        return graph

    def _add_edge(self, graph, u, v, length, *, density=0.0, capacity=1.0):
        graph.add_edge(
            u, v, length=length, capacity=capacity,
            runtime_density=density,
        )

    def _patch_physics(self, queue_fn=None):
        if queue_fn is None:
            queue_fn = lambda G, resource, eta: 0.0
        return patch.multiple(
            spr,
            physical_edge_travel_time=lambda G, u, v: float(G[u][v]["length"]),
            resource_capacity_per_second=lambda G, resource: 1.0,
            predicted_resource_queue_at_time=queue_fn,
            predicted_spatial_wait=lambda G, n, eta, amount=1: 0.0,
            predicted_spatial_density=lambda G, n, eta, amount=0: 0.0,
        )

    def test_single_label_counterexample_is_fixed_by_multilabel(self):
        graph = self._base_graph()
        graph.graph["aa_safety_weight"] = 10.0
        self._add_edge(graph, "S", "A", 1.0, density=3.5)
        self._add_edge(graph, "A", "N", 1.0)
        self._add_edge(graph, "S", "B", 3.0)
        self._add_edge(graph, "B", "N", 1.0)
        self._add_edge(graph, "N", "E", 1.0)

        def queue_at(G, resource, eta):
            return 100.0 if resource == spr.edge_resource_id(G, "N", "E") and eta >= 3.5 else 0.0

        with self._patch_physics(queue_at):
            single_path, single_cost, _ = spr._time_dependent_astar_single_label(
                graph, "S"
            )
            multilabel_path, multilabel_cost, _ = spr._time_dependent_astar_multilabel(
                graph, "S"
            )
        self.assertNotEqual(single_path, multilabel_path)
        self.assertEqual(multilabel_path, ["S", "A", "N", "E"])
        self.assertLess(multilabel_cost, single_cost)

    def test_public_search_defaults_to_multilabel(self):
        graph = self._base_graph()
        graph.graph["aa_safety_weight"] = 10.0
        self._add_edge(graph, "S", "A", 1.0, density=3.5)
        self._add_edge(graph, "A", "N", 1.0)
        self._add_edge(graph, "S", "B", 3.0)
        self._add_edge(graph, "B", "N", 1.0)
        self._add_edge(graph, "N", "E", 1.0)

        def queue_at(G, resource, eta):
            is_terminal = resource == spr.edge_resource_id(G, "N", "E")
            return 100.0 if is_terminal and eta >= 3.5 else 0.0

        with self._patch_physics(queue_at):
            path, cost, _ = spr.time_dependent_astar(graph, "S")
            expected_path, expected_cost, _ = (
                spr._time_dependent_astar_multilabel(graph, "S")
            )
        self.assertEqual(path, expected_path)
        self.assertAlmostEqual(cost, expected_cost)

    def test_public_search_can_explicitly_use_single_label_ablation(self):
        graph = self._base_graph()
        graph.graph["aa_search_mode"] = "single_label"
        self._add_edge(graph, "S", "A", 1.0)
        self._add_edge(graph, "A", "E", 1.0)
        with self._patch_physics():
            path, cost, _ = spr.time_dependent_astar(graph, "S")
        self.assertEqual(path, ["S", "A", "E"])
        self.assertAlmostEqual(cost, 2.0)

    def test_public_search_rejects_unknown_mode(self):
        graph = self._base_graph()
        graph.graph["aa_search_mode"] = "typo"
        with self.assertRaisesRegex(ValueError, "aa_search_mode"):
            spr.time_dependent_astar(graph, "S")

    def test_multilabel_matches_all_simple_path_enumeration(self):
        graph = self._base_graph()
        graph.graph["aa_safety_weight"] = 10.0
        self._add_edge(graph, "S", "A", 1.0, density=3.5)
        self._add_edge(graph, "A", "N", 1.0)
        self._add_edge(graph, "S", "B", 3.0)
        self._add_edge(graph, "B", "N", 1.0)
        self._add_edge(graph, "N", "E", 1.0)

        def queue_at(G, resource, eta):
            return 100.0 if resource == spr.edge_resource_id(G, "N", "E") and eta >= 3.5 else 0.0

        with self._patch_physics(queue_at):
            best_path, best_cost, _ = spr._time_dependent_astar_multilabel(
                graph, "S"
            )
            enumerated = []
            for path in nx.all_simple_paths(graph, "S", "E"):
                cost, _ = spr.evaluate_time_dependent_path(graph, path)
                enumerated.append((cost, path))
        expected_cost, expected_path = min(enumerated, key=lambda item: item[0])
        self.assertEqual(best_path, expected_path)
        self.assertAlmostEqual(best_cost, expected_cost)

    def test_different_arrival_times_are_retained(self):
        graph = self._base_graph()
        self._add_edge(graph, "S", "A", 5.0)
        self._add_edge(graph, "A", "N", 5.0)
        self._add_edge(graph, "S", "B", 7.0)
        self._add_edge(graph, "B", "N", 8.0)
        self._add_edge(graph, "N", "E", 100.0)
        with self._patch_physics():
            spr._time_dependent_astar_multilabel(graph, "S")
        active_n = [
            label for label in graph.graph["_aa_last_multilabel_labels_by_id"].values()
            if label["node"] == "N" and label.get("active", True)
        ]
        self.assertEqual(sorted(label["elapsed"] for label in active_n), [10.0, 15.0])

    def test_same_arrival_time_allows_safe_pruning(self):
        graph = self._base_graph()
        graph.graph["aa_safety_weight"] = 10.0
        self._add_edge(graph, "S", "A", 1.0)
        self._add_edge(graph, "A", "N", 1.0)
        self._add_edge(graph, "S", "B", 1.0, density=3.5)
        self._add_edge(graph, "B", "N", 1.0)
        with self._patch_physics():
            spr._time_dependent_astar_multilabel(graph, "S", target_exits=())
        active_n = [
            label for label in graph.graph["_aa_last_multilabel_labels_by_id"].values()
            if label["node"] == "N" and label.get("active", True)
        ]
        self.assertEqual(len(active_n), 1)
        self.assertGreater(
            graph.graph["_aa_diagnostics"]["multilabel_pruned_same_arrival_count"],
            0,
        )

    def test_same_index_bucket_does_not_merge_distinct_times(self):
        graph = self._base_graph()
        graph.graph["aa_multilabel_index_bucket_width"] = 1.0
        self._add_edge(graph, "S", "A", 1.0)
        self._add_edge(graph, "A", "N", 1.01)
        self._add_edge(graph, "S", "B", 1.0)
        self._add_edge(graph, "B", "N", 1.02)
        with self._patch_physics():
            spr._time_dependent_astar_multilabel(graph, "S", target_exits=())
        active_n = [
            label for label in graph.graph["_aa_last_multilabel_labels_by_id"].values()
            if label["node"] == "N" and label.get("active", True)
        ]
        self.assertEqual(sorted(round(label["elapsed"], 2) for label in active_n), [2.01, 2.02])

    def test_multilabel_paths_do_not_use_cycles(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        for node in ("S", "A", "B", "E"):
            graph.add_node(node, type="exit" if node == "E" else "area", area=100)
        self._add_edge(graph, "S", "A", 1.0)
        self._add_edge(graph, "A", "B", 1.0)
        self._add_edge(graph, "B", "A", 1.0)
        self._add_edge(graph, "A", "E", 1.0)
        with self._patch_physics():
            path, _, _ = spr._time_dependent_astar_multilabel(graph, "S")
        self.assertEqual(path, ["S", "A", "E"])
        self.assertEqual(len(path), len(set(path)))


class InitialAABatchSplitTests(unittest.TestCase):
    def test_initial_batch_split_preserves_people_and_source_group(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["aa_initial_routing_batch_size"] = 20
        graph.add_node(
            "u", people=103, people_dict={"L2": 103},
            source_group_dict={"L2_train1_Z1": 103},
        )
        batches = net._ensure_node_aa_batches(graph, "u")
        self.assertEqual([batch["amount"] for batch in batches], [20, 20, 20, 20, 20, 3])
        self.assertEqual(sum(batch["amount"] for batch in batches), 103)
        self.assertEqual({batch["source_group"] for batch in batches}, {"L2_train1_Z1"})
        self.assertEqual(len({batch["batch_id"] for batch in batches}), 6)

    def test_initial_batch_size_zero_keeps_legacy_single_batch(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["aa_initial_routing_batch_size"] = 0
        graph.add_node(
            "u", people=103, people_dict={"L2": 103},
            source_group_dict={"L2_train1_Z1": 103},
        )
        batches = net._ensure_node_aa_batches(graph, "u")
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["amount"], 103)


class L2UpstreamResidualReplanTests(unittest.TestCase):
    NODE = "Platform_L2_Z1_Wait"
    STAIR_A = "Stair_L2_A"
    STAIR_B = "Stair_L2_B"

    def _graph(self):
        graph = nx.DiGraph()
        graph.graph.update({
            "_sim_time": 0.0,
            "_transit_queue": [],
            "_resource_queues": {},
            "_resource_flow_credit": {},
            "density_dependent_flow": False,
            "spillback_enabled": False,
            "aa_reroute_gain_min": 0.20,
        })
        graph.add_node(
            self.NODE,
            type="platform_waiting_zone",
            line_id="L2",
            people=300,
            area=100,
            source_group_dict={"L2_train1_Z1": 300},
            people_dict={"L2": 300},
        )
        for stair, exit_node in (
            (self.STAIR_A, "Exit_L2_A"),
            (self.STAIR_B, "Exit_L2_B"),
        ):
            graph.add_node(
                stair,
                type="stair",
                line_id="L2",
                people=0,
                area=100,
                capacity=10,
            )
            graph.add_node(exit_node, type="exit", people=0, area=100)
            graph.add_edge(stair, exit_node, length=1.0, capacity=10)
        graph.add_edge(
            self.NODE,
            self.STAIR_A,
            length=1.0,
            capacity=10,
            edge_type="platform_zone_to_vertical",
        )
        graph.add_edge(
            self.NODE,
            self.STAIR_B,
            length=1.0,
            capacity=10,
            edge_type="platform_zone_to_vertical",
        )
        net._annotate_aa_evacuation_stages_and_replan_scope(graph)
        return graph

    def test_platform_release_node_is_enabled_only_for_real_parallel_options(self):
        graph = self._graph()
        node_data = graph.nodes[self.NODE]
        self.assertEqual(node_data["evac_stage"], "platform_train")
        self.assertTrue(node_data["aa_active_replan_allowed"])
        self.assertTrue(node_data["aa_l2_upstream_release_node"])
        self.assertEqual(
            set(node_data["aa_replan_successors"]),
            {self.STAIR_A, self.STAIR_B},
        )
        self.assertEqual(
            graph.graph["aa_replan_scope_diagnostics"][
                "l2_upstream_release_replan_node_count"
            ],
            1,
        )

    def test_formal_l2_scope_contains_waiting_zones_not_train_cars_without_branching(self):
        graph = net.build_graph()
        active_l2_nodes = {
            node
            for node, data in graph.nodes(data=True)
            if data.get("aa_l2_upstream_release_node")
        }
        self.assertEqual(
            active_l2_nodes,
            {
                "Platform_L2_Z1_Wait",
                "Platform_L2_Z2_Wait",
                "Platform_L2_Z3_Wait",
                "Platform_L2_Z4_Wait",
            },
        )
        self.assertTrue(all(
            not data.get("aa_l2_upstream_release_node", False)
            for node, data in graph.nodes(data=True)
            if data.get("type") == "train_car" and data.get("line_id") == "L2"
        ))

    def test_residual_batch_replans_after_current_stair_congestion(self):
        graph = self._graph()
        resource_a = net.edge_resource_id(graph, self.NODE, self.STAIR_A)
        graph.graph["_resource_queues"] = {resource_a: 10}
        batch = net._ensure_node_aa_batches(graph, self.NODE)[0]
        batch.update({
            "amount": 290,
            "current_node": self.NODE,
            "current_path": [self.NODE, self.STAIR_A, "Exit_L2_A"],
            "waiting_resource": resource_a,
            "queue_enter_time": 0.0,
            "plan_history_node": self.NODE,
            "selected_first_hops": [self.STAIR_A],
        })

        def evaluate_path(_graph, path, _now, amount=1):
            cost = 100.0 if path[1] == self.STAIR_A else 70.0
            return cost, [{
                "resource_id": net.edge_resource_id(
                    _graph, path[0], path[1]
                ),
                "predicted_queue": 10.0 if path[1] == self.STAIR_A else 0.0,
                "predicted_wait": 2.0 if path[1] == self.STAIR_A else 0.0,
                "destination_predicted_density": 0.0,
            }]

        def lower_bound(_graph, _node, _now, _amount, allowed_successors=None, **_kwargs):
            return 70.0 if self.STAIR_B in set(allowed_successors or ()) else 100.0

        def astar(_graph, node, _now, amount=1, **_kwargs):
            return (
                [node, self.STAIR_B, "Exit_L2_B"],
                70.0,
                [{
                    "resource_id": net.edge_resource_id(
                        _graph, node, self.STAIR_B
                    ),
                    "predicted_queue": 0.0,
                    "predicted_wait": 0.0,
                    "destination_predicted_density": 0.0,
                }],
            )

        captured_requests = []

        def integerize(_graph, requests):
            captured_requests.extend(requests)
            return [
                (item["u"], item["v"], int(item["requested"]))
                for item in requests
            ]

        with patch.multiple(
            spr,
            evaluate_time_dependent_path=evaluate_path,
            aa_one_step_objective_lower_bound=lower_bound,
            time_dependent_astar=astar,
        ), patch.object(net, "_integerize_aa_batch_requests", integerize):
            moves = net._get_predictive_aa_step_moves(
                graph, [self.NODE], predictive=True
            )

        self.assertEqual(moves, [(self.NODE, self.STAIR_B, 290)])
        self.assertEqual(captured_requests[0]["requested"], 290)
        self.assertTrue(captured_requests[0]["l2_platform_replan"])
        diagnostics = graph.graph["_aa_diagnostics"]
        self.assertEqual(diagnostics["l2_platform_replan_trigger_count"], 1)
        self.assertEqual(diagnostics["l2_platform_replan_evaluation_count"], 1)

    def _residual_batch(self, graph):
        resource_a = net.edge_resource_id(graph, self.NODE, self.STAIR_A)
        batch = net._ensure_node_aa_batches(G=graph, node=self.NODE)[0]
        batch.update({
            "amount": 290,
            "current_node": self.NODE,
            "current_path": [self.NODE, self.STAIR_A, "Exit_L2_A"],
            "waiting_resource": resource_a,
            "queue_enter_time": 0.0,
            "plan_history_node": self.NODE,
            "selected_first_hops": [self.STAIR_A],
        })
        return resource_a

    def test_l2_residual_keeps_current_path_without_congestion_trigger(self):
        graph = self._graph()
        resource_a = self._residual_batch(graph)

        def evaluate_path(_graph, path, _now, amount=1):
            return 100.0, [{
                "resource_id": resource_a,
                "predicted_queue": 0.0,
                "predicted_wait": 0.0,
                "destination_predicted_density": 0.0,
            }]

        captured_requests = []

        def integerize(_graph, requests):
            captured_requests.extend(requests)
            return [
                (item["u"], item["v"], int(item["requested"]))
                for item in requests
            ]

        with patch.object(spr, "evaluate_time_dependent_path", evaluate_path), \
             patch.object(net, "_integerize_aa_batch_requests", integerize):
            moves = net._get_predictive_aa_step_moves(
                graph, [self.NODE], predictive=True
            )

        self.assertEqual(moves, [(self.NODE, self.STAIR_A, 290)])
        self.assertFalse(captured_requests[0]["l2_platform_replan"])
        self.assertEqual(
            graph.graph["_aa_diagnostics"][
                "l2_platform_replan_not_triggered_count"
            ],
            1,
        )

    def test_l2_residual_stays_when_triggered_gain_is_below_twenty_percent(self):
        graph = self._graph()
        resource_a = self._residual_batch(graph)
        graph.graph["_resource_queues"] = {resource_a: 10}

        def evaluate_path(_graph, path, _now, amount=1):
            return 100.0, [{
                "resource_id": resource_a,
                "predicted_queue": 10.0,
                "predicted_wait": 2.0,
                "destination_predicted_density": 0.0,
            }]

        def lower_bound(_graph, _node, _now, _amount, **_kwargs):
            return 95.0

        captured_requests = []

        def integerize(_graph, requests):
            captured_requests.extend(requests)
            return [
                (item["u"], item["v"], int(item["requested"]))
                for item in requests
            ]

        with patch.object(spr, "evaluate_time_dependent_path", evaluate_path), \
             patch.object(spr, "aa_one_step_objective_lower_bound", lower_bound), \
             patch.object(net, "_integerize_aa_batch_requests", integerize):
            moves = net._get_predictive_aa_step_moves(
                graph, [self.NODE], predictive=True
            )

        self.assertEqual(moves, [(self.NODE, self.STAIR_A, 290)])
        self.assertFalse(captured_requests[0]["l2_platform_replan"])
        diagnostics = graph.graph["_aa_diagnostics"]
        self.assertEqual(diagnostics["l2_platform_replan_trigger_count"], 1)
        self.assertEqual(diagnostics["l2_platform_replan_evaluation_count"], 1)
        self.assertGreaterEqual(
            diagnostics["l2_platform_replan_gain_below_threshold_count"],
            1,
        )

    def test_l2_replan_people_diagnostic_uses_executor_acceptance(self):
        graph = self._graph()
        request = {
            "u": self.NODE,
            "v": self.STAIR_B,
            "requested": 290,
            "batch_id": "l2-residual",
            "source_group": "L2_train1_Z1",
            "arrival_time": 0.0,
            "queue_enter_time": 0.0,
            "l2_platform_replan": True,
        }
        with patch.object(
            net,
            "_integerize_moves",
            return_value=[(self.NODE, self.STAIR_B, 8)],
        ):
            moves = net._integerize_aa_batch_requests(graph, [request])

        self.assertEqual(moves, [(self.NODE, self.STAIR_B, 8)])
        diagnostics = graph.graph["_aa_diagnostics"]
        self.assertEqual(diagnostics["l2_platform_replan_accept_count"], 1)
        self.assertEqual(diagnostics["l2_platform_rerouted_people"], 8)


class FormalMetricOutputTests(unittest.TestCase):
    def _result(self, method):
        return {
            "method": method,
            "target_people": 10.0,
            "evacuated_people": 10.0,
            "remaining_people": 0.0,
            "completed": True,
            "termination_reason": "completed",
            "evacuation_time": 12.0,
            "mean_station_throughput": 10.0 / 12.0,
            "queueing_time": 20.0,
            "resource_queueing_time": 20.0,
            "stationary_time": 23.0,
            "_diagnostic_spatial_blocked_person_seconds": 3.0,
            "_diagnostic_high_density_exposure_person_seconds": 4.0,
            "moving_average_speed": 1.1,
            "edge_traversal_avg_speed": 1.0,
            "effective_evacuation_speed": 0.5,
            "total_movement_distance": 100.0,
            "moving_person_seconds": 90.0,
            "total_system_person_seconds": 200.0,
            "mean_moving_time": 9.0,
            "mean_queueing_time": 2.0,
            "mean_stationary_time": 2.3,
            "mean_total_evacuation_time": 20.0,
            "exit_load_jain_index": 0.8,
            "key_facility_load_jain_index": 0.7,
            "wall_clock_s": 0.1,
            "exit_usage": {"Exit": 10.0},
            "clearance_times": {"L2": 12.0},
            "line_t95": {"L2": 10.0},
            "eval": {"t95": 10.0, "t100": 12.0},
            "_raw_metrics": {
                "key_facility_throughput": {"Gate": 10.0},
                "aa_diagnostics": {},
                "high_density_diagnostics": [],
                "high_density_exposure_person_seconds": 4.0,
            },
        }

    def test_formal_summary_has_one_canonical_field_per_metric(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self._result("ImprovedAStar")
            before = copy.deepcopy(result)
            comparison._write_single_algorithm_outputs(
                result, temp_dir, 4, 10, diagnostic_metrics=False
            )
            with (Path(temp_dir) / "summary_metrics.csv").open(
                "r", newline="", encoding="utf-8-sig"
            ) as handle:
                reader = csv.reader(handle)
                header = next(reader)
                row = next(reader)
            self.assertEqual(len(header), len(row))
            self.assertEqual(len(header), len(set(header)))
            self.assertIn("cumulative_stationary_person_seconds", header)
            self.assertIn("mean_stationary_time_seconds_per_person", header)
            self.assertIn("moving_average_speed_m_per_s", header)
            self.assertIn("moving_person_seconds", header)
            self.assertIn("total_system_person_seconds", header)
            self.assertEqual(row[header.index("moving_person_seconds")], "90.0")
            self.assertEqual(row[header.index("total_system_person_seconds")], "200.0")
            self.assertNotIn("cumulative_queueing_person_seconds", header)
            self.assertNotIn("mean_queueing_time_seconds_per_person", header)
            self.assertNotIn("queueing_time_person_seconds", header)
            self.assertNotIn("resource_queueing_time_person_seconds", header)
            self.assertNotIn("high_density_exposure_person_seconds", header)
            self.assertNotIn("spatial_blocked_exposure_person_seconds", header)
            self.assertFalse((Path(temp_dir) / "high_density_diagnostics.csv").exists())
            self.assertEqual(result, before)

    def test_saved_comparison_report_excludes_removed_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dirs = []
            for method in ("ImprovedAStar", "AdaptiveQueueAwareAStar"):
                run_dir = root / method
                comparison._write_single_algorithm_outputs(
                    self._result(method), run_dir, 4, 10, diagnostic_metrics=False
                )
                dirs.append(run_dir)
            comparison.compare_saved_results(*dirs)
            report = (root / "mode4_formal_report.md").read_text(encoding="utf-8")
            self.assertIn("| moving_person_seconds | 90.000000 | 90.000000 |", report)
            self.assertIn("| total_system_person_seconds | 200.000000 | 200.000000 |", report)
            forbidden = (
                "high_density_exposure_person_seconds",
                "spatial_blocked_exposure_person_seconds",
                "HighDensityExposure",
                "SpatialBlockedExposure",
                "J_severe",
            )
            for name in forbidden:
                self.assertNotIn(name, report)


class PathfinderRouteExportTests(unittest.TestCase):
    def _route_graph(self):
        graph = nx.DiGraph()
        graph.add_node("S", type="platform", people=0)
        graph.add_node("Stair_A", type="stair", people=0)
        graph.add_node("Stair_B", type="stair", people=0)
        graph.add_node("Gate_1", type="gate", people=0)
        graph.add_node("Gate_2", type="gate", people=0)
        graph.add_node("Exit_1", type="exit", people=0)
        for u, v in (
            ("S", "Stair_A"), ("S", "Stair_B"),
            ("Stair_A", "Gate_1"), ("Stair_A", "Gate_2"),
            ("Stair_B", "Gate_1"), ("Gate_1", "Exit_1"),
            ("Gate_2", "Exit_1"),
        ):
            graph.add_edge(u, v, length=1, capacity=100)
        return graph

    def _export_result(self, routes, total):
        graph = self._route_graph()
        source_group = "L2_platform_waiting::S"
        exit_total = sum(route["route_people"] for route in routes)
        node_by_group = {}
        for route in routes:
            for node in route["raw_full_path"][1:]:
                node_by_group.setdefault(node, {})
                node_by_group[node][source_group] = (
                    node_by_group[node].get(source_group, 0)
                    + route["route_people"]
                )
        return {
            "method": "ImprovedAStar",
            "_simulation_graph": graph,
            "_raw_metrics": {
                "source_group_totals": {source_group: total},
                "completed_executed_routes": [
                    {"source_group": source_group, **route} for route in routes
                ],
                "exit_usage_by_source_group": {
                    "Exit_1": {source_group: exit_total}
                },
                "node_throughput_by_sg": node_by_group,
                "key_facility_throughput": {
                    node: sum(groups.values())
                    for node, groups in node_by_group.items()
                    if node.startswith(("Stair_", "Gate_"))
                },
                "route_tracking_errors": [],
            },
        }

    def test_largest_remainder_examples_are_exact_and_stable(self):
        rows = [
            {"route_id": "r1", "route_people": 80},
            {"route_id": "r2", "route_people": 210},
            {"route_id": "r3", "route_people": 185},
        ]
        first = comparison._largest_remainder_percentages(rows, 475)
        second = comparison._largest_remainder_percentages(rows, 475)
        self.assertEqual(first, second)
        self.assertEqual(first, {"r1": 16.8, "r2": 44.2, "r3": 39.0})
        self.assertAlmostEqual(sum(first.values()), 100.0)

    def test_largest_remainder_ties_single_and_tiny_route(self):
        tied = [
            {"route_id": "a", "route_people": 1},
            {"route_id": "b", "route_people": 1},
            {"route_id": "c", "route_people": 1},
        ]
        self.assertEqual(
            comparison._largest_remainder_percentages(tied, 3),
            {"a": 33.4, "b": 33.3, "c": 33.3},
        )
        self.assertEqual(
            comparison._largest_remainder_percentages(
                [{"route_id": "only", "route_people": 7}], 7
            ),
            {"only": 100.0},
        )
        tiny = comparison._largest_remainder_percentages([
            {"route_id": "large", "route_people": 999},
            {"route_id": "tiny", "route_people": 1},
        ], 1000)
        self.assertIn("tiny", tiny)
        self.assertEqual(tiny["tiny"], 0.1)

    def test_percentage_correction_handles_99_9_and_100_1_inputs(self):
        under = comparison._largest_remainder_percentages([
            {"route_id": "a", "route_people": 500},
            {"route_id": "b", "route_people": 499},
        ], 1000)
        over = comparison._largest_remainder_percentages([
            {"route_id": "a", "route_people": 501},
            {"route_id": "b", "route_people": 500},
        ], 1000)
        self.assertAlmostEqual(sum(under.values()), 100.0)
        self.assertAlmostEqual(sum(over.values()), 100.0)

    def test_same_exit_different_stairs_remain_distinct(self):
        result = self._export_result([
            {
                "raw_full_path": ["S", "Stair_A", "Gate_1", "Exit_1"],
                "route_people": 4,
            },
            {
                "raw_full_path": ["S", "Stair_B", "Gate_1", "Exit_1"],
                "route_people": 6,
            },
        ], 10)
        rows, _, validation, summary = comparison._build_pathfinder_route_exports(
            result, 1, 10
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["first_vertical_facility"] for row in rows}, {
            "Stair_A", "Stair_B",
        })
        self.assertTrue(validation[0]["validation_passed"])
        self.assertEqual(summary["people_conservation_error"], 0)

    def test_same_stair_different_gates_remain_distinct(self):
        result = self._export_result([
            {
                "raw_full_path": ["S", "Stair_A", "Gate_1", "Exit_1"],
                "route_people": 5,
            },
            {
                "raw_full_path": ["S", "Stair_A", "Gate_2", "Exit_1"],
                "route_people": 5,
            },
        ], 10)
        rows, groups, validation, _ = comparison._build_pathfinder_route_exports(
            result, 1, 10
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["gate_facility"] for row in rows}, {
            "Gate_1", "Gate_2",
        })
        self.assertEqual(len({row["group_name"] for row in groups}), 2)
        self.assertTrue(validation[0]["exit_sum_consistent"])
        self.assertTrue(validation[0]["facility_sum_consistent"])

    def test_raw_facility_audit_uses_executed_paths_not_merged_canonical_path(self):
        graph = self._route_graph()
        graph.add_node("Hall_X", type="area", people=0)
        graph.remove_edge("Stair_A", "Gate_1")
        graph.add_edge("Stair_A", "Hall_X", length=1, capacity=100)
        graph.add_edge("Hall_X", "Gate_1", length=1, capacity=100)
        source_group = "L2_platform_waiting::S"
        result = {
            "method": "ImprovedAStar",
            "_simulation_graph": graph,
            "_raw_metrics": {
                "source_group_totals": {source_group: 10},
                "completed_executed_routes": [{
                    "source_group": source_group,
                    "raw_full_path": [
                        "S", "Stair_A", "Hall_X", "Gate_1", "Exit_1"
                    ],
                    "route_people": 10,
                }],
                "exit_usage_by_source_group": {
                    "Exit_1": {source_group: 10}
                },
                "node_throughput_by_sg": {
                    "Stair_A": {source_group: 10},
                    "Hall_X": {source_group: 10},
                    "Gate_1": {source_group: 10},
                    "Exit_1": {source_group: 10},
                },
                "key_facility_throughput": {
                    "Stair_A": 10,
                    "Hall_X": 10,
                    "Gate_1": 10,
                },
                "route_tracking_errors": [],
            },
        }
        rows, _, validation, summary = comparison._build_pathfinder_route_exports(
            result, 1, 10
        )
        self.assertEqual(rows[0]["canonical_path"], "Stair_A -> Gate_1 -> Exit_1")
        self.assertTrue(validation[0]["facility_throughput_consistency"])
        self.assertTrue(validation[0]["validation_passed"])
        self.assertTrue(summary["_merged_validation_rows"][0]["validation_passed"])

    def test_three_pathfinder_csv_files_have_integer_people_and_exact_percent(self):
        result = self._export_result([
            {
                "raw_full_path": ["S", "Stair_A", "Gate_1", "Exit_1"],
                "route_people": 4,
            },
            {
                "raw_full_path": ["S", "Stair_B", "Gate_1", "Exit_1"],
                "route_people": 6,
            },
        ], 10)
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = comparison._write_pathfinder_route_outputs(
                result, Path(temp_dir), 1, 10
            )
            allocation_path = Path(temp_dir) / "pathfinder_route_allocation.csv"
            raw_path = Path(temp_dir) / "pathfinder_route_allocation_raw.csv"
            merged_path = Path(temp_dir) / "pathfinder_route_allocation_merged.csv"
            group_path = Path(temp_dir) / "pathfinder_group_setup.csv"
            validation_path = Path(temp_dir) / "pathfinder_route_validation.csv"
            raw_validation_path = Path(temp_dir) / "raw_route_validation.csv"
            merged_validation_path = Path(temp_dir) / "merged_route_validation.csv"
            self.assertTrue(all(path.exists() for path in (
                allocation_path, raw_path, merged_path, group_path,
                validation_path, raw_validation_path, merged_validation_path,
            )))
            with allocation_path.open(
                "r", newline="", encoding="utf-8-sig"
            ) as handle:
                allocation = list(csv.DictReader(handle))
            self.assertEqual([int(row["route_people"]) for row in allocation], [4, 6])
            self.assertEqual(
                sum(float(row["route_percentage"]) for row in allocation),
                100.0,
            )
            self.assertTrue(all(
                len(row["route_percentage"].split(".")[-1]) == 1
                for row in allocation
            ))
            self.assertEqual(summary["people_conservation_error"], 0)

    def test_equivalent_car_paths_are_merged_before_percentages(self):
        graph = self._route_graph()
        graph.add_node("Car1", type="platform", people=0)
        graph.add_node("Car2", type="platform", people=0)
        graph.add_edge("Car1", "Stair_A", length=1, capacity=100)
        graph.add_edge("Car2", "Stair_A", length=1, capacity=100)
        source_group = "L2_train1_Z1"
        result = {
            "method": "ImprovedAStar",
            "_simulation_graph": graph,
            "_raw_metrics": {
                "source_group_totals": {source_group: 100},
                "completed_executed_routes": [
                    {
                        "source_group": source_group,
                        "raw_full_path": ["Car1", "Stair_A", "Gate_1", "Exit_1"],
                        "route_people": 50,
                    },
                    {
                        "source_group": source_group,
                        "raw_full_path": ["Car2", "Stair_A", "Gate_1", "Exit_1"],
                        "route_people": 50,
                    },
                ],
                "exit_usage_by_source_group": {
                    "Exit_1": {source_group: 100}
                },
                "node_throughput_by_sg": {
                    "Stair_A": {source_group: 100},
                    "Gate_1": {source_group: 100},
                    "Exit_1": {source_group: 100},
                },
                "key_facility_throughput": {
                    "Stair_A": 100,
                    "Gate_1": 100,
                },
                "route_tracking_errors": [],
            },
        }
        rows, _, validation, summary = comparison._build_pathfinder_route_exports(
            result, 4, 100
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["route_people"], 100)
        self.assertEqual(rows[0]["route_percentage"], 100.0)
        self.assertEqual(rows[0]["canonical_path"], "Stair_A -> Gate_1 -> Exit_1")
        self.assertNotRegex(rows[0]["canonical_path"], r"Car|C1|C2|C3|C4|C5|C6")
        self.assertTrue(validation[0]["validation_passed"])
        self.assertEqual(summary["people_conservation_error"], 0)

    def test_percentages_are_people_weighted_after_canonical_merge(self):
        result = self._export_result([
            {
                "raw_full_path": ["S", "Stair_A", "Gate_1", "Exit_1"],
                "route_people": 80,
            },
            {
                "raw_full_path": ["S", "Stair_B", "Gate_1", "Exit_1"],
                "route_people": 20,
            },
        ], 100)
        rows, _, _, _ = comparison._build_pathfinder_route_exports(result, 1, 100)
        percentages = {
            row["first_vertical_facility"]: row["route_percentage"]
            for row in rows
        }
        self.assertEqual(percentages, {"Stair_A": 80.0, "Stair_B": 20.0})

    def test_discontinuous_and_cyclic_routes_are_not_silently_repaired(self):
        result = self._export_result([
            {
                "raw_full_path": [
                    "S", "Stair_A", "Gate_1", "Stair_A", "Exit_1"
                ],
                "route_people": 10,
            },
        ], 10)
        rows, _, validation, _ = comparison._build_pathfinder_route_exports(
            result, 1, 10
        )
        self.assertEqual(rows[0]["raw_full_path"],
                         "S -> Stair_A -> Gate_1 -> Stair_A -> Exit_1")
        self.assertTrue(rows[0]["contains_cycle"])
        self.assertEqual(rows[0]["validation_status"], "ERROR")
        self.assertFalse(validation[0]["path_continuity_valid"])

    def _run_tracked_execution(self, tracking):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_track_executed_routes"] = tracking
        graph.add_node(
            "S", type="area", people=10,
            people_dict={"L2": 10},
            source_group_dict={"L2_hall_people": 10},
        )
        graph.add_node(
            "Stair", type="stair", people=0,
            people_dict={"L2": 0}, source_group_dict={},
        )
        graph.add_node(
            "Exit", type="exit", people=0,
            people_dict={"L2": 0}, source_group_dict={},
        )
        graph.add_edge("S", "Stair", length=0, capacity=10)
        graph.add_edge("Stair", "Exit", length=0, capacity=10)
        net._initialize_executed_route_tracking(graph)
        net._schedule_moves_as_transit(graph, [("S", "Stair", 10)])
        net._process_transit_arrivals(graph, 0.0)
        net._schedule_moves_as_transit(graph, [("Stair", "Exit", 10)])
        evacuated = {"L2": 0.0}
        evacuated_groups = {"L2_hall_people": 0.0}
        exit_usage = {"Exit": {"L2": 0.0}}
        exit_groups = {"Exit": {}}
        net._process_transit_arrivals(
            graph, 0.0,
            evacuated_by_line=evacuated,
            evacuated_by_source_group=evacuated_groups,
            exit_usage_dict=exit_usage,
            exit_usage_by_source_group=exit_groups,
        )
        physical_state = {
            node: (
                graph.nodes[node]["people"],
                dict(graph.nodes[node]["people_dict"]),
                dict(graph.nodes[node]["source_group_dict"]),
            )
            for node in graph
        }
        return graph, physical_state, evacuated, evacuated_groups, exit_usage

    def test_route_tracking_does_not_change_physical_execution(self):
        untracked = self._run_tracked_execution(False)
        tracked = self._run_tracked_execution(True)
        self.assertEqual(untracked[1:], tracked[1:])
        completed = tracked[0].graph["_completed_executed_routes"]
        self.assertEqual(
            completed[("L2_hall_people", ("S", "Stair", "Exit"))], 10
        )

    def test_actual_integer_split_produces_two_continuous_routes(self):
        graph = self._route_graph()
        graph.graph["_sim_time"] = 0.0
        graph.graph["_transit_queue"] = []
        graph.graph["_track_executed_routes"] = True
        for node in graph:
            graph.nodes[node]["people"] = 0
            graph.nodes[node]["people_dict"] = {"L2": 0}
            graph.nodes[node]["source_group_dict"] = {}
        graph.nodes["S"]["people"] = 10
        graph.nodes["S"]["people_dict"]["L2"] = 10
        graph.nodes["S"]["source_group_dict"]["L2_hall_people"] = 10
        for u, v in graph.edges:
            graph[u][v]["length"] = 0
        net._initialize_executed_route_tracking(graph)
        net._schedule_moves_as_transit(
            graph, [("S", "Stair_A", 4), ("S", "Stair_B", 6)]
        )
        net._process_transit_arrivals(graph, 0.0)
        net._schedule_moves_as_transit(
            graph, [("Stair_A", "Gate_1", 4), ("Stair_B", "Gate_1", 6)]
        )
        net._process_transit_arrivals(graph, 0.0)
        net._schedule_moves_as_transit(graph, [("Gate_1", "Exit_1", 10)])
        net._process_transit_arrivals(graph, 0.0)
        completed = graph.graph["_completed_executed_routes"]
        self.assertEqual(
            completed[("L2_hall_people", ("S", "Stair_A", "Gate_1", "Exit_1"))],
            4,
        )
        self.assertEqual(
            completed[("L2_hall_people", ("S", "Stair_B", "Gate_1", "Exit_1"))],
            6,
        )

    def test_small_improved_metrics_are_identical_with_route_tracking(self):
        population = {
            line: {
                "train_1": 0, "train_2": 0, "platform_waiting": 0,
                "hall_people": 0, "transfer_people": 0,
            }
            for line in net.ALL_LINE_IDS
        }
        population["L2"]["hall_people"] = 10
        results = []
        for tracking in (False, True):
            graph = net.build_graph()
            graph.graph["density_dependent_flow"] = True
            graph.graph["spillback_enabled"] = True
            graph.graph["_track_executed_routes"] = tracking
            net.init_people(graph, population, apply_noise=False)
            targets = net._infer_target_by_line_from_graph_state(graph)
            results.append(net._run_simulation_for_metrics_core(
                graph,
                net.PAPER_SINGLE_PATH_METHOD,
                targets,
                collect_detailed_series=False,
            ))
        keys = (
            "time", "queueing_time", "moving_average_speed",
            "edge_traversal_average_speed", "effective_evacuation_speed",
            "exit_usage", "clearance_times_by_line", "edge_flow_totals",
        )
        for key in keys:
            self.assertEqual(results[0][key], results[1][key], key)


class ImprovedTemporaryHighCostRegressionTests(unittest.TestCase):
    def test_high_density_edge_recovers_on_the_next_step(self):
        graph = nx.DiGraph()
        graph.graph["_sim_time"] = 0.0
        graph.add_node("source", type="area", people=1, area=10)
        graph.add_node("gate", type="gate_wide", people=4, area=1)
        graph.add_edge(
            "source",
            "gate",
            length=1.0,
            weight=7.0,
            runtime_density=0.0,
        )

        active, _ = net._paper_refresh_temporary_high_cost_weights(
            graph
        )
        self.assertIn(("source", "gate"), active)
        self.assertEqual(
            graph["source"]["gate"]["sim_weight"],
            spr.PAPER_TEMPORARY_HIGH_COST,
        )
        self.assertEqual(graph["source"]["gate"]["weight"], 7.0)
        self.assertTrue(graph.has_edge("source", "gate"))

        graph.graph["_sim_time"] = 1.0
        graph.nodes["gate"]["people"] = 3
        active, _ = net._paper_refresh_temporary_high_cost_weights(
            graph
        )
        self.assertNotIn(("source", "gate"), active)
        self.assertLess(
            graph["source"]["gate"]["sim_weight"],
            spr.PAPER_TEMPORARY_HIGH_COST,
        )
        self.assertEqual(graph["source"]["gate"]["weight"], 7.0)
        diagnostics = graph.graph[
            "_improved_temporary_high_cost_diagnostics"
        ]
        self.assertEqual(
            diagnostics["recovered_next_step_events"], 1
        )
        self.assertEqual(
            diagnostics["stale_high_cost_state_count"], 0
        )


if __name__ == "__main__":
    unittest.main()
