import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import random
import numpy as np
import platform
import copy
import statistics
import os
import pandas as pd
import math
import sys
import time
import json
from time import perf_counter
import warnings
from bisect import bisect_right
from heapq import merge
from pathlib import Path

from calc_platform_dists import PATHFINDER_CONFIG
import single_path_routing as spr
import split_guidance as split_router

AA_INITIAL_ROUTING_BATCH_SIZE_DEFAULT = 0


def _install_predicted_queue_performance_counter():
    """Instrument AA queue prediction without changing its inputs or result."""
    current = spr.predicted_resource_queue_at_time
    if getattr(current, "_network_performance_counter", False):
        return

    original = current

    def measured(G, resource_id, target_time):
        started = time.perf_counter()
        result = original(G, resource_id, target_time)
        elapsed = time.perf_counter() - started
        if G.graph.get("_active_simulation_method") == OUR_SINGLE_PATH_METHOD:
            diagnostics = G.graph.setdefault("_aa_diagnostics", {})
            diagnostics["predicted_queue_query_runtime_seconds"] = (
                float(diagnostics.get("predicted_queue_query_runtime_seconds", 0.0))
                + elapsed
            )
        return result

    measured._network_performance_counter = True
    measured._original_function = original
    spr.predicted_resource_queue_at_time = measured


def _remove_predicted_queue_performance_counter():
    current = spr.predicted_resource_queue_at_time
    if getattr(current, "_network_performance_counter", False):
        spr.predicted_resource_queue_at_time = current._original_function


def _span_from_train_cfg(train_cfg):
    return {
        "start": train_cfg["start_pos"],
        "end": train_cfg["end_pos"],
    }


def _mid_span(train_a, train_b):
    return {
        "start": (
            (train_a["start_pos"][0] + train_b["start_pos"][0]) / 2.0,
            (train_a["start_pos"][1] + train_b["start_pos"][1]) / 2.0,
        ),
        "end": (
            (train_a["end_pos"][0] + train_b["end_pos"][0]) / 2.0,
            (train_a["end_pos"][1] + train_b["end_pos"][1]) / 2.0,
        ),
    }


def _span_mean_y(span):
    start = span.get("start")
    end = span.get("end")
    if not start or not end:
        return 0.0
    return (start[1] + end[1]) / 2.0


def _maglev_band_spans_by_train():
    train_cfgs = PATHFINDER_CONFIG.get("Maglev", {}).get("trains", [])
    if len(train_cfgs) < 4:
        return {}

    train_1_spans = [_span_from_train_cfg(train_cfgs[0]), _span_from_train_cfg(train_cfgs[1])]
    train_2_spans = [_span_from_train_cfg(train_cfgs[2]), _span_from_train_cfg(train_cfgs[3])]

    train_1_spans.sort(key=_span_mean_y, reverse=True)
    train_2_spans.sort(key=_span_mean_y, reverse=True)

    return {
        1: {
            "upper": train_1_spans[0],
            "middle": train_1_spans[1],
        },
        2: {
            "middle": train_2_spans[0],
            "lower": train_2_spans[1],
        },
    }


def _train_total_people(physics):
    if "train_people" in physics:
        return float(physics["train_people"])
    return float(physics["car_people"]) * float(physics["cars"])


def _car_people_from_physics(physics):
    return _train_total_people(physics) / max(float(physics["cars"]), 1.0)


def _interp_point(start, end, ratio):
    return (
        start[0] + (end[0] - start[0]) * ratio,
        start[1] + (end[1] - start[1]) * ratio,
    )


def _layout_point_from_span(train_span, car_idx, door_idx, car_count, door_count, fallback_pos):
    """
    train_span: 该列车的轴线 start/end
    car_idx:    第几节车厢
    door_idx:   0 表示车厢中心；1..door_count 表示车门
    """
    if not train_span or not train_span.get("start") or not train_span.get("end"):
        return fallback_pos

    start = train_span["start"]
    end = train_span["end"]

    car_start = _interp_point(start, end, (car_idx - 1) / car_count)
    car_end = _interp_point(start, end, car_idx / car_count)

    if door_idx == 0:
        return _interp_point(car_start, car_end, 0.5)

    return _interp_point(car_start, car_end, door_idx / (door_count + 1))
def _sorted_train_car_nodes(G, line_id, train_idx):
    prefix = f"Train_{line_id}_{train_idx}_Car"
    nodes = [
        n for n, d in G.nodes(data=True)
        if d.get("type") == "train_car" and n.startswith(prefix)
    ]

    def sort_key(name):
        car_idx = 0
        for part in name.split("_"):
            if part.startswith("Car"):
                try:
                    car_idx = int(part[3:])
                except ValueError:
                    car_idx = 0
        return (car_idx, name)

    return sorted(nodes, key=sort_key)


PAPER_SINGLE_PATH_METHOD = spr.PAPER_SINGLE_PATH_METHOD
OUR_SINGLE_PATH_METHOD = spr.OUR_SINGLE_PATH_METHOD
OUR_SPLIT_GUIDANCE_METHOD = spr.OUR_SPLIT_GUIDANCE_METHOD
METHOD_ALIASES = spr.METHOD_ALIASES
OUR_SINGLE_PATH_FAMILY_METHODS = {
    OUR_SINGLE_PATH_METHOD,
    spr.OUR_NO_WAITING_TIME_METHOD,
    spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD,
}
MESOSCOPIC_METHODS = {
    spr.MESOSCOPIC_PHYSICAL_TIME_METHOD,
    spr.MESOSCOPIC_CURRENT_QUEUE_METHOD,
}

METHOD_DISPLAY_NAMES = {
    PAPER_SINGLE_PATH_METHOD: "ImprovedAStar",
    OUR_SINGLE_PATH_METHOD: "AdaptiveQueueAwareAStar",
    OUR_SPLIT_GUIDANCE_METHOD: "Our Split Guidance",
    spr.OUR_NO_WAITING_TIME_METHOD: "NoWaitingTime (Density-Only)",
    spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD: "CurrentQueueAwareAStar",
    spr.MESOSCOPIC_PHYSICAL_TIME_METHOD: "MesoscopicPhysicalTimeAStar",
    spr.MESOSCOPIC_CURRENT_QUEUE_METHOD: "MesoscopicCurrentQueueAwareAStar",
}

METHOD_OUTPUT_TAGS = {
    PAPER_SINGLE_PATH_METHOD: "improved_astar",
    OUR_SINGLE_PATH_METHOD: "adaptive_queue_aware_astar",
    OUR_SPLIT_GUIDANCE_METHOD: "our_split_guidance",
    spr.OUR_NO_WAITING_TIME_METHOD: "no_waiting_time",
    spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD: "current_queue_aware_astar",
    spr.MESOSCOPIC_PHYSICAL_TIME_METHOD: "mesoscopic_physical_time_astar",
    spr.MESOSCOPIC_CURRENT_QUEUE_METHOD: "mesoscopic_current_queue_aware_astar",
}

OUTPUT_DIR = None


def _output_path(filename):
    if not filename or os.path.isabs(str(filename)):
        return filename
    if OUTPUT_DIR:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return os.path.join(OUTPUT_DIR, str(filename))
    return filename


SYSTEM_MODE_OUTPUTS = {
    1: ("mode1_regular_emergency", "Mode 1 - Regular emergency"),
    2: ("mode2_upbound_full_train", "Mode 2 - Upbound full train"),
    3: ("mode3_downbound_full_train", "Mode 3 - Downbound full train"),
    4: ("mode4_bidirectional_full_train", "Mode 4 - Bidirectional full train"),
}


def _set_system_mode_output_dir(mode):
    global OUTPUT_DIR
    slug, label = SYSTEM_MODE_OUTPUTS.get(mode, (f"mode{mode}", f"Mode {mode}"))
    OUTPUT_DIR = os.path.abspath(os.path.join(os.getcwd(), "outputs", slug))
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR, label

OUR_GUIDANCE_MIN_HOLD_SECONDS = 2.0
OUR_GUIDANCE_SWITCH_MARGIN = 0.03
OUR_GUIDANCE_FORCE_SWITCH_MARGIN = 0.20
# These facilities are physically parallel pairs in the L2 model.  The
# aggregate waiting-zone representation otherwise sends the whole zone to the
# marginally cheaper member and leaves the adjacent usable facility at zero.
L2_LOCAL_PARALLEL_VERTICALS = {}
# L18 has two physical gate pairs serving the same downstream exit corridors.
# A single-next-hop choice otherwise locks almost the whole flow onto the
# marginally shorter member (notably S2) while the adjacent gate remains idle.
L18_LOCAL_PARALLEL_GATES = {}
# Reversible high-load correction. Set this to False, or set
# G.graph["spillback_enabled"] = False, to recover the previous flow model.
HIGH_LOAD_SPILLBACK_ENABLED = True
HIGH_LOAD_JAM_DENSITY_P_PER_M2 = spr.PAPER_DENSITY_JAM
EDGE_RECEIVING_DENSITY_PARAMETER_NAME = (
    "edge_receiving_density_limit_p_per_m2"
)
EDGE_RECEIVING_DENSITY_LIMIT_P_PER_M2 = min(
    float(spr.PAPER_FREE_SPEED)
    / (2.0 * max(float(spr.PAPER_DENSITY_SLOPE), 1e-9)),
    float(spr.PAPER_DENSITY_JAM),
)
EDGE_RECEIVING_DENSITY_FORMULA = (
    "min(PAPER_FREE_SPEED / (2 * PAPER_DENSITY_SLOPE), "
    "PAPER_DENSITY_JAM)"
)
EDGE_RECEIVING_DENSITY_SOURCE = (
    "critical density maximizing q(k)=k*"
    "(PAPER_FREE_SPEED-PAPER_DENSITY_SLOPE*k), capped by "
    "PAPER_DENSITY_JAM"
)
EDGE_RECEIVING_HARD_LIMIT_ENABLED_DEFAULT = True
# Kept as a public compatibility constant. Node storage is now strictly
# physical and never enlarged by a time-based flow buffer.
HIGH_LOAD_MIN_RECEIVING_BUFFER_SECONDS = 0.0
DEFAULT_GATE_AREA_PER_UNIT_M2 = 2.0
GATE_QUEUE_AREAS_ENABLED_DEFAULT = (
    os.environ.get("GATE_QUEUE_AREAS_ENABLED", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)
GATE_QUEUE_AREA_LINES_DEFAULT = tuple(
    part.strip()
    for part in os.environ.get(
        "GATE_QUEUE_AREA_LINES", "L2,L7,L16,L18,Maglev"
    ).split(",")
    if part.strip()
)
GATE_QUEUE_DEPTH_M_DEFAULT = float(os.environ.get("GATE_QUEUE_DEPTH_M", "6.0"))
# Queue depth is a physical clearance assumption and is configured per line
# because the station halls do not have identical gate-bank geometry.
GATE_QUEUE_DEPTH_M_BY_LINE_DEFAULT = {
    "L7": 5.5,
    "L2": 7.0,
    "Maglev": 8.0,
    "L16": 8.0,
    "L18": 8.0,
}
GATE_QUEUE_SERVICE_EDGE_LENGTH_M = 0.2
VALID_DIRECTIONS = {"up", "down", "stop up", "stop down", "out", "one_way"}
_CONFIG_WARNING_EMITTED = False
# Set this to False, or set G.graph["guidance_corrections_enabled"] = False,
# to restore the previous reservation-cache and degradation-reference behavior.
GUIDANCE_CORRECTIONS_ENABLED = True
FACILITY_BASE_SPEED_M_PER_S = {
    "flat": 1.40,
    "stair": 0.75,
    "escalator": 0.50,
}

SINGLE_PATH_CASE_POPULATION = 100.0
SINGLE_PATH_CASE_SPECS = [
    {"case_id": "L2_C1", "line": "L2", "origin": "Platform_L2", "start_role": "platform"},
    {"case_id": "L2_C2", "line": "L2", "origin": "Stair_L2_1", "start_role": "stair_a"},
    {"case_id": "L2_C3", "line": "L2", "origin": "Stair_L2_3", "start_role": "stair_b"},
    {"case_id": "L2_C4", "line": "L2", "origin": "Escalator_L2_up1", "start_role": "escalator"},
    {"case_id": "L7_C1", "line": "L7", "origin": "Platform_L7", "start_role": "platform"},
    {"case_id": "L7_C2", "line": "L7", "origin": "Stair_L7_1", "start_role": "stair_a"},
    {"case_id": "L7_C3", "line": "L7", "origin": "Stair_L7_2", "start_role": "stair_b"},
    {"case_id": "L7_C4", "line": "L7", "origin": "Escalator_L7_up1", "start_role": "escalator"},
    {"case_id": "L18_C1", "line": "L18", "origin": "Platform_L18", "start_role": "platform"},
    {"case_id": "L18_C2", "line": "L18", "origin": "Stair_L18_1", "start_role": "stair_a"},
    {"case_id": "L18_C3", "line": "L18", "origin": "Stair_L18_2", "start_role": "stair_b"},
    {"case_id": "L18_C4", "line": "L18", "origin": "Escalator_L18_down3", "start_role": "escalator"},
]


def _normalize_method(method):
    return spr.normalize_method(method)


def _method_display_name(method):
    return METHOD_DISPLAY_NAMES.get(_normalize_method(method), _normalize_method(method))


def _method_output_tag(method):
    return METHOD_OUTPUT_TAGS.get(_normalize_method(method), _normalize_method(method).lower())


def _routing_base_method(method):
    return spr.routing_base_method(method)


def _uses_dynamic_a_star(method):
    return spr.uses_dynamic_a_star(method)


def _uses_multi_split(method):
    return _normalize_method(method) == OUR_SPLIT_GUIDANCE_METHOD


def _uses_paper_single_path(method):
    return _routing_base_method(method) == PAPER_SINGLE_PATH_METHOD


def _uses_predictive_single_path(method):
    return spr.uses_predictive_single_path(method)


def _is_key_facility_node(node_name, node_data):
    node_type = str(node_data.get("type", "")).lower()
    name = str(node_name)
    if name.startswith("VN_") or node_type == "virtual":
        return False
    if node_type in {"platform", "platform_waiting_zone", "exit"}:
        return False
    if "exit" in name.lower() and node_type in {"escalator", "stair"}:
        return False
    return node_type in {"gate", "escalator", "stair", "transfer"}


def _select_key_facility_nodes(G_base, method_metrics, top_k=8):
    candidates = []
    for node, data in G_base.nodes(data=True):
        if not _is_key_facility_node(node, data):
            continue
        total_queue_seconds = 0.0
        max_peak_density = 0.0
        for _, metrics in method_metrics:
            stat = metrics.get("node_stats", {}).get(node, {})
            total_queue_seconds += float(stat.get("queue_seconds", 0.0))
            max_peak_density = max(
                max_peak_density,
                float(stat.get("peak_congestion_index", stat.get("peak_density", 0.0))),
            )
        if total_queue_seconds <= 0.0 and max_peak_density <= 0.0:
            continue
        candidates.append((total_queue_seconds, max_peak_density, node))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [node for _, _, node in candidates[:top_k]]


def _heuristic_cost(u, v, d_dict, method):
    return spr.heuristic_cost(u, v, d_dict, method)


def _shortest_distances_to_exits(G):
    """Compute only node-to-exit static distances, not all-pairs distances."""
    result = {}
    reverse_graph = G.reverse(copy=False)
    for exit_node in spr.allowed_exit_nodes(G):
        lengths = nx.single_source_dijkstra_path_length(
            reverse_graph, exit_node, weight="length"
        )
        for node, distance in lengths.items():
            result.setdefault(node, {})[exit_node] = distance
    return result


def _node_out_capacity(G, node):
    return spr.node_out_capacity(G, node)


def _exit_outflow_capacity(G, exit_node):
    """Total inflow capacity of an exit (sum of capacities of incoming edges)."""
    total = 0.0
    for pred in G.predecessors(exit_node):
        total += float(G[pred][exit_node].get("capacity", 0.0))
    return max(total, 0.001)


def _path_total_cost(G, path, method, weight_key="sim_weight"):
    if not path or len(path) <= 1:
        return float("inf")

    if _uses_predictive_single_path(method) and hasattr(spr, "_aa_live_path_cost"):
        return spr._aa_live_path_cost(G, path, method)

    total = 0.0
    for idx in range(len(path) - 1):
        u = path[idx]
        v = path[idx + 1]
        if not G.has_edge(u, v):
            return float("inf")
        edge_cost = float(G[u][v].get(weight_key, float("inf")))
        if not math.isfinite(edge_cost):
            return float("inf")
        total += edge_cost

    return total


def _our_path_is_usable(G, current_node, path):
    if not path or len(path) <= 1 or path[0] != current_node:
        return False
    for idx in range(len(path) - 1):
        if not G.has_edge(path[idx], path[idx + 1]):
            return False
    return True


def _edge_dynamic_cost(G, u, v, method):
    return spr.edge_dynamic_cost(G, u, v, method, fruin_speed)


def update_dynamic_weights(G, method):
    spr.update_dynamic_weights(G, method, fruin_speed)


def get_split_next_moves(
    G,
    current_node,
    method,
    shortest_dists,
    score_ratio=1.15,
    score_slack=2.0,
    min_split_share=0.05,
):
    return split_router.get_split_next_moves(
        G,
        current_node,
        method,
        shortest_dists,
        fruin_speed,
        DELTA_T,
        score_ratio=score_ratio,
        score_slack=score_slack,
        min_split_share=min_split_share,
    )


def _has_parallel_service_successors(G, current_node, min_count=2):
    service_successors = [
        succ
        for succ in G.successors(current_node)
        if spr.is_capacity_service_node(G, succ)
    ]
    return len(service_successors) >= min_count


def _platform_local_parallel_path(G, path, source_prefix, parallel_map):
    """Build the current downstream route through a paired platform facility."""
    if not path or len(path) < 3:
        return None
    source, primary, downstream = path[0], path[1], path[2]
    if not str(source).startswith(source_prefix):
        return None
    alternate = parallel_map.get(primary)
    if not alternate:
        return None
    if not G.has_edge(source, alternate) or not G.has_edge(alternate, downstream):
        return None
    alternate_path = [source, alternate] + list(path[2:])
    return alternate_path if _our_path_is_usable(G, source, alternate_path) else None


def _l18_local_parallel_gate_path(G, path):
    """Keep the selected exit but use the paired L18 gate in parallel."""
    if not path or len(path) < 3:
        return None
    source, primary, downstream = path[0], path[1], path[2]
    alternate = L18_LOCAL_PARALLEL_GATES.get(primary)
    if not alternate:
        return None
    if not G.has_edge(source, alternate) or not G.has_edge(alternate, downstream):
        return None
    alternate_path = [source, alternate] + list(path[2:])
    return alternate_path if _our_path_is_usable(G, source, alternate_path) else None


def _choose_our_single_path_with_inertia(G, current_node, shortest_dists, method):
    method = _normalize_method(method)
    candidates = spr.enumerate_exit_paths(
        G,
        current_node,
        method,
        shortest_dists,
        fruin_speed,
    )
    if not candidates:
        return None

    best = candidates[0]
    guidance_state = G.graph.setdefault("_our_guidance_state", {})
    sim_time = float(G.graph.get("_sim_time", 0.0))
    prev = guidance_state.get(current_node)

    chosen = best
    switched_at = sim_time
    decision_reason = "initial"

    prev_usable = bool(prev and _our_path_is_usable(G, current_node, prev.get("path")))
    if prev_usable:
        prev_path = prev["path"]
        prev_cost = _path_total_cost(G, prev_path, method)
        best_cost = float(best["cost"])
        prev_next = prev.get("next_hop")
        best_next = best.get("next_hop")
        held_for = sim_time - float(prev.get("switched_at", sim_time))
        selected_cost = float(prev.get("selected_cost", prev_cost))

        # Degradation trigger: if the current path cost has grown >50% since
        # selection and a better alternative exists (>2% improvement), force
        # a switch regardless of hold time or normal switch margin.
        degraded = False
        if selected_cost > 0 and math.isfinite(prev_cost):
            cost_growth = prev_cost / selected_cost
            if cost_growth > 1.5 and best_cost < prev_cost * 0.98:
                degraded = True

        if best_next == prev_next:
            switched_at = float(prev.get("switched_at", sim_time))
            decision_reason = "same_next_hop"
        elif degraded:
            chosen = best
            switched_at = sim_time
            decision_reason = "degraded"
        elif math.isfinite(prev_cost):
            clearly_better = best_cost <= prev_cost * (1.0 - OUR_GUIDANCE_SWITCH_MARGIN)
            force_switch = best_cost <= prev_cost * (1.0 - OUR_GUIDANCE_FORCE_SWITCH_MARGIN)
            if (held_for < OUR_GUIDANCE_MIN_HOLD_SECONDS and not force_switch) or (
                not clearly_better and not force_switch
            ):
                chosen = {
                    "target": prev_path[-1],
                    "path": prev_path,
                    "next_hop": prev_next,
                    "cost": prev_cost,
                }
                switched_at = float(prev.get("switched_at", sim_time))
                decision_reason = "hold"
            else:
                decision_reason = "force_switch" if force_switch else "better_route"

    corrections_enabled = G.graph.get(
        "guidance_corrections_enabled", GUIDANCE_CORRECTIONS_ENABLED
    )
    route_changed = not prev_usable or chosen.get("next_hop") != prev.get("next_hop")
    if route_changed or not corrections_enabled:
        selection_reference_cost = float(chosen["cost"])
    else:
        # Preserve the cost at the last actual next-hop switch. Overwriting it
        # every step made gradual deterioration invisible to the >50% trigger.
        selection_reference_cost = float(prev.get("selected_cost", chosen["cost"]))

    guidance_state[current_node] = {
        "path": chosen["path"],
        "next_hop": chosen["next_hop"],
        "switched_at": switched_at,
        "selected_cost": selection_reference_cost,
        "current_cost": float(chosen["cost"]),
        "decision_reason": decision_reason,
        "path_version": (
            int(prev.get("path_version", 0)) + 1
            if prev and route_changed
            else int(prev.get("path_version", 1)) if prev else 1
        ),
    }
    return chosen["path"]


def _next_cohort_id(G):
    sequence = int(G.graph.get("_mesoscopic_cohort_sequence", 0)) + 1
    G.graph["_mesoscopic_cohort_sequence"] = sequence
    return f"cohort_{sequence}"


def _ensure_node_mesoscopic_cohorts(G, node):
    """Materialize existing source totals as natural, uncommitted cohorts."""
    data = G.nodes[node]
    if "_mesoscopic_cohorts" in data:
        return data["_mesoscopic_cohorts"]
    arrival_time = float(G.graph.get("_sim_time", 0.0))
    cohorts = []
    for source_group, amount in sorted(data.get("source_group_dict", {}).items()):
        amount = max(int(amount), 0)
        if amount:
            cohorts.append({
                "cohort_id": _next_cohort_id(G),
                "source_group": source_group,
                "arrival_time": arrival_time,
                "amount": amount,
                "committed_segment": [],
                "segment_index": 0,
                "next_decision_node": None,
                "committed": False,
            })
    data["_mesoscopic_cohorts"] = cohorts
    return cohorts


def _first_branch_signature(G, origin, successor):
    """Return the first key resource/exit reached without returning to origin."""
    queue = [(successor, 0)]
    seen = {origin}
    signatures = set()
    while queue:
        node, depth = queue.pop(0)
        if node in seen or depth > 12:
            continue
        seen.add(node)
        node_type = str(G.nodes[node].get("type", "")).lower()
        if node_type == "exit" or spr.is_capacity_service_node(G, node):
            signatures.add(node)
            continue
        successors = [n for n in G.successors(node) if n not in seen]
        if len(successors) > 1:
            signatures.add(f"channel:{node}")
            continue
        queue.extend((n, depth + 1) for n in successors)
    return tuple(sorted(signatures, key=str))


def routing_decision_options(G, node):
    cache = G.graph.setdefault("_routing_decision_option_cache", {})
    if node in cache:
        return cache[node]
    options = []
    for successor in G.successors(node):
        signature = _first_branch_signature(G, node, successor)
        if signature:
            options.append((successor, signature))
    cache[node] = options
    return options


def is_routing_decision_node(G, node):
    explicit = G.nodes[node].get("routing_decision")
    if explicit is not None:
        return bool(explicit)
    options = routing_decision_options(G, node)
    return len({signature for _, signature in options}) >= 2


def write_routing_decision_nodes_report(G, output_path="routing_decision_nodes_report.md"):
    lines = [
        "# 路由决策节点报告",
        "",
        "自动识别规则：显式 `routing_decision` 优先；否则至少两个后继分支必须通往不同的首个关键设施、通道分叉或出口。",
        "",
        "| 节点 | 类型 | 可选后继 | 对应关键设施/通道 | 识别依据 | 显式配置 |",
        "|---|---|---|---|---|---|",
    ]
    for node in sorted(G.nodes, key=str):
        if not is_routing_decision_node(G, node):
            continue
        options = routing_decision_options(G, node)
        explicit = G.nodes[node].get("routing_decision")
        lines.append(
            "| {node} | {node_type} | {successors} | {signatures} | {basis} | {explicit} |".format(
                node=node,
                node_type=G.nodes[node].get("type", ""),
                successors="<br>".join(str(s) for s, _ in options),
                signatures="<br>".join(", ".join(map(str, sig)) for _, sig in options),
                basis="显式属性" if explicit is not None else "不同首个关键方向",
                explicit="是" if explicit is not None else "否",
            )
        )
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _peek_resource_integer_capacity(G, resource_id, demand):
    capacity = resource_capacity_per_second(G, resource_id)
    if math.isinf(capacity):
        return max(int(demand), 0)
    carry = float(G.graph.get("_resource_flow_credit", {}).get(resource_id, 0.0))
    return max(int(math.floor(max(capacity, 0.0) * DELTA_T + carry + 1e-9)), 0)


def node_integer_departure_budget(G, node):
    """Physical upper bound for cohorts that may request departure this step."""
    available = max(int(G.nodes[node].get("people", 0)), 0)
    if available <= 0:
        return 0
    by_resource = {}
    reserved = _reserved_transit_by_node(G)
    for successor in G.successors(node):
        resource_id = edge_resource_id(G, node, successor)
        resource_cap = _peek_resource_integer_capacity(G, resource_id, available)
        # Fractional credits advance inside the common allocator only when a
        # request exists. A positive-rate resource therefore needs one pending
        # application even on a zero-whole-credit step; the allocator may still
        # reject it, and rejected people remain uncommitted upstream.
        if resource_cap <= 0 and resource_capacity_per_second(G, resource_id) > 0:
            resource_cap = 1
        slots = _node_receiving_slots(G, successor, reserved.get(successor, 0.0))
        receiving_cap = available if math.isinf(slots) else int(slots)
        feasible = min(resource_cap, receiving_cap, available)
        by_resource[resource_id] = max(by_resource.get(resource_id, 0), feasible)
    return min(sum(by_resource.values()), available)


def _path_segment_to_next_decision(G, path):
    if not path or len(path) < 2:
        return [], None
    for index, node in enumerate(path[1:], start=1):
        if G.nodes[node].get("type") == "exit" or is_routing_decision_node(G, node):
            return path[: index + 1], node
    return list(path), path[-1]


def _mesoscopic_path_for_step(G, node, method, shortest_dists):
    sim_time = float(G.graph.get("_sim_time", 0.0))
    cache = G.graph.setdefault("_mesoscopic_step_path_cache", {})
    if G.graph.get("_mesoscopic_step_path_cache_time") != sim_time:
        cache.clear()
        G.graph["_mesoscopic_step_path_cache_time"] = sim_time
    key = (method, node)
    if key not in cache:
        cache[key] = spr.mesoscopic_full_graph_path(G, node, method, shortest_dists)
    return cache[key]


def _integerize_mesoscopic_requests(G, requests):
    """Use the common allocator, then attach commitment only to accepted cohorts."""
    grouped = {}
    for request in requests:
        key = (request["u"], request["v"])
        grouped[key] = grouped.get(key, 0) + int(request["requested"])
    accepted_moves = _integerize_moves(
        G, [(u, v, amount) for (u, v), amount in grouped.items()]
    )
    accepted_by_edge = {(u, v): int(amount) for u, v, amount in accepted_moves}
    allocations = {}
    for request in requests:
        key = (request["u"], request["v"])
        accepted = min(int(request["requested"]), accepted_by_edge.get(key, 0))
        accepted_by_edge[key] = accepted_by_edge.get(key, 0) - accepted
        rejected_choices = G.graph.setdefault("_mesoscopic_last_rejected_choice", {})
        if int(request["requested"]) > accepted:
            rejected_choices[request["cohort_id"]] = request["v"]
        else:
            rejected_choices.pop(request["cohort_id"], None)
        if accepted <= 0:
            continue
        item = dict(request)
        item["amount"] = accepted
        allocations.setdefault(key, []).append(item)
    G.graph["_mesoscopic_accepted_allocations"] = allocations
    used_by_resource = {}
    for u, v, amount in accepted_moves:
        resource_id = edge_resource_id(G, u, v)
        used_by_resource[resource_id] = used_by_resource.get(resource_id, 0) + int(amount)
    reachable = G.graph.get("_mesoscopic_reachable_demand", {})
    requested_resources = {
        edge_resource_id(G, request["u"], request["v"]) for request in requests
    }
    cumulative = G.graph.setdefault("_mesoscopic_resource_execution", {})
    step_capacities = G.graph.get("_last_resource_step_capacity", {})
    for resource_id in set(reachable) | requested_resources:
        if resource_id in step_capacities:
            available = int(step_capacities[resource_id])
        else:
            available = _peek_resource_integer_capacity(
                G, resource_id, int(reachable.get(resource_id, 0))
            )
        used = int(used_by_resource.get(resource_id, 0))
        unused = max(available - used, 0)
        demand = int(reachable.get(resource_id, 0))
        stat = cumulative.setdefault(resource_id, {
            "total_available_integer_capacity": 0,
            "used_integer_capacity": 0,
            "unused_integer_capacity": 0,
            "upstream_reachable_demand_person_steps": 0,
            "idle_time_with_reachable_demand": 0.0,
            "busy_time": 0.0,
        })
        stat["total_available_integer_capacity"] += available
        stat["used_integer_capacity"] += used
        stat["unused_integer_capacity"] += unused
        stat["upstream_reachable_demand_person_steps"] += demand
        if used > 0:
            stat["busy_time"] += DELTA_T
        if unused > 0 and demand > 0:
            stat["idle_time_with_reachable_demand"] += DELTA_T
    return accepted_moves


def _get_mesoscopic_step_moves(G, active_nodes, shortest_dists, method):
    requests = []
    diagnostics = G.graph.setdefault("_mesoscopic_diagnostics", {})
    diagnostics["decision_count"] = int(diagnostics.get("decision_count", 0))
    entry_resources = G.graph.get("_mesoscopic_entry_resources")
    if entry_resources is None:
        entry_resources = {}
        for resource_id, controls in iter_physical_resources(G).items():
            for edge_u, _ in controls:
                entry_resources.setdefault(edge_u, set()).add(resource_id)
        G.graph["_mesoscopic_entry_resources"] = entry_resources
    reachable_demand = {}
    for node in active_nodes:
        cohorts = [c for c in _ensure_node_mesoscopic_cohorts(G, node) if int(c["amount"]) > 0]
        uncommitted = sum(int(c["amount"]) for c in cohorts if not c.get("committed"))
        if uncommitted > 0:
            descendants_cache = G.graph.setdefault("_mesoscopic_descendants_cache", {})
            reachable_nodes = descendants_cache.get(node)
            if reachable_nodes is None:
                reachable_nodes = nx.descendants(G, node) | {node}
                descendants_cache[node] = reachable_nodes
            for reachable_node in reachable_nodes:
                for resource_id in entry_resources.get(reachable_node, ()):
                    reachable_demand[resource_id] = (
                        reachable_demand.get(resource_id, 0) + uncommitted
                    )
        budget = node_integer_departure_budget(G, node)
        if not cohorts or budget <= 0:
            continue
        allocations = _integer_capped_allocation(
            budget,
            [int(c["amount"]) for c in cohorts],
            [int(c["amount"]) for c in cohorts],
        )
        for cohort, requested in zip(cohorts, allocations):
            if requested <= 0:
                continue
            segment = list(cohort.get("committed_segment", []))
            index = int(cohort.get("segment_index", 0))
            committed = bool(cohort.get("committed"))
            if committed and index + 1 < len(segment) and segment[index] == node:
                path_segment = segment
                next_node = segment[index + 1]
                next_decision = cohort.get("next_decision_node")
            else:
                if committed:
                    diagnostics["nondecision_replan_count"] = int(
                        diagnostics.get("nondecision_replan_count", 0)
                    ) + 1
                path = _mesoscopic_path_for_step(G, node, method, shortest_dists)
                if not path or len(path) < 2:
                    continue
                path_segment, next_decision = _path_segment_to_next_decision(G, path)
                next_node = path_segment[1]
                index = 0
                diagnostics["decision_count"] += 1
                last_rejected = G.graph.setdefault(
                    "_mesoscopic_last_rejected_choice", {}
                ).get(cohort["cohort_id"])
                if last_rejected is not None and last_rejected != next_node:
                    diagnostics["reroute_after_rejection_count"] = int(
                        diagnostics.get("reroute_after_rejection_count", 0)
                    ) + 1
            requests.append({
                "u": node,
                "v": next_node,
                "requested": int(requested),
                "cohort_id": cohort["cohort_id"],
                "source_group": cohort["source_group"],
                "arrival_time": cohort["arrival_time"],
                "committed_segment": path_segment,
                "segment_index": index,
                "next_decision_node": next_decision,
            })
    G.graph["_mesoscopic_reachable_demand"] = reachable_demand
    return _integerize_mesoscopic_requests(G, requests)


def _next_aa_batch_id(G):
    value = int(G.graph.get("_aa_batch_sequence", 0)) + 1
    G.graph["_aa_batch_sequence"] = value
    return f"aa_batch_{value}"


def _split_integer_amount(total_amount, max_batch_size):
    total_amount = max(int(total_amount), 0)
    if total_amount <= 0:
        return []
    if not max_batch_size or max_batch_size <= 0:
        return [total_amount]
    result = []
    while total_amount > 0:
        amount = min(total_amount, int(max_batch_size))
        result.append(amount)
        total_amount -= amount
    return result


def _ensure_node_aa_batches(G, node):
    data = G.nodes[node]
    if "_aa_batches" in data:
        return data["_aa_batches"]
    now = float(G.graph.get("_sim_time", 0.0))
    source_amounts = {
        source_group: int(amount)
        for source_group, amount in data.get("source_group_dict", {}).items()
        if int(amount) > 0
    }
    if not source_amounts:
        source_amounts = {
            f"{line_id}_unspecified": int(amount)
            for line_id, amount in data.get("people_dict", {}).items()
            if int(amount) > 0
        }
    if not source_amounts and int(data.get("people", 0)) > 0:
        source_amounts = {"unknown_unspecified": int(data["people"])}
    batch_size = int(
        G.graph.get(
            "aa_initial_routing_batch_size",
            AA_INITIAL_ROUTING_BATCH_SIZE_DEFAULT,
        )
        or 0
    )
    batches = []
    for source_group, amount in sorted(source_amounts.items()):
        for split_amount in _split_integer_amount(amount, batch_size):
            batches.append({
                "batch_id": _next_aa_batch_id(G),
                "source_group": source_group,
                "arrival_time": now,
                "amount": int(split_amount),
                "current_node": node,
                "current_path": [],
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
            })
    data["_aa_batches"] = batches
    return data["_aa_batches"]


def _aa_batch_merge_key(batch):
    opportunity_items = tuple(
        sorted(
            (
                repr(key),
                float(value),
            )
            for key, value in (
                batch.get("step4b2_opportunity_best") or {}
            ).items()
        )
    )
    return (
        batch.get("source_group"),
        float(batch.get("arrival_time", 0.0)),
        tuple(batch.get("current_path") or []),
        batch.get("waiting_resource"),
        batch.get("queue_enter_time"),
        batch.get("planned_selection_node"),
        batch.get("plan_history_node"),
        tuple(batch.get("selected_first_hops") or ()),
        bool(batch.get("has_rerouted", False)),
        bool(batch.get("gate_switch_in_progress", False)),
        bool(batch.get("gate_switch_completed", False)),
        bool(batch.get("service_committed", False)),
        bool(batch.get("precommit_pending", False)),
        batch.get("gate_switch_target_queue"),
        (
            batch.get("batch_id")
            if "executed_route_batches" in batch
            else None
        ),
        tuple(
            (
                item.get("source_group"),
                tuple(item.get("path") or ()),
                int(item.get("amount", 0)),
            )
            for item in batch.get("executed_route_batches", ())
        ),
        opportunity_items,
        tuple(
            (
                item.get("u"),
                item.get("v"),
                item.get(
                    "resource_entry_time"
                ),
            )
            for item in batch.get(
                "path_predictions",
                [],
            )
        ),
    )


def _aa_signature_float(value, digits=9):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number):
        return "nan"
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    return round(number, digits)


def _aa_prediction_cost_from_details(details):
    if not details:
        return None
    value = details[-1].get("objective_cost")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _aa_shift_prediction_times(details, delta):
    shifted = []
    for item in details or ():
        row = dict(item)
        for field in ("resource_entry_time", "arrival_time"):
            if field not in row:
                continue
            try:
                value = float(row[field])
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                row[field] = value + delta
        shifted.append(row)
    return shifted


def _aa_path_prediction_state_signature(G, path, amount, predictive):
    path = tuple(path or ())
    if len(path) < 2:
        return ("invalid", path, int(amount), bool(predictive))

    prediction_versions = G.graph.get("_aa_round_prediction_versions", {})
    step_capacity = G.graph.get("_aa_step_resource_capacity", {})
    edge_records = spr.ensure_aa_step_edge_records(G)
    resources = []
    nodes = set(path)

    for u, v in zip(path, path[1:]):
        if not G.has_edge(u, v):
            return ("missing_edge", path, int(amount), bool(predictive), u, v)
        resource_id, travel, edge_density, _risk, service_rate = edge_records[(u, v)]
        resources.append((
            resource_id,
            _aa_signature_float(spr.current_resource_queue(G, resource_id)),
            _aa_signature_float(service_rate),
            _aa_signature_float(travel),
            _aa_signature_float(edge_density),
            _aa_signature_float(G[u][v].get("runtime_passengers", 0.0)),
            int(prediction_versions.get(resource_id, 0)),
            (
                int(step_capacity.get(resource_id))
                if resource_id in step_capacity
                else None
            ),
        ))

    node_state = []
    blocked_sources = G.graph.get("_current_spatial_blocked_sources", {})
    for node in sorted(nodes, key=str):
        if node not in G.nodes:
            continue
        data = G.nodes[node]
        density = spr.spatial_effective_density(G, node)
        node_state.append((
            node,
            str(data.get("type", "")),
            _aa_signature_float(data.get("people", 0.0)),
            _aa_signature_float(data.get("area", 0.0)),
            _aa_signature_float(density),
            _aa_signature_float(blocked_sources.get(node, 0.0)),
        ))

    return (
        path,
        int(amount),
        bool(predictive),
        _aa_signature_float(spr.aa_safety_weight(G)),
        tuple(resources),
        tuple(node_state),
    )


def _aa_store_path_prediction_cache(
    G,
    batch,
    path,
    details,
    amount,
    predictive,
    now,
    *,
    cost=None,
):
    details = [dict(item) for item in details or ()]
    batch["path_predictions"] = details
    if not details:
        batch.pop("path_prediction_signature", None)
        batch.pop("path_prediction_time", None)
        batch.pop("path_prediction_cost", None)
        return

    batch["path_prediction_signature"] = _aa_path_prediction_state_signature(
        G,
        path,
        amount,
        predictive,
    )
    batch["path_prediction_time"] = float(now)
    if cost is None:
        cost = _aa_prediction_cost_from_details(details)
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        cost = None
    if cost is not None and math.isfinite(cost):
        batch["path_prediction_cost"] = cost
    else:
        batch.pop("path_prediction_cost", None)


def _aa_reuse_cached_path_prediction(batch, now):
    cached = [dict(item) for item in batch.get("path_predictions") or ()]
    if not cached:
        return None, []
    cost = batch.get("path_prediction_cost")
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        cost = _aa_prediction_cost_from_details(cached)
    if cost is None or not math.isfinite(cost):
        return None, []
    cached_time = float(batch.get("path_prediction_time", now))
    shifted = _aa_shift_prediction_times(cached, float(now) - cached_time)
    batch["path_predictions"] = [dict(item) for item in shifted]
    batch["path_prediction_time"] = float(now)
    batch["path_prediction_cost"] = float(cost)
    return float(cost), shifted


def _aa_path_prediction_miss_reason(cached_signature, current_signature):
    if not cached_signature:
        return "missing_signature"
    if not current_signature:
        return "missing_current_signature"
    if len(cached_signature) != len(current_signature):
        return "signature_shape"
    if cached_signature[0] != current_signature[0]:
        return "path"
    if cached_signature[1] != current_signature[1]:
        return "amount"
    if cached_signature[2] != current_signature[2]:
        return "predictive_mode"
    if cached_signature[3] != current_signature[3]:
        return "safety_weight"

    cached_resources = tuple(cached_signature[4])
    current_resources = tuple(current_signature[4])
    if len(cached_resources) != len(current_resources):
        return "resource_shape"
    for cached, current in zip(cached_resources, current_resources):
        if cached[0] != current[0]:
            return "resource_id"
        resource_fields = (
            "resource_queue",
            "resource_capacity",
            "edge_travel_time",
            "edge_density",
            "edge_runtime_passengers",
            "round_prediction_version",
            "step_capacity",
        )
        for index, field in enumerate(resource_fields, start=1):
            if cached[index] != current[index]:
                return field

    cached_nodes = tuple(cached_signature[5])
    current_nodes = tuple(current_signature[5])
    if len(cached_nodes) != len(current_nodes):
        return "node_shape"
    for cached, current in zip(cached_nodes, current_nodes):
        if cached[0] != current[0]:
            return "node_id"
        node_fields = (
            "node_type",
            "node_people",
            "node_area",
            "node_density",
            "node_blocked_source",
        )
        for index, field in enumerate(node_fields, start=1):
            if cached[index] != current[index]:
                return field
    return "other"


def _append_aa_batch(G, node, batch):
    node_data = G.nodes[node]
    batches = node_data.setdefault(
        "_aa_batches",
        [],
    )
    arrival_epoch = int(
        G.graph.get(
            "_aa_arrival_merge_epoch",
            0,
        )
    )

    if (
        node_data.get(
            "_aa_batch_merge_index_epoch"
        )
        != arrival_epoch
    ):
        merge_index = {}

        for existing in batches:
            key = _aa_batch_merge_key(existing)

            merge_index.setdefault(
                key,
                existing,
            )

        node_data[
            "_aa_batch_merge_index"
        ] = merge_index

        node_data[
            "_aa_batch_merge_index_epoch"
        ] = arrival_epoch
    else:
        merge_index = node_data.setdefault(
            "_aa_batch_merge_index",
            {},
        )

    merge_key = _aa_batch_merge_key(batch)
    existing = merge_index.get(merge_key)

    if existing is not None:
        existing["amount"] = (
            int(existing.get("amount", 0))
            + int(batch.get("amount", 0))
        )
        return existing

    batches.append(batch)
    merge_index[merge_key] = batch
    return batch


def _is_explicit_aa_selection_stage(G, node):
    data = G.nodes[node]
    if "aa_selection_stage" in data:
        return bool(data["aa_selection_stage"])
    node_type = str(data.get("type", "")).lower()
    name = str(node)
    return (
        node_type in {"platform_waiting_zone", "stair", "escalator"}
        or node_type.startswith("gate")
        or "gate" in node_type
        or "Hall_Arrival" in name
        or "Mid_Platform" in name
        or "Transfer_Start" in name
    )


def _record_step0_aa_candidate_diagnostics(G, node, batch, now, best_path):
    """Capture one representative snapshot per requested Step 0 decision."""
    if not best_path:
        return
    source_group = str(batch.get("source_group", ""))
    line_id, source_type, _ = _parse_source_group_id(source_group)
    is_l7_train = line_id == "L7" and source_type in {
        "train_1", "train_2"
    }
    is_maglev_train = line_id == "Maglev" and source_type in {
        "train_1", "train_2"
    }
    chosen_exit = str(best_path[-1])
    category = None
    targets = ()
    l2_exits = (
        "Exit_L2_2", "Exit_L2_3", "Exit_L2_4", "Exit_L2_6"
    )
    l7_and_l2_exits = (
        "Exit_L7_7", "Exit_L7_8/9", *l2_exits
    )
    maglev_and_l2_exits = (
        "Exit_Maglev_18",
        "Exit_Maglev_19",
        "Exit_Maglev_20",
        "Exit_Maglev_21",
        *l2_exits,
    )
    if line_id == "L2" and chosen_exit in l2_exits:
        category = f"L2_choose_{chosen_exit}"
        targets = l2_exits
    elif is_l7_train and chosen_exit.startswith("Exit_L7_"):
        category = f"{source_group}_choose_L7_exit"
        targets = l7_and_l2_exits
    elif is_l7_train and chosen_exit == "Exit_L2_2":
        category = f"{source_group}_choose_Exit_L2_2"
        targets = l7_and_l2_exits
    elif is_l7_train and chosen_exit.startswith("Exit_L2_"):
        category = f"{source_group}_choose_L2_exit"
        targets = l7_and_l2_exits
    elif is_maglev_train and chosen_exit.startswith("Exit_Maglev_"):
        category = f"{source_group}_choose_Maglev_exit"
        targets = maglev_and_l2_exits
    elif is_maglev_train and chosen_exit.startswith("Exit_L2_"):
        category = f"{source_group}_choose_L2_exit"
        targets = maglev_and_l2_exits
    if category is None:
        return

    captured = G.graph.setdefault(
        "_step0_aa_candidate_categories", set()
    )
    if category in captured:
        return
    captured.add(category)
    rows = spr.diagnose_time_dependent_exit_candidates(
        G,
        node,
        now,
        int(batch.get("amount", 0)),
        targets,
    )
    output = G.graph.setdefault(
        "_step0_aa_candidate_diagnostics", []
    )
    for row in rows:
        output.append({
            "category": category,
            "sim_time": float(now),
            "source_group": source_group,
            "start_node": node,
            "batch_people": int(batch.get("amount", 0)),
            "chosen_exit": chosen_exit,
            **row,
        })


# A deterministic shortest-path tie break can leave a real parallel exit
# unused even when it is reachable from the same line.  Keep this as an
# explicit operational coverage policy: it may select only an existing,
# finite A* candidate and never changes topology or splits a batch.
_EXIT_COVERAGE_EXCLUDED = {"Exit_L18_13"}
_EXIT_COVERAGE_SOURCE_TYPES = {
    "platform_waiting",
    "train_1",
    "train_2",
}


def _same_line_exit_targets(G, line_id):
    line_id = str(line_id or "")
    if not line_id:
        return []
    prefix = f"Exit_{line_id}_"
    return sorted(
        node
        for node, data in G.nodes(data=True)
        if data.get("type") == "exit"
        and str(node).startswith(prefix)
        and str(node) not in _EXIT_COVERAGE_EXCLUDED
    )


def _routing_node_line_id(G, node):
    data = G.nodes.get(node, {})
    configured = data.get("line_id")
    if configured:
        return str(configured)
    name = str(node)
    for line_id in ("Maglev", "L18", "L16", "L7", "L2"):
        if (
            name.startswith(f"Train_{line_id}_")
            or f"_{line_id}_" in name
            or name.startswith(f"Platform_{line_id}")
        ):
            return line_id
    return ""


def _select_exit_coverage_candidate(
    G,
    line_id,
    candidates,
    used_key,
):
    """Return the lowest-cost feasible candidate for an unused same-line exit."""
    targets = _same_line_exit_targets(G, line_id)
    if len(targets) <= 1:
        return None
    used_by_line = G.graph.setdefault(used_key, {})
    used = set(used_by_line.setdefault(str(line_id), []))
    feasible_targets = {
        str(item.get("target"))
        for item in candidates
        if math.isfinite(float(item.get("cost", float("inf"))))
    }
    missing = set(targets) - used
    if not missing or not (missing & feasible_targets):
        return None
    missing_candidates = [
        item
        for item in candidates
        if str(item.get("target")) in missing
        and math.isfinite(float(item.get("cost", float("inf"))))
    ]
    if not missing_candidates:
        return None
    return min(
        missing_candidates,
        key=lambda item: (
            float(item.get("cost", float("inf"))),
            len(item.get("path") or ()),
            str(item.get("target")),
        ),
    )


def _paper_exit_coverage_allowed(G, node):
    """Keep cross-line transfer batches free to choose any feasible exit.

    Exit coverage is an operational tie-break for local source groups.  A
    transfer batch can legitimately evacuate through the destination line's
    exit, so forcing it back to a same-line exit can create a long cross-line
    detour that is not implied by the density cost.
    """
    source_groups = G.nodes.get(node, {}).get("source_group_dict", {})
    for source_group_id, amount in source_groups.items():
        if float(amount) <= 0.0:
            continue
        _, source_type, _ = _parse_source_group_id(str(source_group_id))
        if source_type == "transfer_people":
            return False
    return True


def _register_exit_coverage_target(G, line_id, target, used_key):
    if not line_id or not target:
        return
    used_by_line = G.graph.setdefault(used_key, {})
    used = used_by_line.setdefault(str(line_id), [])
    if target not in used:
        used.append(str(target))


def _gate_facility_from_path(G, path):
    for node in path or ():
        if node not in G.nodes:
            continue
        data = G.nodes[node]
        if str(data.get("type", "")).lower().startswith("gate"):
            return (
                str(node).removesuffix("_Queue")
                if str(node).endswith("_Queue")
                else str(node)
            )
    return None


def _paper_path_via_unused_gate(G, start, target, line_id):
    """Find an existing target path through an as-yet-unused gate branch."""
    used_gates = set(
        G.graph.get("_paper_exit_coverage_used_gates", {}).get(
            str(line_id), []
        )
    )
    gate_prefix = f"Gate_{line_id}_"
    gate_nodes = sorted(
        node
        for node, data in G.nodes(data=True)
        if str(node).startswith(gate_prefix)
        and not str(node).endswith("_Queue")
        and str(data.get("type", "")).lower().startswith("gate")
        and _gate_queue_node_name(node) in G.nodes
        and node not in used_gates
    )
    candidates = []
    for gate in gate_nodes:
        queue_node = _gate_queue_node_name(gate)
        try:
            upstream = nx.shortest_path(
                G,
                start,
                queue_node,
                weight="sim_weight",
            )
            downstream = nx.shortest_path(
                G,
                gate,
                target,
                weight="sim_weight",
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        path = list(upstream) + list(downstream)
        if (
            len(path) <= 1
            or len(set(path)) != len(path)
            or any(
                G[u][v].get("gate_switch_only")
                for u, v in zip(path, path[1:])
            )
        ):
            continue
        cost = sum(
            float(G[u][v].get("sim_weight", float("inf")))
            for u, v in zip(path, path[1:])
        )
        if math.isfinite(cost):
            candidates.append((cost, gate, path))
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (item[0], len(item[2]), str(item[1])),
    )


def _register_exit_coverage_gate(G, line_id, gate):
    if not line_id or not gate:
        return
    used_by_line = G.graph.setdefault(
        "_paper_exit_coverage_used_gates", {}
    )
    used = used_by_line.setdefault(str(line_id), [])
    if gate not in used:
        used.append(str(gate))


def _aa_apply_initial_exit_coverage(
    G,
    node,
    batch,
    now,
    chosen_path,
    chosen_details,
):
    """Use an existing candidate to cover an unused same-line exit once."""
    line_id, source_type, _ = _parse_source_group_id(
        str(batch.get("source_group", ""))
    )
    if source_type not in _EXIT_COVERAGE_SOURCE_TYPES:
        return chosen_path, chosen_details, False
    targets = _same_line_exit_targets(G, line_id)
    if len(targets) <= 1 or not chosen_path:
        return chosen_path, chosen_details, False

    # The first A* result is already a valid candidate. Register it before
    # considering an unused exit, so the policy never replaces a route with
    # another copy of the same target.
    selected_target = str(chosen_path[-1])
    _register_exit_coverage_target(
        G, line_id, selected_target, "_aa_exit_coverage_used"
    )
    used = set(
        G.graph.get("_aa_exit_coverage_used", {}).get(str(line_id), [])
    )
    missing = [target for target in targets if target not in used]
    if not missing:
        return chosen_path, chosen_details, False

    alternatives = []
    for target in missing:
        path, cost, details = spr.time_dependent_astar(
            G,
            node,
            current_time=now,
            amount=int(batch.get("amount", 0)),
            predictive=True,
            target_exits=(target,),
        )
        if path and details and math.isfinite(float(cost)):
            alternatives.append((float(cost), str(target), path, details))
    if not alternatives:
        return chosen_path, chosen_details, False

    _, target, path, details = min(
        alternatives,
        key=lambda item: (item[0], len(item[2]), item[1]),
    )
    _register_exit_coverage_target(
        G, line_id, target, "_aa_exit_coverage_used"
    )
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    diagnostics["aa_initial_exit_coverage_override_count"] = int(
        diagnostics.get("aa_initial_exit_coverage_override_count", 0)
    ) + 1
    diagnostics["aa_initial_exit_coverage_override_people"] = int(
        diagnostics.get("aa_initial_exit_coverage_override_people", 0)
    ) + int(batch.get("amount", 0))
    diagnostics.setdefault("aa_initial_exit_coverage_overrides", []).append({
        "sim_time": float(now),
        "line_id": str(line_id),
        "source_group": str(batch.get("source_group", "")),
        "amount": int(batch.get("amount", 0)),
        "target_exit": target,
        "path": list(path),
    })
    return list(path), list(details), True


def _aa_step4b2_edge_allowed(
    G,
    decision_node,
    selected_first_hop,
    u,
    v,
):
    """Apply the accepted Step 4B-1 stage and branch scope to one edge."""
    if G[u][v].get("gate_switch_only"):
        return False
    if u == decision_node:
        return v == selected_first_hop
    if v == decision_node:
        return False

    # Once a first-hop branch is selected, a complete candidate may not enter
    # a different first-hop branch later in the same path.
    configured = set(_aa_active_replan_successors(G, decision_node))
    if v in configured and v != selected_first_hop:
        return False

    current_rank = int(G.nodes[u].get("evac_stage_rank", 0))
    successor_rank = int(G.nodes[v].get("evac_stage_rank", 0))
    if successor_rank < current_rank:
        return (
            G[u][v].get("aa_stage_transition")
            == "downstream_transfer_branch"
        )
    return True


def _aa_step4b2_path_respects_scope(
    G,
    decision_node,
    path,
    *,
    allowed_first_hops=None,
):
    """Validate a complete active-reroute path without executed-node history."""
    if not path or len(path) < 2 or path[0] != decision_node:
        return False
    if len(set(path)) != len(path):
        return False
    if any(
        not G.has_edge(u, v)
        for u, v in zip(path, path[1:])
    ):
        return False
    configured = set(_aa_active_replan_successors(G, decision_node))
    permitted = (
        set(allowed_first_hops)
        if allowed_first_hops is not None
        else configured
    )
    if path[1] not in configured or path[1] not in permitted:
        return False
    if path[-1] not in set(spr.allowed_exit_nodes(G)):
        return False
    return all(
        _aa_step4b2_edge_allowed(
            G,
            decision_node,
            path[1],
            u,
            v,
        )
        for u, v in zip(path, path[1:])
    )


def _aa_step4b2_concrete_alternative_path(
    G,
    decision_node,
    successor,
):
    """Return one static shortest complete path inside the Step 4B-1 scope."""
    cache = G.graph.setdefault("_aa_step4b2_concrete_path_cache", {})
    key = (decision_node, successor)
    if key not in cache:
        scoped_graph = nx.subgraph_view(
            G,
            filter_edge=lambda u, v: _aa_step4b2_edge_allowed(
                G,
                decision_node,
                successor,
                u,
                v,
            ),
        )
        candidates = []
        for exit_node in spr.allowed_exit_nodes(G):
            try:
                tail = nx.shortest_path(
                    scoped_graph,
                    successor,
                    exit_node,
                    weight="length",
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            path = [decision_node] + list(tail)
            if not _aa_step4b2_path_respects_scope(
                G,
                decision_node,
                path,
                allowed_first_hops={successor},
            ):
                continue
            length = sum(
                float(G[u][v].get("length", 0.0))
                for u, v in zip(path, path[1:])
            )
            candidates.append((length, str(exit_node), path))
        cache[key] = list(min(candidates)[2]) if candidates else []
    return list(cache[key])


def _is_gate_approach_node(G, node):
    if node not in G.nodes:
        return False
    data = G.nodes[node]
    return (
        data.get("type") in {"gate_approach", "queue_area"}
        or data.get("queue_for_gate") is not None
        or data.get("approach_for_gate") is not None
    )


def _gate_for_approach_node(G, node):
    if node not in G.nodes:
        return None
    data = G.nodes[node]
    return data.get("queue_for_gate") or data.get("approach_for_gate")


_GATE_REPLAN_REASON_COUNTERS = {
    "no_alternative_targets": "gate_replan_no_alternative_targets_count",
    "no_real_path": "gate_replan_no_real_path_count",
    "edge_filter_rejected": "gate_replan_edge_filter_rejected_count",
    "alternative_cost_infinite": "gate_replan_alternative_cost_infinite_count",
    "same_gate_result": "gate_replan_same_gate_result_count",
    "gain_below_threshold": "gate_replan_gain_below_threshold_count",
    "qualified_switch": "gate_replan_qualified_switch_count",
}


def _gate_approach_node_for_gate(G, gate):
    mapping = G.graph.get("gate_queue_area_nodes", {})
    if gate in mapping and mapping[gate] in G.nodes:
        return mapping[gate]
    for node, data in G.nodes(data=True):
        if _is_gate_approach_node(G, node) and _gate_for_approach_node(G, node) == gate:
            return node
    return None


def _path_length_m(G, path):
    if not path or len(path) < 2:
        return 0.0
    total = 0.0
    for u, v in zip(path, path[1:]):
        if not G.has_edge(u, v):
            return math.inf
        total += float(G[u][v].get("length", 0.0) or 0.0)
    return total


def _shortest_directed_path(G, source, target):
    if source not in G.nodes or target not in G.nodes:
        return []
    cache = G.graph.setdefault("_gate_directed_path_cache", {})
    key = (source, target)
    if key not in cache:
        try:
            cache[key] = list(nx.shortest_path(G, source, target, weight="length"))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            cache[key] = []
    return list(cache[key])


def _directed_gate_path(G, approach_node, target_gate):
    target_approach = _gate_approach_node_for_gate(G, target_gate)
    candidates = []
    if target_approach is not None:
        to_approach = _shortest_directed_path(G, approach_node, target_approach)
        to_gate = _shortest_directed_path(G, target_approach, target_gate)
        if to_approach and to_gate:
            candidates.append(to_approach + to_gate[1:])
    direct = _shortest_directed_path(G, approach_node, target_gate)
    if direct:
        candidates.append(direct)
    if not candidates:
        return []
    return min(candidates, key=lambda path: (_path_length_m(G, path), len(path)))


def _record_gate_replan_diagnostic(
    G,
    *,
    node,
    batch,
    now,
    current_gate,
    alternative_targets,
    directed_paths,
    stay_cost,
    best_cost=math.inf,
    best_path=None,
    gain=None,
    result,
):
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    counter = _GATE_REPLAN_REASON_COUNTERS.get(result)
    if counter is not None:
        diagnostics[counter] = int(diagnostics.get(counter, 0)) + 1
    if result == "qualified_switch":
        diagnostics["gate_approach_replan_accept_count"] = int(
            diagnostics.get("gate_approach_replan_accept_count", 0)
        ) + 1
    else:
        diagnostics["gate_approach_replan_rejected_count"] = int(
            diagnostics.get("gate_approach_replan_rejected_count", 0)
        ) + 1
    directed_path = next((path for path in directed_paths.values() if path), [])
    row = {
        "simulation_time": float(now),
        "gate_approach": node,
        "source_group": batch.get("source_group"),
        "passenger_count": int(batch.get("amount", 0)),
        "current_gate": current_gate,
        "alternative_gates": ";".join(map(str, alternative_targets or ())),
        "directed_path_exists": any(bool(path) for path in directed_paths.values()),
        "directed_path_nodes": " -> ".join(map(str, directed_path)),
        "found_alternative_path": " -> ".join(map(str, best_path or ())),
        "stay_cost": float(stay_cost) if math.isfinite(stay_cost) else math.inf,
        "best_alternative_cost": (
            float(best_cost) if math.isfinite(best_cost) else math.inf
        ),
        "gain_ratio": (
            float(gain)
            if gain is not None and math.isfinite(float(gain))
            else ""
        ),
        "no_switch_reason": result,
    }
    G.graph.setdefault("_aa_gate_replan_diagnostics", []).append(row)


def _build_gate_approach_connectivity_report(G):
    rows = []
    gate_to_approach = {
        _gate_for_approach_node(G, node): node
        for node, data in G.nodes(data=True)
        if _is_gate_approach_node(G, node)
    }
    for from_approach, data in sorted(G.nodes(data=True), key=lambda item: str(item[0])):
        if not _is_gate_approach_node(G, from_approach):
            continue
        current_gate = _gate_for_approach_node(G, from_approach)
        alternatives = tuple(
            data.get("aa_configured_alternative_target_resources", ())
            or data.get("aa_alternative_target_resources", ())
        )
        for target_gate in alternatives:
            to_approach = gate_to_approach.get(target_gate)
            if to_approach is None:
                path = []
            else:
                path = _shortest_directed_path(G, from_approach, to_approach)
            contains_stair_or_platform = any(
                str(G.nodes[node].get("type", "")).lower()
                in {"stair", "escalator", "platform", "platform_waiting_zone", "train"}
                for node in path
                if node in G.nodes
            )
            rows.append({
                "from_gate_approach": from_approach,
                "current_gate": current_gate,
                "to_gate": target_gate,
                "to_gate_approach": to_approach or "",
                "directed_path_exists": bool(path),
                "path_nodes": " -> ".join(map(str, path)),
                "path_length": (
                    _path_length_m(G, path) if path else ""
                ),
                "contains_stair_or_platform": contains_stair_or_platform,
                "contains_current_gate": (
                    current_gate in path[1:] if path else False
                ),
                "passes_target_gate": target_gate in path if path else False,
            })
    return rows


def _gate_switch_path_violates_upstream_return(G, decision_node, path):
    for node in list(path)[1:]:
        if node == decision_node:
            return True
        if node not in G.nodes:
            return True
        data = G.nodes[node]
        node_type = str(data.get("type", "")).lower()
        name = str(node).lower()
        if node_type in {"train", "train_car", "platform", "platform_waiting_zone"}:
            return True
        if name.startswith(("train_", "platform_")):
            return True
        if node_type in {"stair", "escalator"}:
            return True
    return False


def _gate_switch_path_target_gate(G, path, current_gate):
    for node in list(path)[1:]:
        if node == current_gate:
            return current_gate
        if node in G.nodes and spr.is_capacity_service_node(G, node):
            if "gate" in str(G.nodes[node].get("type", "")).lower():
                return node
    return None


def _aa_gate_switch_path_respects_scope(
    G,
    decision_node,
    path,
    alternative_targets,
):
    if not path or len(path) < 2 or path[0] != decision_node:
        return False
    if len(set(path)) != len(path):
        return False
    if any(not G.has_edge(u, v) for u, v in zip(path, path[1:])):
        return False
    if path[-1] not in set(spr.allowed_exit_nodes(G)):
        return False
    current_gate = G.nodes[decision_node].get("aa_current_gate")
    target_gate = _gate_switch_path_target_gate(G, path, current_gate)
    if target_gate is None or target_gate == current_gate:
        return False
    if target_gate not in set(alternative_targets or ()):
        return False
    target_approach = _gate_approach_node_for_gate(G, target_gate)
    traversed_approaches = [
        item
        for item in path[1:]
        if _is_gate_approach_node(G, item)
    ]
    if traversed_approaches != [target_approach]:
        return False
    for u, v in zip(path, path[1:]):
        if (
            u == decision_node
            and v == target_gate
            and float(G[u][v].get("length", 0.0) or 0.0) <= 1e-9
        ):
            G.graph.setdefault("_aa_diagnostics", {})[
                "teleport_switch_violation_count"
            ] = int(
                G.graph.setdefault("_aa_diagnostics", {}).get(
                    "teleport_switch_violation_count", 0
                )
            ) + 1
            return False
    if _gate_switch_path_violates_upstream_return(G, decision_node, path):
        G.graph.setdefault("_aa_diagnostics", {})[
            "return_to_stair_violation_count"
        ] = int(
            G.graph.setdefault("_aa_diagnostics", {}).get(
                "return_to_stair_violation_count", 0
            )
        ) + 1
        return False
    return True


def _aa_gate_switch_edge_allowed(
    G,
    decision_node,
    current_gate,
    alternative_targets,
    u,
    v,
):
    if v == decision_node:
        return False
    if v == current_gate:
        return False
    if _gate_switch_path_violates_upstream_return(G, decision_node, (u, v)):
        return False
    if spr.is_capacity_service_node(G, v) and "gate" in str(
        G.nodes[v].get("type", "")
    ).lower():
        return v in set(alternative_targets or ())
    return True


def _record_gate_switch_event(
    G,
    node,
    batch,
    now,
    current_gate,
    target_gate,
    stay_cost,
    best_cost,
    gain,
    first_hop,
    amount,
):
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    diagnostics["gate_switch_event_count"] = (
        int(diagnostics.get("gate_switch_event_count", 0)) + 1
    )
    minimum = diagnostics.get("minimum_gate_switch_gain")
    diagnostics["minimum_gate_switch_gain"] = (
        float(gain)
        if minimum is None
        else min(float(minimum), float(gain))
    )
    G.graph.setdefault("_aa_gate_switch_events", []).append({
        "simulation_time": float(now),
        "source_group": batch.get("source_group"),
        "current_gate": current_gate,
        "target_gate": target_gate,
        "passenger_count": int(amount),
        "stay_cost": float(stay_cost),
        "switch_cost": float(best_cost),
        "improvement_ratio": float(gain),
        "actual_first_hop": first_hop,
    })


def _gate_approach_replan_trigger(G, node, current_gate, path_details):
    """Return whether a waiting gate batch has a real congestion trigger."""
    density = spr.spatial_effective_density(G, node)
    predicted_wait = 0.0
    for detail in path_details or ():
        if detail.get("resource_id") != ("facility", current_gate):
            continue
        predicted_wait = max(
            predicted_wait,
            float(detail.get("predicted_wait", 0.0) or 0.0),
        )
    triggered = bool(
        density >= MODERATE_CONGESTION_DENSITY_THRESHOLD
        or predicted_wait > 0.0
    )
    return triggered, {
        "queue_density": float(density),
        "predicted_current_gate_wait": float(predicted_wait),
        "density_threshold": float(MODERATE_CONGESTION_DENSITY_THRESHOLD),
    }


def _l2_upstream_replan_trigger(G, node, old_path, path_details):
    """Detect congestion on the currently planned L2 release branch.

    This is deliberately evaluated only for the residual batch still at the
    upstream release node. It observes the existing resource queue, forecast
    wait, spatial density and last-step receiving rejection; it does not add a
    second capacity or congestion model.
    """
    first_hop = old_path[1] if len(old_path) >= 2 else None
    if first_hop is None or not G.has_edge(node, first_hop):
        return False, {
            "planned_first_hop": first_hop or "",
            "planned_resource_queue": 0.0,
            "planned_predicted_wait": 0.0,
            "planned_predicted_density": 0.0,
            "planned_receiving_blocked": False,
            "trigger_reasons": "invalid_current_path",
        }

    resource_id = edge_resource_id(G, node, first_hop)
    matching = [
        detail for detail in path_details or ()
        if detail.get("resource_id") == resource_id
    ]
    predicted_wait = max(
        (float(detail.get("predicted_wait", 0.0) or 0.0) for detail in matching),
        default=0.0,
    )
    predicted_queue = max(
        (float(detail.get("predicted_queue", 0.0) or 0.0) for detail in matching),
        default=0.0,
    )
    predicted_density = max(
        (
            float(
                detail.get(
                    "destination_predicted_density",
                    detail.get("predicted_density", 0.0),
                )
                or 0.0
            )
            for detail in matching
        ),
        default=0.0,
    )
    current_queue = max(float(spr.current_resource_queue(G, resource_id)), 0.0)
    current_density = max(
        float(spr.spatial_effective_density(G, first_hop)),
        0.0,
    )
    receiving_blocked = bool(
        float(
            G.graph.get("_current_spatial_blocked_sources", {}).get(node, 0.0)
        ) > 0.0
    )
    reasons = []
    if current_queue > 0.0:
        reasons.append("resource_queue")
    if predicted_queue > 0.0 or predicted_wait > 0.0:
        reasons.append("predicted_wait")
    if max(predicted_density, current_density) >= MODERATE_CONGESTION_DENSITY_THRESHOLD:
        reasons.append("density")
    if receiving_blocked:
        reasons.append("receiving_blockage")
    return bool(reasons), {
        "planned_first_hop": first_hop,
        "planned_resource_id": resource_id,
        "planned_resource_queue": current_queue,
        "planned_predicted_queue": predicted_queue,
        "planned_predicted_wait": predicted_wait,
        "planned_predicted_density": predicted_density,
        "planned_current_density": current_density,
        "planned_receiving_blocked": receiving_blocked,
        "trigger_reasons": ";".join(reasons),
    }


def _evaluate_aa_reroute_opportunity(
    G,
    node,
    batch,
    old_path,
    stay_cost,
    now,
    predictive,
    *,
    alternative_targets=None,
    configured_successors=None,
    selected_first_hops=None,
):
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    amount = int(batch.get("amount", 0))
    gain_min = float(G.graph.get("aa_reroute_gain_min", 0.0))
    switch_cost_limit = stay_cost * (1.0 - gain_min)
    configured_successors = set(
        configured_successors
        if configured_successors is not None
        else _aa_active_replan_successors(G, node)
    )
    selected_first_hops = set(selected_first_hops or ())
    current_gate = G.nodes[node].get("aa_current_gate")
    alternative_targets = tuple(alternative_targets or ())
    gate_mode = bool(alternative_targets or current_gate)
    directed_paths = (
        {
            target_gate: _directed_gate_path(G, node, target_gate)
            for target_gate in alternative_targets
        }
        if gate_mode else {}
    )
    directed_path_exists = any(bool(path) for path in directed_paths.values())

    if gate_mode:
        diagnostics["gate_approach_replan_evaluation_count"] = (
            int(diagnostics.get("gate_approach_replan_evaluation_count", 0)) + 1
        )
        alternative_successors = sorted(
            configured_successors - {old_path[1]},
            key=str,
        )
    else:
        alternative_successors = sorted(
            configured_successors - {old_path[1]} - selected_first_hops,
            key=str,
        )

    if gate_mode and not alternative_targets:
        diagnostics["gate_stay_people"] = (
            int(diagnostics.get("gate_stay_people", 0)) + amount
        )
        _record_gate_replan_diagnostic(
            G,
            node=node,
            batch=batch,
            now=now,
            current_gate=current_gate,
            alternative_targets=alternative_targets,
            directed_paths=directed_paths,
            stay_cost=stay_cost,
            result="no_alternative_targets",
        )
        return None

    if not alternative_successors:
        if gate_mode:
            diagnostics["gate_stay_people"] = (
                int(diagnostics.get("gate_stay_people", 0)) + amount
            )
            _record_gate_replan_diagnostic(
                G,
                node=node,
                batch=batch,
                now=now,
                current_gate=current_gate,
                alternative_targets=alternative_targets,
                directed_paths=directed_paths,
                stay_cost=stay_cost,
                result=(
                    "edge_filter_rejected"
                    if directed_path_exists else "no_real_path"
                ),
            )
        return None

    qualified = []
    gate_best_cost = math.inf
    gate_best_path = []
    gate_best_gain = None
    gate_seen_infinite = False
    gate_seen_same_gate = False
    gate_seen_filter_rejected = False
    gate_seen_below_threshold = False
    for alternative_successor in alternative_successors:
        lower_bound = spr.aa_one_step_objective_lower_bound(
            G,
            node,
            now,
            amount,
            predictive=predictive,
            allowed_successors={alternative_successor},
        )
        if (
            not math.isfinite(lower_bound)
            or lower_bound > switch_cost_limit
        ):
            diagnostics["alternative_lower_bound_pruned_count"] += 1
            if gate_mode:
                if not math.isfinite(lower_bound):
                    gate_seen_infinite = True
                else:
                    gate_seen_below_threshold = True
                    if lower_bound < gate_best_cost:
                        gate_best_cost = float(lower_bound)
                        gate_best_gain = (
                            (stay_cost - lower_bound) / stay_cost
                            if stay_cost > 0.0 else 0.0
                        )
            continue

        if gate_mode:
            def edge_allowed(u, v, _successor=alternative_successor):
                if u == node:
                    return v == _successor
                if _is_gate_approach_node(G, u):
                    return v == _gate_for_approach_node(G, u)
                if _is_gate_approach_node(G, v):
                    return (
                        _gate_for_approach_node(G, v)
                        in alternative_targets
                    )
                return _aa_gate_switch_edge_allowed(
                    G,
                    node,
                    current_gate,
                    alternative_targets,
                    u,
                    v,
                )

            best_path, best_cost, best_details = spr.time_dependent_astar(
                G,
                node,
                now,
                amount=amount,
                predictive=predictive,
                objective_cutoff=switch_cost_limit,
                edge_allowed=edge_allowed,
                allow_gate_switch_edges=True,
            )
            if (
                not best_path
                or not math.isfinite(best_cost)
            ):
                diagnostics["concrete_alternative_pruned_count"] += 1
                if not best_path:
                    gate_seen_below_threshold = directed_path_exists
                    gate_seen_filter_rejected = not directed_path_exists
                else:
                    gate_seen_infinite = True
                continue
            target_gate = _gate_switch_path_target_gate(
                G, best_path, current_gate
            )
            if best_cost < gate_best_cost:
                gate_best_cost = float(best_cost)
                gate_best_path = list(best_path)
                gate_best_gain = (
                    (stay_cost - best_cost) / stay_cost
                    if stay_cost > 0.0 else 0.0
                )
            if target_gate is None or target_gate == current_gate:
                gate_seen_same_gate = True
                diagnostics["concrete_alternative_pruned_count"] += 1
                continue
            if not _aa_gate_switch_path_respects_scope(
                G, node, best_path, alternative_targets
            ):
                gate_seen_filter_rejected = True
                diagnostics["concrete_alternative_pruned_count"] += 1
                continue
            qualified.append((
                float(best_cost),
                str(alternative_successor),
                alternative_successor,
                list(best_path),
                list(best_details),
                target_gate,
            ))
            continue

        concrete_path = _aa_step4b2_concrete_alternative_path(
            G,
            node,
            alternative_successor,
        )
        if not concrete_path:
            diagnostics["concrete_alternative_pruned_count"] += 1
            continue
        concrete_cost, concrete_details = (
            spr.evaluate_time_dependent_path(
                G,
                concrete_path,
                now,
                amount=amount,
            )
            if predictive
            else spr.evaluate_candidate_path_with_cumulative_eta(
                G,
                concrete_path,
                spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD,
                now,
                amount=amount,
            )
        )
        if (
            not math.isfinite(concrete_cost)
            or concrete_cost > switch_cost_limit
            or not _aa_step4b2_path_respects_scope(
                G,
                node,
                concrete_path,
                allowed_first_hops={alternative_successor},
            )
        ):
            diagnostics["concrete_alternative_pruned_count"] += 1
            continue
        qualified.append((
            float(concrete_cost),
            str(alternative_successor),
            alternative_successor,
            list(concrete_path),
            list(concrete_details),
            None,
        ))

    if not qualified:
        if gate_mode:
            diagnostics["gate_stay_people"] = (
                int(diagnostics.get("gate_stay_people", 0)) + amount
            )
            if not directed_path_exists:
                result = "no_real_path"
            elif gate_seen_filter_rejected:
                result = "edge_filter_rejected"
            elif gate_seen_infinite:
                result = "alternative_cost_infinite"
            elif gate_seen_same_gate:
                result = "same_gate_result"
            else:
                result = "gain_below_threshold"
            _record_gate_replan_diagnostic(
                G,
                node=node,
                batch=batch,
                now=now,
                current_gate=current_gate,
                alternative_targets=alternative_targets,
                directed_paths=directed_paths,
                stay_cost=stay_cost,
                best_cost=gate_best_cost,
                best_path=gate_best_path,
                gain=gate_best_gain,
                result=result,
            )
        return None

    (
        best_concrete_cost,
        _,
        best_concrete_successor,
        best_concrete_path,
        best_concrete_details,
        target_gate,
    ) = min(qualified)
    concrete_opportunity = (stay_cost - best_concrete_cost) / stay_cost
    opportunity_key = (
        node,
        tuple(sorted((str(old_path[1]), str(best_concrete_successor)))),
    )
    opportunity_best = batch.setdefault("step4b2_opportunity_best", {})
    previous_opportunity = opportunity_best.get(opportunity_key)
    if (
        previous_opportunity is not None
        and concrete_opportunity <= float(previous_opportunity) + 1e-12
    ):
        diagnostics["repeated_opportunity_pruned_count"] += 1
        if gate_mode:
            diagnostics["gate_stay_people"] = (
                int(diagnostics.get("gate_stay_people", 0)) + amount
            )
            _record_gate_replan_diagnostic(
                G,
                node=node,
                batch=batch,
                now=now,
                current_gate=current_gate,
                alternative_targets=alternative_targets,
                directed_paths=directed_paths,
                stay_cost=stay_cost,
                best_cost=best_concrete_cost,
                best_path=best_concrete_path,
                gain=concrete_opportunity,
                result="gain_below_threshold",
            )
        return None
    opportunity_best[opportunity_key] = float(concrete_opportunity)

    qualified_first_hops = {item[2] for item in qualified}
    if gate_mode:
        best_path, best_cost, best_details = (
            best_concrete_path,
            best_concrete_cost,
            best_concrete_details,
        )
        actual_gain = concrete_opportunity
        path_scope_valid = True
    else:
        def step4b2_edge_allowed(u, v):
            if u == node:
                return v in qualified_first_hops
            if v == node:
                return False
            if v in configured_successors:
                return False
            current_rank = int(G.nodes[u].get("evac_stage_rank", 0))
            successor_rank = int(G.nodes[v].get("evac_stage_rank", 0))
            if successor_rank < current_rank:
                return (
                    G[u][v].get("aa_stage_transition")
                    == "downstream_transfer_branch"
                )
            return True

        diagnostics["active_replan_astar_count"] += 1
        diagnostics["astar_call_count"] += 1
        astar_started = time.perf_counter()
        best_path, best_cost, best_details = spr.time_dependent_astar(
            G,
            node,
            now,
            amount=amount,
            predictive=predictive,
            objective_cutoff=switch_cost_limit,
            edge_allowed=step4b2_edge_allowed,
        )
        diagnostics["astar_runtime_seconds"] += time.perf_counter() - astar_started
        actual_gain = (
            (stay_cost - best_cost) / stay_cost
            if best_path and stay_cost > 0.0 and math.isfinite(best_cost)
            else 0.0
        )
        path_scope_valid = (
            _aa_step4b2_path_respects_scope(
                G,
                node,
                best_path,
                allowed_first_hops=qualified_first_hops,
            )
            if best_path else False
        )

    should_switch = bool(
        best_path
        and len(best_path) >= 2
        and best_path[1] != old_path[1]
        and (gate_mode or best_path[1] not in selected_first_hops)
        and path_scope_valid
        and best_cost < stay_cost
        and actual_gain >= gain_min
    )
    if not should_switch:
        diagnostics["astar_keep_old_path_count"] += 1
        if best_path and not path_scope_valid:
            diagnostics["stage_or_branch_rejected_astar_count"] += 1
        if gate_mode:
            diagnostics["gate_stay_people"] = (
                int(diagnostics.get("gate_stay_people", 0)) + amount
            )
            if not best_path or not directed_path_exists:
                result = "no_real_path"
            elif not path_scope_valid:
                result = "edge_filter_rejected"
            elif target_gate is None or target_gate == current_gate:
                result = "same_gate_result"
            else:
                result = "gain_below_threshold"
            _record_gate_replan_diagnostic(
                G,
                node=node,
                batch=batch,
                now=now,
                current_gate=current_gate,
                alternative_targets=alternative_targets,
                directed_paths=directed_paths,
                stay_cost=stay_cost,
                best_cost=best_cost,
                best_path=best_path,
                gain=actual_gain,
                result=result,
            )
        return None

    if gate_mode:
        _record_gate_replan_diagnostic(
            G,
            node=node,
            batch=batch,
            now=now,
            current_gate=current_gate,
            alternative_targets=alternative_targets,
            directed_paths=directed_paths,
            stay_cost=stay_cost,
            best_cost=best_cost,
            best_path=best_path,
            gain=actual_gain,
            result="qualified_switch",
        )
        _record_gate_switch_event(
            G,
            node,
            batch,
            now,
            current_gate,
            target_gate,
            stay_cost,
            best_cost,
            actual_gain,
            best_path[1],
            amount,
        )

    return {
        "path": list(best_path),
        "details": list(best_details),
        "cost": float(best_cost),
        "gain": float(actual_gain),
        "target_gate": target_gate,
        "qualified_first_hops": qualified_first_hops,
    }


def _integerize_aa_batch_requests(G, requests):
    sorted_requests = sorted(
        requests,
        key=lambda request: (
            edge_resource_id(G, request["u"], request["v"]),
            int(request.get("request_priority", 1)),
            float(request.get("queue_enter_time", request.get("arrival_time", 0.0)) or 0.0),
            float(request.get("arrival_time", 0.0)),
            str(request.get("batch_id", "")),
        ),
    )
    grouped = {}
    for request in sorted_requests:
        key = (request["u"], request["v"])
        grouped[key] = grouped.get(key, 0) + int(request["requested"])
    accepted_moves = _integerize_moves(
        G, [(u, v, amount) for (u, v), amount in grouped.items()]
    )
    remaining_by_edge = {(u, v): int(amount) for u, v, amount in accepted_moves}
    allocations = {}
    for request in sorted_requests:
        key = (request["u"], request["v"])
        accepted = min(int(request["requested"]), remaining_by_edge.get(key, 0))
        remaining_by_edge[key] = remaining_by_edge.get(key, 0) - accepted
        if request.get("precommitted_gate_service") and accepted < int(
            request["requested"]
        ):
            for batch in _ensure_node_aa_batches(G, request["u"]):
                if batch.get("batch_id") == request.get("batch_id"):
                    batch["service_committed"] = False
                    batch["precommit_pending"] = False
                    break
        if accepted > 0:
            item = dict(request)
            item["amount"] = accepted
            allocations.setdefault(key, []).append(item)
            if request.get("l2_platform_replan"):
                diagnostics = G.graph.setdefault("_aa_diagnostics", {})
                diagnostics["l2_platform_replan_accept_count"] = int(
                    diagnostics.get("l2_platform_replan_accept_count", 0)
                ) + 1
                diagnostics["l2_platform_rerouted_people"] = int(
                    diagnostics.get("l2_platform_rerouted_people", 0)
                ) + accepted
    G.graph["_aa_accepted_allocations"] = allocations
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    for edge_allocations in allocations.values():
        for allocation in edge_allocations:
            _finalize_l7_hall_decision_diagnostic(
                G,
                allocation.get("l7_hall_decision_row_index"),
                int(allocation.get("amount", 0)),
            )
            if not allocation.get("hall_gate_switch_decision"):
                continue
            accepted = int(allocation.get("amount", 0))
            if accepted <= 0:
                continue
            diagnostics["hall_gate_switch_executed_count"] = int(
                diagnostics.get("hall_gate_switch_executed_count", 0)
            ) + 1
            diagnostics["hall_gate_switch_executed_people"] = int(
                diagnostics.get("hall_gate_switch_executed_people", 0)
            ) + accepted
            diagnostics["aa_prediction_triggered_switch_count"] = int(
                diagnostics.get("aa_prediction_triggered_switch_count", 0)
            ) + 1
    return accepted_moves


def _aa_step_resource_capacity(G, resource_id, demand=0):
    """Return one shared integer capacity value for this AA time step."""
    capacities = G.graph.setdefault("_aa_step_resource_capacity", {})
    if resource_id not in capacities:
        capacities[resource_id] = resource_integer_capacity_for_step(
            G, resource_id, demand
        )
    return int(capacities[resource_id])


def _split_aa_route_trace(items, first_amount):
    first_amount = max(int(first_amount), 0)
    first = []
    rest = []
    remaining_first = first_amount
    for item in items or ():
        available = max(int(item.get("amount", 0)), 0)
        take = min(available, remaining_first)
        if take > 0:
            first.append({**item, "amount": take})
            remaining_first -= take
        if available > take:
            rest.append({**item, "amount": available - take})
    return first, rest


def _prepare_aa_gate_service_commitments(G, active_nodes, now):
    """Pre-lock FIFO Gate service before any Gate Approach comparison."""
    requests = []
    candidates_by_resource = {}
    for node in active_nodes:
        if not _is_gate_approach_node(G, node):
            continue
        gate = G.nodes[node].get("aa_current_gate") or _gate_for_approach_node(
            G, node
        )
        if gate not in G.nodes or not G.has_edge(node, gate):
            continue
        resource_id = edge_resource_id(G, node, gate)
        for batch in list(_ensure_node_aa_batches(G, node)):
            amount = int(batch.get("amount", 0))
            if amount <= 0 or batch.get("gate_switch_in_progress"):
                continue
            if batch.get("queue_enter_time") is None:
                batch["queue_enter_time"] = float(now)
            candidates_by_resource.setdefault(resource_id, []).append(
                (node, gate, batch)
            )

    committed_people = 0
    waiting_people = 0
    commit_events = 0
    for resource_id, candidates in candidates_by_resource.items():
        candidates.sort(
            key=lambda item: (
                float(item[2].get("queue_enter_time", now) or now),
                str(item[2].get("batch_id", "")),
            )
        )
        remaining_capacity = _aa_step_resource_capacity(
            G, resource_id, sum(int(item[2].get("amount", 0)) for item in candidates)
        )
        for node, gate, batch in candidates:
            amount = int(batch.get("amount", 0))
            committed = min(amount, max(remaining_capacity, 0))
            if committed > 0:
                committed_batch = copy.deepcopy(batch)
                waiting_batch = copy.deepcopy(batch)
                committed_batch["batch_id"] = _next_aa_batch_id(G)
                committed_batch["amount"] = committed
                committed_batch["current_node"] = node
                retained_path = list(batch.get("current_path") or [])
                retained_path_is_valid = (
                    len(retained_path) >= 2
                    and retained_path[0] == node
                    and retained_path[1] == gate
                    and all(
                        G.has_edge(u, v)
                        for u, v in zip(retained_path, retained_path[1:])
                    )
                )
                # Pre-commit only locks this step's Queue->Gate service.  The
                # accepted child must retain its downstream Gate->...->Exit
                # suffix; otherwise it arrives at the Gate with a one-node
                # path and may be unable to recover under post-Gate filters.
                committed_batch["current_path"] = (
                    retained_path
                    if retained_path_is_valid
                    else [node, gate]
                )
                committed_batch["waiting_resource"] = resource_id
                committed_batch["service_committed"] = True
                committed_batch["precommit_pending"] = True
                committed_trace, waiting_trace = _split_aa_route_trace(
                    batch.get("executed_route_batches", ()), committed
                )
                if "executed_route_batches" in batch:
                    committed_batch["executed_route_batches"] = committed_trace
                    waiting_batch["executed_route_batches"] = waiting_trace

                waiting_amount = amount - committed
                batches = _ensure_node_aa_batches(G, node)
                batch_index = batches.index(batch)
                replacement = [committed_batch]
                if waiting_amount > 0:
                    waiting_batch["amount"] = waiting_amount
                    waiting_batch["service_committed"] = False
                    waiting_batch["precommit_pending"] = False
                    replacement.append(waiting_batch)
                batches[batch_index:batch_index + 1] = replacement

                requests.append({
                    "u": node,
                    "v": gate,
                    "requested": committed,
                    "batch_id": committed_batch["batch_id"],
                    "source_group": committed_batch["source_group"],
                    "arrival_time": committed_batch["arrival_time"],
                    "current_path": list(committed_batch["current_path"]),
                    "waiting_resource": resource_id,
                    "queue_enter_time": committed_batch["queue_enter_time"],
                    "queued_for_gate": gate,
                    "path_predictions": [],
                    "rerouted_this_step": False,
                    "gate_approach_switch": None,
                    "precommitted_gate_service": True,
                    "request_priority": 0,
                })
                committed_people += committed
                commit_events += 1
                remaining_capacity -= committed
                amount = waiting_amount
            waiting_people += max(amount, 0)

    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    diagnostics["gate_approach_service_committed_people"] = int(
        diagnostics.get("gate_approach_service_committed_people", 0)
    ) + committed_people
    diagnostics["gate_approach_reroutable_waiting_people"] = int(
        diagnostics.get("gate_approach_reroutable_waiting_people", 0)
    ) + waiting_people
    diagnostics["gate_approach_service_commit_events"] = int(
        diagnostics.get("gate_approach_service_commit_events", 0)
    ) + commit_events
    return requests


def _set_aa_round_queue_adjustment(
    G,
    resource_id,
    value,
):
    adjustments = G.graph.setdefault(
        "_aa_round_queue_adjustment",
        {},
    )
    previous = float(adjustments.get(resource_id, 0.0))
    value = float(value)
    adjustments[resource_id] = value
    if value != previous:
        spr.note_queue_adjustment_changed(G, resource_id)


def _get_predictive_aa_step_moves(G, active_nodes, predictive=True):
    # Soft resource intentions used only by AA queue-cost prediction.
    G.graph["_aa_round_prediction_events"] = []
    G.graph["_aa_round_prediction_versions"] = {}
    G.graph["_aa_round_queue_adjustment"] = {}
    G.graph["_aa_queue_adjustment_versions"] = {}

    # Unaccepted planning requests are forbidden from creating hard spatial
    # reservations. Remove stale fields left by older implementations.
    G.graph.pop("_aa_round_spatial_events", None)
    G.graph.pop("_aa_round_spatial_events_by_node", None)
    G.graph.pop("_aa_round_spatial_event_times_by_node", None)

    G.graph.pop("_aa_transit_spatial_events_cache", None)
    G.graph.pop("_confirmed_resource_arrivals_cache", None)
    G.graph.pop("_aa_resource_event_indices_cache", None)
    requests = []
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    diagnostics.setdefault("path_decisions", 0)
    diagnostics.setdefault("reroute_count", 0)
    diagnostics.setdefault("effective_reroute_count", 0)
    diagnostics.setdefault("reverse_reroute_count", 0)
    diagnostics.setdefault("a_b_a_cycle_count", 0)
    diagnostics.setdefault("astar_call_count", 0)
    diagnostics.setdefault("old_path_evaluation_count", 0)
    diagnostics.setdefault("same_path_reuse_count", 0)
    diagnostics.setdefault("astar_cutoff_no_improvement_count", 0)
    diagnostics.setdefault("astar_runtime_seconds", 0.0)
    diagnostics.setdefault("old_path_evaluation_runtime_seconds", 0.0)
    diagnostics.setdefault("predicted_queue_query_count", 0)
    diagnostics.setdefault("predicted_queue_query_runtime_seconds", 0.0)
    diagnostics.setdefault("predicted_queue_scanned_event_count", 0)
    diagnostics.setdefault("predicted_queue_index_query_count", 0)
    diagnostics.setdefault("predicted_queue_fallback_linear_scan_count", 0)
    diagnostics.setdefault("spatial_index_query_count", 0)
    diagnostics.setdefault("spatial_fallback_linear_scan_count", 0)
    diagnostics.setdefault("max_active_batch_count", 0)
    diagnostics.setdefault("simulation_step_count", 0)
    diagnostics.setdefault("committed_replan_skip_count", 0)
    diagnostics.setdefault("committed_path_refresh_count", 0)
    diagnostics.setdefault("old_path_prediction_reuse_count", 0)
    diagnostics.setdefault("old_path_prediction_refresh_count", 0)
    diagnostics.setdefault("old_path_prediction_signature_miss_count", 0)
    diagnostics.setdefault("old_path_prediction_signature_miss_reasons", {})
    diagnostics.setdefault("infeasible_old_path_count", 0)
    diagnostics.setdefault("infeasible_path_astar_count", 0)
    diagnostics.setdefault("infeasible_path_recovery_count", 0)
    diagnostics.setdefault("infeasible_path_no_alternative_count", 0)
    diagnostics.setdefault("recovered_people_count", 0)
    diagnostics.setdefault("planned_selection_node_illegal_block_count", 0)
    diagnostics.setdefault("active_replan_astar_count", 0)
    diagnostics.setdefault("alternative_lower_bound_pruned_count", 0)
    diagnostics.setdefault("concrete_alternative_pruned_count", 0)
    diagnostics.setdefault("repeated_opportunity_pruned_count", 0)
    diagnostics.setdefault("astar_keep_old_path_count", 0)
    diagnostics.setdefault("first_hop_change_count", 0)
    diagnostics.setdefault("reroute_event_people_sum", 0)
    diagnostics.setdefault("unique_rerouted_people_count", 0)
    diagnostics.setdefault("plan_return_pruned_count", 0)
    diagnostics.setdefault("minimum_actual_reroute_gain", None)
    diagnostics.setdefault("stage_or_branch_rejected_astar_count", 0)
    diagnostics.setdefault("gate_approach_replan_evaluation_count", 0)
    diagnostics.setdefault("gate_approach_replan_accept_count", 0)
    diagnostics.setdefault("gate_approach_replan_rejected_count", 0)
    diagnostics.setdefault("gate_approach_replan_trigger_not_met_count", 0)
    diagnostics.setdefault("gate_approach_rerouted_people", 0)
    diagnostics.setdefault("gate_switch_event_count", 0)
    diagnostics.setdefault("gate_switch_people", 0)
    diagnostics.setdefault("gate_stay_people", 0)
    diagnostics.setdefault("minimum_gate_switch_gain", None)
    diagnostics.setdefault("gate_switch_matrix", {})
    diagnostics.setdefault("l2_platform_replan_trigger_count", 0)
    diagnostics.setdefault("l2_platform_replan_evaluation_count", 0)
    diagnostics.setdefault("l2_platform_replan_accept_count", 0)
    diagnostics.setdefault("l2_platform_rerouted_people", 0)
    diagnostics.setdefault("l2_platform_replan_gain_below_threshold_count", 0)
    diagnostics.setdefault("l2_platform_replan_not_triggered_count", 0)
    diagnostics.setdefault("return_to_stair_violation_count", 0)
    diagnostics.setdefault("teleport_switch_violation_count", 0)
    diagnostics.setdefault("accepted_but_not_transit_count", 0)
    diagnostics.setdefault("rejected_service_commitment_count", 0)
    diagnostics.setdefault("gate_replan_no_alternative_targets_count", 0)
    diagnostics.setdefault("gate_replan_no_real_path_count", 0)
    diagnostics.setdefault("gate_replan_edge_filter_rejected_count", 0)
    diagnostics.setdefault("gate_replan_alternative_cost_infinite_count", 0)
    diagnostics.setdefault("gate_replan_same_gate_result_count", 0)
    diagnostics.setdefault("gate_replan_gain_below_threshold_count", 0)
    diagnostics.setdefault("gate_replan_qualified_switch_count", 0)
    diagnostics.setdefault("hall_gate_switch_decision_count", 0)
    diagnostics.setdefault("hall_gate_switch_decision_people", 0)
    diagnostics.setdefault("hall_gate_switch_executed_count", 0)
    diagnostics.setdefault("hall_gate_switch_executed_people", 0)
    diagnostics.setdefault("gate_queue_replan_attempt_count", 0)
    diagnostics.setdefault("improved_density_triggered_switch_count", 0)
    diagnostics.setdefault("aa_prediction_triggered_switch_count", 0)
    diagnostics.setdefault("gate_approach_service_committed_people", 0)
    diagnostics.setdefault("gate_approach_reroutable_waiting_people", 0)
    diagnostics.setdefault("gate_approach_service_commit_events", 0)
    diagnostics.setdefault("aa_initial_exit_coverage_override_count", 0)
    diagnostics.setdefault("aa_initial_exit_coverage_override_people", 0)
    diagnostics.setdefault("aa_initial_exit_coverage_overrides", [])
    scope_diagnostics = G.graph.get("aa_replan_scope_diagnostics", {})
    diagnostics.setdefault(
        "replan_allowed_node_count",
        int(scope_diagnostics.get("replan_allowed_node_count", 0)),
    )
    diagnostics.setdefault(
        "replan_blocked_nondecision_node_count",
        int(scope_diagnostics.get(
            "replan_blocked_nondecision_node_count", 0
        )),
    )
    diagnostics.setdefault(
        "replan_blocked_upstream_stage_count",
        int(scope_diagnostics.get(
            "replan_blocked_upstream_stage_count", 0
        )),
    )
    diagnostics.setdefault(
        "replan_blocked_single_successor_count",
        int(scope_diagnostics.get(
            "replan_blocked_single_successor_count", 0
        )),
    )
    gain_min = float(G.graph.get("aa_reroute_gain_min", 0.0))
    now = float(G.graph.get("_sim_time", 0.0))
    if G.graph.get("_aa_step_capacity_time") != now:
        G.graph["_aa_step_capacity_time"] = now
        G.graph["_aa_step_resource_capacity"] = {}
    requests.extend(_prepare_aa_gate_service_commitments(G, active_nodes, now))

    batches = []
    for node in active_nodes:
        for batch in _ensure_node_aa_batches(G, node):
            if int(batch.get("amount", 0)) > 0:
                batches.append((node, batch))
    batches.sort(key=lambda item: (
        float(item[1].get("arrival_time", 0.0)),
        str(item[1].get("source_group", "")),
        str(item[0]),
        str(item[1].get("batch_id", "")),
    ))
    diagnostics["max_active_batch_count"] = max(
        int(diagnostics.get("max_active_batch_count", 0)),
        len(batches),
    )
    for node, batch in batches:
        if (
            bool(batch.get("service_committed", False))
            and _is_gate_approach_node(G, node)
            and batch.get("current_node", node) == node
        ):
            diagnostics["committed_replan_skip_count"] += 1
            continue
        stored_path = list(batch.get("current_path") or [])
        had_stored_path = bool(stored_path)
        old_path = list(stored_path)
        if (
            not old_path
            or old_path[0] != node
            or len(old_path) < 2
            or any(
                not G.has_edge(u, v)
                for u, v in zip(old_path, old_path[1:])
            )
            or (
                not bool(batch.get("gate_switch_in_progress", False))
                and any(
                    G[u][v].get("gate_switch_only")
                    for u, v in zip(old_path, old_path[1:])
                    if G.has_edge(u, v)
                )
            )
        ):
            old_path = []
        structurally_infeasible_old_path = had_stored_path and not old_path
        old_resource = batch.get("waiting_resource")
        amount = int(batch.get("amount", 0))
        queue_adjustment = G.graph["_aa_round_queue_adjustment"]
        if _is_gate_approach_node(G, node):
            current_gate = _gate_for_approach_node(G, node)
            batch["queued_for_gate"] = current_gate
            if batch.get("queue_enter_time") is None:
                batch["queue_enter_time"] = now
        if old_resource is not None:
            _set_aa_round_queue_adjustment(
                G,
                old_resource,
                queue_adjustment.get(old_resource, 0) - amount,
            )
        is_selection_stage = _is_explicit_aa_selection_stage(G, node)
        # Step 4A permits a complete search only for an initial decision or an
        # infeasible retained path. A feasible retained path never enters the
        # alternative-route search merely because costs or queues changed.
        may_replan = not old_path

        # A batch that is still physically located at the decision node was not
        # accepted into transit. It may therefore re-evaluate its route this step.
        #
        # Accepted people have already been removed from this node and stored in
        # _transit_queue, so allowing the remaining batch to replan cannot change
        # an accepted physical commitment.
        rerouted_this_step = False
        path_updated_this_step = False
        gate_approach_switch = None
        l2_platform_replan = False
        if may_replan and not old_path:
            diagnostics["astar_call_count"] += 1
            if structurally_infeasible_old_path:
                diagnostics["infeasible_old_path_count"] += 1
                diagnostics["infeasible_path_astar_count"] += 1
                if (
                    is_selection_stage
                    and batch.get("planned_selection_node") == node
                ):
                    diagnostics[
                        "planned_selection_node_illegal_block_count"
                    ] += 1
            if predictive:
                astar_started = time.perf_counter()
                best_path, best_cost, best_details = spr.time_dependent_astar(
                    G,
                    node,
                    now,
                    amount=amount,
                )
                diagnostics["astar_runtime_seconds"] += time.perf_counter() - astar_started
            else:
                astar_started = time.perf_counter()
                best_path, best_cost, best_details = spr.time_dependent_astar(
                    G,
                    node,
                    now,
                    amount=amount,
                    predictive=False,
                )
                diagnostics["astar_runtime_seconds"] += time.perf_counter() - astar_started
            if not best_path or len(best_path) < 2:
                if structurally_infeasible_old_path:
                    diagnostics["infeasible_path_no_alternative_count"] += 1
                if old_resource is not None:
                    _set_aa_round_queue_adjustment(
                        G,
                        old_resource,
                        queue_adjustment.get(old_resource, 0) + amount,
                    )
                continue
            if structurally_infeasible_old_path:
                diagnostics["infeasible_path_recovery_count"] += 1
                diagnostics["recovered_people_count"] += amount
            _record_step0_aa_candidate_diagnostics(
                G,
                node,
                batch,
                now,
                best_path,
            )
            chosen_path, chosen_details = best_path, best_details
            (
                chosen_path,
                chosen_details,
                _coverage_override,
            ) = _aa_apply_initial_exit_coverage(
                G,
                node,
                batch,
                now,
                chosen_path,
                chosen_details,
            )
        elif not may_replan:
            best_path, best_cost = old_path, math.inf
            path_signature = _aa_path_prediction_state_signature(
                G,
                old_path,
                amount,
                predictive,
            )
            can_reuse_prediction = (
                batch.get("path_prediction_signature") == path_signature
                and bool(batch.get("path_predictions"))
                and batch.get("path_prediction_time") is not None
            )
            miss_reason = None
            audit_signature_miss = bool(
                G.graph.get("aa_prediction_signature_audit", False)
            )
            if not can_reuse_prediction and audit_signature_miss:
                if not batch.get("path_predictions"):
                    miss_reason = "missing_predictions"
                elif batch.get("path_prediction_time") is None:
                    miss_reason = "missing_prediction_time"
                else:
                    miss_reason = _aa_path_prediction_miss_reason(
                        batch.get("path_prediction_signature"),
                        path_signature,
                    )
            if can_reuse_prediction:
                stay_cost, best_details = _aa_reuse_cached_path_prediction(
                    batch,
                    now,
                )
                if best_details:
                    diagnostics["same_path_reuse_count"] += 1
                    diagnostics["old_path_prediction_reuse_count"] += 1
                else:
                    can_reuse_prediction = False
                    miss_reason = "missing_prediction_cost"

            if not can_reuse_prediction:
                diagnostics["old_path_prediction_signature_miss_count"] += 1
                if audit_signature_miss:
                    miss_reasons = diagnostics.setdefault(
                        "old_path_prediction_signature_miss_reasons",
                        {},
                    )
                    miss_reason = miss_reason or "unknown"
                    miss_reasons[miss_reason] = int(
                        miss_reasons.get(miss_reason, 0)
                    ) + 1
                # Keep the committed route, but rebuild its forecast from the
                # current queue, spatial storage, density and risk state. This is
                # evaluation only: no alternative-route A* is called in this branch.
                diagnostics["old_path_evaluation_count"] += 1
                diagnostics["committed_path_refresh_count"] += 1
                diagnostics["old_path_prediction_refresh_count"] += 1
                if predictive:
                    evaluation_started = time.perf_counter()
                    stay_cost, best_details = spr.evaluate_time_dependent_path(
                        G,
                        old_path,
                        now,
                        amount=amount,
                    )
                    diagnostics["old_path_evaluation_runtime_seconds"] += (
                        time.perf_counter() - evaluation_started
                    )
                else:
                    stay_cost, best_details = spr.evaluate_candidate_path_with_cumulative_eta(
                        G,
                        old_path,
                        spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD,
                        now,
                        amount=amount,
                    )
                _aa_store_path_prediction_cache(
                    G,
                    batch,
                    old_path,
                    best_details,
                    amount,
                    predictive,
                    now,
                    cost=stay_cost,
                )
            chosen_path, chosen_details = old_path, best_details
            if not math.isfinite(stay_cost):
                diagnostics["infeasible_old_path_count"] += 1
                diagnostics["infeasible_path_astar_count"] += 1
                if (
                    is_selection_stage
                    and batch.get("planned_selection_node") == node
                ):
                    diagnostics[
                        "planned_selection_node_illegal_block_count"
                    ] += 1
                diagnostics["astar_call_count"] += 1
                astar_started = time.perf_counter()
                best_path, best_cost, best_details = spr.time_dependent_astar(
                    G,
                    node,
                    now,
                    amount=amount,
                    predictive=predictive,
                )
                diagnostics["astar_runtime_seconds"] += (
                    time.perf_counter() - astar_started
                )
                if best_path and len(best_path) >= 2 and math.isfinite(best_cost):
                    diagnostics["infeasible_path_recovery_count"] += 1
                    diagnostics["recovered_people_count"] += amount
                    chosen_path, chosen_details = best_path, best_details
                    path_updated_this_step = True
                    if best_path[1] != old_path[1]:
                        diagnostics["reroute_count"] += 1
                        rerouted_this_step = True
                        batch["previous_waiting_resource"] = old_resource
                        batch["queue_enter_time"] = now
                else:
                    diagnostics["infeasible_path_no_alternative_count"] += 1
            else:
                # Step 4B-2: a feasible retained route may actively change
                # only while its unaccepted batch is still at an approved
                # Step 4B-1 decision node.
                successor_groups = dict(
                    G.nodes[node].get(
                        "aa_replan_successor_groups", {}
                    )
                )
                configured_successors = {
                    successor
                    for successor in _aa_active_replan_successors(G, node)
                    if (
                        successor in successor_groups
                        and G.has_edge(node, successor)
                        and (
                            G[node][successor].get(
                                "aa_parallel_choice_group"
                            ) == successor_groups[successor]
                            or G[node][successor].get(
                                "aa_downstream_branch_group"
                            ) == successor_groups[successor]
                        )
                    )
                }
                active_replan_eligible = (
                    bool(G.nodes[node].get(
                        "aa_active_replan_allowed", False
                    ))
                    and not bool(G.nodes[node].get(
                        "aa_replan_return_blocked", False
                    ))
                    and not bool(batch.get(
                        "gate_switch_in_progress", False
                    ))
                    and not bool(batch.get(
                        "gate_switch_completed", False
                    ))
                    and batch.get("current_node", node) == node
                    and len(old_path) >= 2
                    and old_path[1] in configured_successors
                )
                if active_replan_eligible:
                    if batch.get("plan_history_node") != node:
                        batch["plan_history_node"] = node
                        batch["selected_first_hops"] = [
                            old_path[1]
                        ]
                        batch["step4b2_opportunity_best"] = {}
                    elif old_path[1] not in set(
                        batch.get("selected_first_hops") or ()
                    ):
                        batch.setdefault(
                            "selected_first_hops", []
                        ).append(old_path[1])
                selected_first_hops = (
                    set(batch.get("selected_first_hops") or ())
                    if active_replan_eligible
                    else set()
                )
                return_candidates = (
                    configured_successors
                    - {old_path[1]}
                ) & selected_first_hops
                diagnostics["plan_return_pruned_count"] += len(
                    return_candidates
                )
                alternative_successors = sorted(
                    configured_successors
                    - {old_path[1]}
                    - selected_first_hops,
                    key=str,
                )
                gate_alternative_targets = (
                    tuple(G.nodes[node].get("aa_alternative_target_resources") or ())
                    if _is_gate_approach_node(G, node)
                    else ()
                )
                gate_triggered = False
                gate_trigger_state = {}
                l2_release_node = bool(
                    G.nodes[node].get("aa_l2_upstream_release_node", False)
                )
                l2_triggered = False
                l2_trigger_state = {}
                if active_replan_eligible and l2_release_node:
                    l2_triggered, l2_trigger_state = (
                        _l2_upstream_replan_trigger(
                            G,
                            node,
                            old_path,
                            best_details,
                        )
                    )
                    if l2_triggered:
                        diagnostics["l2_platform_replan_trigger_count"] += 1
                if active_replan_eligible and gate_alternative_targets:
                    gate_triggered, gate_trigger_state = (
                        _gate_approach_replan_trigger(
                            G,
                            node,
                            G.nodes[node].get("aa_current_gate"),
                            best_details,
                        )
                    )
                if (
                    active_replan_eligible
                    and gate_alternative_targets
                    and gate_triggered
                ):
                    opportunity = _evaluate_aa_reroute_opportunity(
                        G,
                        node,
                        batch,
                        old_path,
                        stay_cost,
                        now,
                        predictive,
                        alternative_targets=gate_alternative_targets,
                        configured_successors=configured_successors,
                        selected_first_hops=selected_first_hops,
                    )
                    if opportunity is not None:
                        chosen_path = opportunity["path"]
                        chosen_details = opportunity["details"]
                        path_updated_this_step = True
                        rerouted_this_step = True
                        diagnostics["reroute_count"] += 1
                        diagnostics["first_hop_change_count"] += 1
                        diagnostics["reroute_event_people_sum"] += amount
                        if not bool(batch.get("has_rerouted", False)):
                            diagnostics["unique_rerouted_people_count"] += amount
                            batch["has_rerouted"] = True
                        batch.setdefault("selected_first_hops", []).append(
                            chosen_path[1]
                        )
                        minimum_gain = diagnostics.get(
                            "minimum_actual_reroute_gain"
                        )
                        diagnostics["minimum_actual_reroute_gain"] = (
                            float(opportunity["gain"])
                            if minimum_gain is None
                            else min(float(minimum_gain), float(opportunity["gain"]))
                        )
                        previous = batch.get("previous_waiting_resource")
                        new_resource = edge_resource_id(G, node, chosen_path[1])
                        if previous == new_resource:
                            diagnostics["reverse_reroute_count"] += 1
                            diagnostics["a_b_a_cycle_count"] += 1
                        batch["previous_waiting_resource"] = old_resource
                        batch["queue_enter_time"] = now
                        gate_approach_switch = {
                            "current_gate": G.nodes[node].get(
                                "aa_current_gate"
                            ),
                            "target_gate": opportunity.get("target_gate"),
                            "target_queue": _gate_approach_node_for_gate(
                                G, opportunity.get("target_gate")
                            ),
                            "gain": float(opportunity["gain"]),
                            **gate_trigger_state,
                        }
                elif active_replan_eligible and gate_alternative_targets:
                    diagnostics[
                        "gate_approach_replan_trigger_not_met_count"
                    ] += 1
                    diagnostics["gate_stay_people"] += amount
                elif (
                    active_replan_eligible
                    and l2_release_node
                    and not l2_triggered
                ):
                    if not l2_triggered:
                        diagnostics[
                            "l2_platform_replan_not_triggered_count"
                        ] += 1
                elif (
                    active_replan_eligible
                    and alternative_successors
                    and (not l2_release_node or l2_triggered)
                ):
                    if l2_release_node:
                        diagnostics[
                            "l2_platform_replan_evaluation_count"
                        ] += 1
                    switch_cost_limit = stay_cost * (1.0 - gain_min)
                    qualified = []
                    for alternative_successor in alternative_successors:
                        lower_bound = (
                            spr.aa_one_step_objective_lower_bound(
                                G,
                                node,
                                now,
                                amount,
                                predictive=predictive,
                                allowed_successors={
                                    alternative_successor
                                },
                            )
                        )
                        if (
                            not math.isfinite(lower_bound)
                            or lower_bound > switch_cost_limit
                        ):
                            diagnostics[
                                "alternative_lower_bound_pruned_count"
                            ] += 1
                            if (
                                l2_release_node
                                and l2_triggered
                                and math.isfinite(lower_bound)
                                and lower_bound > switch_cost_limit
                            ):
                                diagnostics[
                                    "l2_platform_replan_gain_below_threshold_count"
                                ] += 1
                            continue

                        concrete_path = (
                            _aa_step4b2_concrete_alternative_path(
                                G,
                                node,
                                alternative_successor,
                            )
                        )
                        if not concrete_path:
                            diagnostics[
                                "concrete_alternative_pruned_count"
                            ] += 1
                            continue
                        concrete_cost, concrete_details = (
                            spr.evaluate_time_dependent_path(
                                G,
                                concrete_path,
                                now,
                                amount=amount,
                            )
                            if predictive
                            else spr.evaluate_candidate_path_with_cumulative_eta(
                                G,
                                concrete_path,
                                spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD,
                                now,
                                amount=amount,
                            )
                        )
                        if (
                            not math.isfinite(concrete_cost)
                            or concrete_cost > switch_cost_limit
                            or not _aa_step4b2_path_respects_scope(
                                G,
                                node,
                                concrete_path,
                                allowed_first_hops={
                                    alternative_successor
                                },
                            )
                        ):
                            diagnostics[
                                "concrete_alternative_pruned_count"
                            ] += 1
                            continue
                        qualified.append((
                            float(concrete_cost),
                            str(alternative_successor),
                            alternative_successor,
                            list(concrete_path),
                            list(concrete_details),
                        ))

                    if qualified:
                        (
                            best_concrete_cost,
                            _,
                            best_concrete_successor,
                            best_concrete_path,
                            _best_concrete_details,
                        ) = min(qualified)
                        concrete_opportunity = (
                            stay_cost - best_concrete_cost
                        ) / stay_cost
                        opportunity_key = (
                            node,
                            tuple(sorted(
                                (
                                    str(old_path[1]),
                                    str(best_concrete_successor),
                                )
                            )),
                        )
                        opportunity_best = batch.setdefault(
                            "step4b2_opportunity_best", {}
                        )
                        previous_opportunity = opportunity_best.get(
                            opportunity_key
                        )
                        if (
                            previous_opportunity is not None
                            and concrete_opportunity
                            <= float(previous_opportunity) + 1e-12
                        ):
                            diagnostics[
                                "repeated_opportunity_pruned_count"
                            ] += 1
                        else:
                            opportunity_best[opportunity_key] = float(
                                concrete_opportunity
                            )
                            qualified_first_hops = {
                                item[2] for item in qualified
                            }

                            def step4b2_edge_allowed(u, v):
                                if u == node:
                                    return v in qualified_first_hops
                                if v == node:
                                    return False
                                if v in configured_successors:
                                    return False
                                current_rank = int(
                                    G.nodes[u].get("evac_stage_rank", 0)
                                )
                                successor_rank = int(
                                    G.nodes[v].get("evac_stage_rank", 0)
                                )
                                if successor_rank < current_rank:
                                    return (
                                        G[u][v].get(
                                            "aa_stage_transition"
                                        )
                                        == "downstream_transfer_branch"
                                    )
                                return True

                            diagnostics["active_replan_astar_count"] += 1
                            diagnostics["astar_call_count"] += 1
                            astar_started = time.perf_counter()
                            best_path, best_cost, best_details = (
                                spr.time_dependent_astar(
                                    G,
                                    node,
                                    now,
                                    amount=amount,
                                    predictive=predictive,
                                    objective_cutoff=switch_cost_limit,
                                    edge_allowed=step4b2_edge_allowed,
                                )
                            )
                            diagnostics["astar_runtime_seconds"] += (
                                time.perf_counter() - astar_started
                            )
                            actual_gain = (
                                (stay_cost - best_cost) / stay_cost
                                if (
                                    best_path
                                    and stay_cost > 0.0
                                    and math.isfinite(best_cost)
                                )
                                else 0.0
                            )
                            path_scope_valid = (
                                _aa_step4b2_path_respects_scope(
                                    G,
                                    node,
                                    best_path,
                                    allowed_first_hops=(
                                        qualified_first_hops
                                    ),
                                )
                                if best_path else False
                            )
                            should_switch = bool(
                                best_path
                                and len(best_path) >= 2
                                and best_path[1] != old_path[1]
                                and best_path[1] not in selected_first_hops
                                and path_scope_valid
                                and best_cost < stay_cost
                                and actual_gain >= gain_min
                            )
                            if should_switch:
                                chosen_path = best_path
                                chosen_details = best_details
                                path_updated_this_step = True
                                rerouted_this_step = True
                                l2_platform_replan = bool(
                                    l2_release_node and l2_triggered
                                )
                                diagnostics["reroute_count"] += 1
                                diagnostics[
                                    "first_hop_change_count"
                                ] += 1
                                diagnostics[
                                    "reroute_event_people_sum"
                                ] += amount
                                if not bool(batch.get(
                                    "has_rerouted", False
                                )):
                                    diagnostics[
                                        "unique_rerouted_people_count"
                                    ] += amount
                                    batch["has_rerouted"] = True
                                batch.setdefault(
                                    "selected_first_hops", []
                                ).append(best_path[1])
                                minimum_gain = diagnostics.get(
                                    "minimum_actual_reroute_gain"
                                )
                                diagnostics[
                                    "minimum_actual_reroute_gain"
                                ] = (
                                    float(actual_gain)
                                    if minimum_gain is None
                                    else min(
                                        float(minimum_gain),
                                        float(actual_gain),
                                    )
                                )
                                previous = batch.get(
                                    "previous_waiting_resource"
                                )
                                new_resource = edge_resource_id(
                                    G,
                                    node,
                                    best_path[1],
                                )
                                if previous == new_resource:
                                    diagnostics[
                                        "reverse_reroute_count"
                                    ] += 1
                                    diagnostics[
                                        "a_b_a_cycle_count"
                                    ] += 1
                                batch[
                                    "previous_waiting_resource"
                                ] = old_resource
                                batch["queue_enter_time"] = now
                                if node == "VN_L7_Hall_Arrival":
                                    diagnostics[
                                        "hall_gate_switch_decision_count"
                                    ] += 1
                                    diagnostics[
                                        "hall_gate_switch_decision_people"
                                    ] += amount
                                    batch["hall_gate_switch_decision"] = {
                                        "old_queue": old_path[1],
                                        "selected_queue": best_path[1],
                                        "old_cost": float(stay_cost),
                                        "new_cost": float(best_cost),
                                        "improvement_ratio": float(actual_gain),
                                    }
                            else:
                                diagnostics[
                                    "astar_keep_old_path_count"
                                ] += 1
                                if (
                                    l2_release_node
                                    and l2_triggered
                                    and best_path
                                    and math.isfinite(best_cost)
                                    and actual_gain < gain_min
                                ):
                                    diagnostics[
                                        "l2_platform_replan_gain_below_threshold_count"
                                    ] += 1
                                if best_path and not path_scope_valid:
                                    diagnostics[
                                        "stage_or_branch_rejected_astar_count"
                                    ] += 1
        if not old_path:
            if not structurally_infeasible_old_path:
                diagnostics["path_decisions"] += 1
            batch["queue_enter_time"] = now
            batch["planned_selection_node"] = node
            path_updated_this_step = True
        if may_replan and is_selection_stage:
            batch["planned_selection_node"] = node
        batch["current_path"] = list(chosen_path)
        batch["waiting_resource"] = edge_resource_id(G, node, chosen_path[1])
        _set_aa_round_queue_adjustment(
            G,
            batch["waiting_resource"],
            queue_adjustment.get(batch["waiting_resource"], 0) + amount,
        )
        # Newly selected or changed paths store their new forecast here.
        # Committed paths that were ineligible to replan were refreshed above
        # and retain that current-state forecast.
        if not old_path or path_updated_this_step:
            _aa_store_path_prediction_cache(
                G,
                batch,
                chosen_path,
                chosen_details,
                amount,
                predictive,
                now,
            )
        committed_predictions = list(batch.get("path_predictions") or chosen_details)
        first_prediction = committed_predictions[0] if committed_predictions else {}
        # The first resource is represented in the mutable current-round queue
        # above.  Only downstream resources are future arrival events.
        register_details = chosen_details[1:]
        if predictive:
            spr.register_round_prediction_events(
                G,
                register_details,
                int(batch["amount"]),
                batch["source_group"],
                batch["batch_id"],
            )
        if bool(batch.get("service_committed", False)):
            diagnostics["rejected_service_commitment_count"] = int(
                diagnostics.get("rejected_service_commitment_count", 0)
            ) + 1
        hall_decision_row_index = None
        if node == "VN_L7_Hall_Arrival":
            candidate_costs = {}
            candidate_paths = {}
            for queue_node in _aa_active_replan_successors(G, node):
                candidate_path = (
                    list(chosen_path)
                    if len(chosen_path) >= 2
                    and chosen_path[1] == queue_node
                    else _aa_step4b2_concrete_alternative_path(
                        G, node, queue_node
                    )
                )
                candidate_paths[queue_node] = list(candidate_path or [])
                if not candidate_path:
                    candidate_costs[queue_node] = float("inf")
                    continue
                candidate_cost, _ = (
                    spr.evaluate_time_dependent_path(
                        G,
                        candidate_path,
                        now,
                        amount=amount,
                    )
                    if predictive
                    else spr.evaluate_candidate_path_with_cumulative_eta(
                        G,
                        candidate_path,
                        spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD,
                        now,
                        amount=amount,
                    )
                )
                candidate_costs[queue_node] = float(candidate_cost)
            old_queue = old_path[1] if len(old_path) >= 2 else None
            selected_queue = chosen_path[1]
            old_cost = candidate_costs.get(old_queue, float("inf"))
            selected_cost = candidate_costs.get(
                selected_queue, float("inf")
            )
            improvement = (
                (old_cost - selected_cost) / old_cost
                if (
                    old_queue
                    and math.isfinite(old_cost)
                    and old_cost > 0.0
                    and math.isfinite(selected_cost)
                )
                else None
            )
            switched = bool(
                old_queue and old_queue != selected_queue
            )
            hall_decision_row_index = (
                _append_l7_hall_decision_diagnostic(
                    G,
                    method="AdaptiveQueueAwareAStar",
                    batch_id=batch["batch_id"],
                    batch_amount=int(batch["amount"]),
                    old_queue=old_queue,
                    selected_queue=selected_queue,
                    candidate_costs=candidate_costs,
                    candidate_paths=candidate_paths,
                    improvement_ratio=improvement,
                    decision_people=(
                        int(batch["amount"]) if switched else 0
                    ),
                )
            )
        requests.append({
            "u": node,
            "v": chosen_path[1],
            "requested": int(batch["amount"]),
            "batch_id": batch["batch_id"],
            "source_group": batch["source_group"],
            "arrival_time": batch["arrival_time"],
            "current_path": list(chosen_path),
            "waiting_resource": batch["waiting_resource"],
            "queue_enter_time": batch["queue_enter_time"],
            "queued_for_gate": batch.get("queued_for_gate"),
            "path_predictions": committed_predictions,
            "rerouted_this_step": rerouted_this_step,
            "l2_platform_replan": l2_platform_replan,
            "gate_approach_switch": gate_approach_switch,
            "hall_gate_switch_decision": (
                node == "VN_L7_Hall_Arrival"
                and bool(batch.get("hall_gate_switch_decision"))
                and rerouted_this_step
            ),
            "l7_hall_decision_row_index": hall_decision_row_index,
            "predicted_queue_at_entry": float(first_prediction.get("predicted_queue", 0.0)),
            "predicted_entry_time": float(first_prediction.get("resource_entry_time", now)),
        })
    return _integerize_aa_batch_requests(G, requests)


def get_step_moves(G, method, shortest_dists):
    method = _normalize_method(method)
    active_nodes = [
        n for n in G.nodes()
        if G.nodes[n].get("people", 0) > 0.1 and G.nodes[n].get("type") != "exit"
    ]

    moves = []

    fixed_next = G.graph.get("_fixed_next_by_node")
    if fixed_next:
        for u in active_nodes:
            v = fixed_next.get(u)
            if not v or not G.has_edge(u, v):
                continue
            flow = float(G.nodes[u]["people"])
            if flow > 0:
                moves.append((u, v, flow))
        return _integerize_moves(G, moves)

    if method == PAPER_SINGLE_PATH_METHOD:
        return _get_paper_step_moves(G, active_nodes)

    if method == OUR_SINGLE_PATH_METHOD:
        return _get_predictive_aa_step_moves(G, active_nodes)

    if method == spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD:
        return _get_predictive_aa_step_moves(G, active_nodes, predictive=False)

    if method in MESOSCOPIC_METHODS:
        return _get_mesoscopic_step_moves(G, active_nodes, shortest_dists, method)

    if method in OUR_SINGLE_PATH_FAMILY_METHODS:
        guidance_state = G.graph.setdefault("_our_guidance_state", {})
        for node in list(guidance_state):
            if node not in active_nodes:
                guidance_state.pop(node, None)

        # Parallel correction OFF — only the primary path is executed.
    # The original L2/L18 parallel facility logic has been removed.
    # To re-enable, uncomment the platform_local_parallel_path / l18_local_parallel_gate_path
    # block and restore L2_LOCAL_PARALLEL_VERTICALS / L18_LOCAL_PARALLEL_GATES.
        for u in active_nodes:
            path = _choose_our_single_path_with_inertia(G, u, shortest_dists, method)
            if path and len(path) > 1:
                v = path[1]
                flow = float(G.nodes[u]["people"])
                if flow > 0:
                    moves.append((u, v, flow))
        return _integerize_moves(G, moves)

    update_dynamic_weights(G, method)
    for u in active_nodes:
        moves.extend(get_split_next_moves(G, u, method, shortest_dists))

    return _integerize_moves(G, moves)


def _node_density(G, node):
    return spr.spatial_effective_density(G, node)


def _evaluation_node_physical_state(G, node):
    """Return (density, physical occupancy, abstract overflow queue).

    In high-load mode, queue nodes are reservoir abstractions: their ``people``
    count includes occupants inside the represented area plus the queue spilling
    into its upstream approach. Only the physical share belongs in density
    metrics; the remainder stays in queueing metrics.
    """
    if node not in G.nodes:
        return 0.0, 0.0, 0.0
    if not uses_spatial_storage(G, node):
        return 0.0, 0.0, 0.0
    data = G.nodes[node]
    effective_area = effective_node_area(G, node)
    people = max(float(data.get("people", 0.0)), 0.0)
    physical_people = people
    if _spillback_enabled(G) and _is_queue_node(G, node):
        jam_density = min(
            max(float(G.graph.get("receiving_jam_density", HIGH_LOAD_JAM_DENSITY_P_PER_M2)), 0.1),
            spr.PAPER_DENSITY_JAM,
        )
        physical_people = min(people, effective_area * jam_density)
    overflow_queue = max(people - physical_people, 0.0)
    return physical_people / effective_area, physical_people, overflow_queue


def _evaluation_node_density(G, node):
    """Method-independent physical density used only for evaluation."""
    density, _, _ = _evaluation_node_physical_state(G, node)
    return density


def _node_congestion_index(G, node):
    return spr.node_congestion_index(G, node)


def _congestion_thresholds_for_measure(measure_type):
    if measure_type == "resource_queue":
        return float("inf"), float("inf")
    return MODERATE_CONGESTION_DENSITY_THRESHOLD, SEVERE_CONGESTION_DENSITY_THRESHOLD


def _gate_backlog_record_id(record, fallback):
    for key in ("batch_id", "cohort_id", "person_id"):
        if record.get(key) is not None:
            return (key, str(record[key]))
    return ("aggregate",) + tuple(map(str, fallback))


def gate_service_backlog_state(G, gate, consumer=None):
    """Rebuild current Gate stock plus direct-upstream blocked stock."""
    if gate not in G.nodes or not is_point_service_resource(G, gate):
        return {
            "gate_node_waiting_people": 0.0,
            "upstream_blocked_people": 0.0,
            "backlog_people": 0.0,
            "overlap_people": 0.0,
        }
    fixture = G.graph.get("_gate_backlog_test_records")
    if fixture is not None:
        node_records = list(fixture.get("gate", {}).get(gate, ()))
        upstream_records = list(fixture.get("upstream", {}).get(gate, ()))
    else:
        node_records = [
            {"batch_id": b.get("batch_id"), "amount": b.get("amount", 0)}
            for b in G.nodes[gate].get("_aa_batches", ())
            if float(b.get("amount", 0)) > 0
        ]
        if not node_records:
            node_records = [
                {"source_group": group, "amount": amount}
                for group, amount in G.nodes[gate].get(
                    "source_group_dict", {}
                ).items()
                if float(amount) > 0
            ]
        if not node_records and float(G.nodes[gate].get("people", 0)) > 0:
            node_records = [{
                "source_group": "unattributed",
                "amount": G.nodes[gate].get("people", 0),
            }]
        upstream_records = []
        rejected_sources = G.graph.get(
            "_current_gate_upstream_spillback_sources", {}
        ).get(gate, {})
        for source, rejected in rejected_sources.items():
            if not G.has_edge(source, gate):
                continue
            if (
                G.graph.get("_active_simulation_method")
                == PAPER_SINGLE_PATH_METHOD
                and G.graph.get("_paper_fixed_next_by_node", {}).get(source)
                != gate
            ):
                continue
            remaining = min(
                max(float(rejected), 0.0),
                max(float(G.nodes[source].get("people", 0.0)), 0.0),
            )
            for batch in G.nodes[source].get("_aa_batches", ()):
                path = list(batch.get("current_path") or ())
                amount = min(max(float(batch.get("amount", 0)), 0.0), remaining)
                if amount <= 0 or len(path) < 2 or path[:2] != [source, gate]:
                    continue
                upstream_records.append({
                    "batch_id": batch.get("batch_id"),
                    "amount": amount,
                    "source": source,
                })
                remaining -= amount
            if remaining > 0:
                upstream_records.append({
                    "source_group": "aggregate",
                    "amount": remaining,
                    "source": source,
                })

    def collapse(records, location):
        totals = {}
        for index, record in enumerate(records):
            identity = _gate_backlog_record_id(
                record,
                (location, gate, record.get("source", gate),
                 record.get("source_group", "unknown"), index),
            )
            totals[identity] = max(
                totals.get(identity, 0.0),
                max(float(record.get("amount", 0.0)), 0.0),
            )
        return totals

    node_totals = collapse(node_records, "gate")
    upstream_totals = collapse(upstream_records, "upstream")
    overlap_ids = set(node_totals) & set(upstream_totals)
    overlap = sum(
        min(node_totals[key], upstream_totals[key]) for key in overlap_ids
    )
    node_people = sum(node_totals.values())
    upstream_people = sum(
        amount for key, amount in upstream_totals.items()
        if key not in overlap_ids
    )
    backlog_people = node_people + upstream_people
    stat = G.graph.setdefault("_gate_backlog_diagnostics", {}).setdefault(
        gate, {}
    )
    stat.update({
        "gate_node_waiting_people": node_people,
        "gate_node_occupancy_people": node_people,
        "gate_upstream_blocked_people": upstream_people,
        "gate_spillback_queue_people": upstream_people,
        "gate_service_backlog_people": backlog_people,
        "gate_backlog_overlap_people": overlap,
    })
    physical_node_people = max(float(G.nodes[gate].get("people", 0.0)), 0.0)
    mismatch = (
        overlap > 1e-9
        or abs(node_people - physical_node_people) > 1e-9
    )
    stat["gate_backlog_mismatch_count"] = int(
        stat.get("gate_backlog_mismatch_count", 0)
    ) + int(mismatch)
    if consumer is None and G.graph.get(
        "_active_simulation_method"
    ) == OUR_SINGLE_PATH_METHOD:
        consumer = "aa"
    routing_queue = (
        spr.physical_resource_queue(G, ("facility", gate))
        if hasattr(spr, "physical_resource_queue")
        else float(
            G.graph.get("_resource_queues", {}).get(("facility", gate), 0.0)
        )
    )
    stat["gate_routing_queue_people"] = routing_queue
    if consumer == "improved":
        stat["improved_queue_q_used"] = routing_queue
    elif consumer == "aa":
        stat["aa_queue_q_used"] = routing_queue
    return {
        "gate_node_waiting_people": node_people,
        "upstream_blocked_people": upstream_people,
        "backlog_people": backlog_people,
        "overlap_people": overlap,
    }


def _paper_gate_effective_state(G, node):
    """Return Improved's gate density and routing queue state."""
    node_people = max(float(G.nodes[node].get("people", 0.0)), 0.0)
    queue_node = G.graph.get("gate_queue_area_nodes", {}).get(node)
    queue_area_people = (
        max(float(G.nodes[queue_node].get("people", 0.0)), 0.0)
        if queue_node in G.nodes
        else 0.0
    )
    backlog = gate_service_backlog_state(G, node, consumer="improved")
    resource_id = ("facility", node)
    service_request = (
        spr.physical_resource_queue(G, resource_id)
        if hasattr(spr, "physical_resource_queue")
        else float(G.graph.get("_resource_queues", {}).get(resource_id, 0.0))
    )
    upstream_excluded = backlog["upstream_blocked_people"]
    # Route cost Q is the upstream queue waiting for this Gate's service
    # capacity. It is not a spatial density term. Spatial density uses the
    # physical gate queue area when one exists. Gate and Queue are separate
    # physical locations, so a route is blocked by the more crowded of the
    # two footprints rather than by their sum divided by one area.
    queue_people = service_request
    effective_people = node_people + queue_area_people
    queue_area = (
        max(float(effective_node_area(G, queue_node)), 0.1)
        if queue_node in G.nodes
        else max(float(effective_node_area(G, node)), 0.1)
    )
    # A configured Queue mapping is the authoritative physical footprint for
    # both sides of the Gate service buffer, including small routing-only test
    # graphs that do not set the formal storage mode explicitly.
    gate_area = queue_area
    gate_density = node_people / gate_area
    queue_density = queue_area_people / queue_area
    effective_area = queue_area if queue_node in G.nodes else gate_area
    effective_density = max(gate_density, queue_density)
    threshold = MODERATE_CONGESTION_DENSITY_THRESHOLD
    exceeded = effective_density > threshold
    density_diag = G.graph.setdefault(
        "_improved_gate_density_diagnostics", {}
    )
    stat = density_diag.setdefault(node, {})
    stat["improved_gate_density_actual_people"] = (
        float(stat.get("improved_gate_density_actual_people", 0.0))
        + node_people
    )
    stat["improved_gate_density_upstream_excluded_people"] = (
        float(
            stat.get(
                "improved_gate_density_upstream_excluded_people", 0.0
            )
        )
        + upstream_excluded
    )
    stat.setdefault("improved_gate_density_duplicate_count", 0)
    stat["maximum_actual_gate_people"] = max(
        float(stat.get("maximum_actual_gate_people", 0.0)),
        node_people,
    )
    stat["maximum_gate_density"] = max(
        float(stat.get("maximum_gate_density", 0.0)),
        gate_density,
    )
    stat["improved_gate_density_queue_area_people"] = (
        float(stat.get("improved_gate_density_queue_area_people", 0.0))
        + queue_area_people
    )
    stat["maximum_queue_area_people"] = max(
        float(stat.get("maximum_queue_area_people", 0.0)),
        queue_area_people,
    )
    stat["maximum_queue_density"] = max(
        float(stat.get("maximum_queue_density", 0.0)),
        queue_density,
    )
    stat["maximum_upstream_excluded_people"] = max(
        float(stat.get("maximum_upstream_excluded_people", 0.0)),
        upstream_excluded,
    )
    stat["improved_gate_routing_queue_people"] = (
        float(stat.get("improved_gate_routing_queue_people", 0.0))
        + queue_people
    )
    stat["maximum_routing_queue_people"] = max(
        float(stat.get("maximum_routing_queue_people", 0.0)),
        queue_people,
    )
    return {
        "node_people": node_people,
        "service_queue": service_request,
        "upstream_queue": upstream_excluded,
        "gate_node_occupancy": node_people,
        "queue_area_occupancy": queue_area_people,
        "gate_spillback_queue": upstream_excluded,
        "queue_people": queue_people,
        "effective_people": effective_people,
        "effective_area": effective_area,
        "gate_effective_area": gate_area,
        "queue_effective_area": queue_area,
        "gate_density": gate_density,
        "queue_density": queue_density,
        "density_basis": "max(gate_density,queue_density)",
        "effective_area_source": (
            G.nodes[queue_node].get("area_source", "queue_area")
            if queue_node in G.nodes
            else G.nodes[node].get("area_source", "gate_node")
        ),
        "effective_density": effective_density,
        "threshold": threshold,
        "exceeded": exceeded,
    }


def _log_paper_gate_state(G, node, state):
    """Emit bounded Improved gate-density diagnostics.

    Log the initial state, the first threshold exceedance, and one snapshot per
    100 simulated seconds. This keeps Mode 4 logs readable without changing
    routing or physical execution.
    """
    now = float(G.graph.get("_sim_time", 0.0))
    time_bin = int(now // 100.0)
    log_state = G.graph.setdefault("_paper_gate_density_log_state", {})
    previous = log_state.setdefault(
        node,
        {"last_time_bin": None, "ever_exceeded": False},
    )
    first_exceedance = bool(state["exceeded"] and not previous["ever_exceeded"])
    periodic_snapshot = previous["last_time_bin"] != time_bin
    if not (periodic_snapshot or first_exceedance):
        return

    previous["last_time_bin"] = time_bin
    previous["ever_exceeded"] = bool(
        previous["ever_exceeded"] or state["exceeded"]
    )
    message = (
        f"ImprovedGateDensity time={now:.1f}s"
        f" gate={node}"
        f" node_people={state['node_people']:.0f}"
        f" routing_queue={state['queue_people']:.0f}"
        f" effective_density={state['effective_density']:.3f}"
        f" threshold_exceeded={str(bool(state['exceeded'])).lower()}"
        f" removed={str(bool(state['exceeded'])).lower()}"
    )
    print(message, flush=True)
    run_log_path = G.graph.get("_run_log_path")
    if run_log_path:
        with open(run_log_path, "a", encoding="utf-8") as log_handle:
            log_handle.write(message + "\n")


_PAPER_TARGET_GATE_DIRECTIONS = {
    "Gate_L18_E1": ("L18_gate", "Exit_L18_12"),
    "Gate_L18_E2": ("L18_gate", "Exit_L18_13"),
    "Gate_L18_S1": ("L18_gate", "Exit_L18_17"),
    "Gate_L18_S2": ("L18_gate", "Exit_L18_17"),
    "Gate_L2_N_West": ("L2_exit_direction", "Exit_L2_2"),
    "Gate_L2_N_East": ("L2_exit_direction", "Exit_L2_6"),
    "Gate_L2_S_West": ("L2_exit_direction", "Exit_L2_4"),
    "Gate_L2_S_East": ("L2_exit_direction", "Exit_L2_3"),
}


def _crossline_source_line_id(G, node):
    """Infer the physical line that owns a transfer entry node."""
    name = str(node)
    normalized = name.replace("-", "_")

    def line_token(token):
        token = str(token).strip("_")
        if token in ALL_LINE_IDS:
            return token
        if token.isdigit() and f"L{token}" in ALL_LINE_IDS:
            return f"L{token}"
        return ""

    # For directional names such as VN_L16_to_Maglev, the first line is the
    # source line.  Do this before graph-neighbour inference, because a node
    # name can contain both the source and target line identifiers.
    if normalized.startswith("VN_"):
        direction = normalized[3:]
        for marker in ("_to_", "to"):
            if marker in direction:
                source = line_token(direction.split(marker, 1)[0])
                if source:
                    return source
    if normalized.startswith("Transfer_"):
        source = line_token(normalized.split("_", 2)[1])
        if source:
            return source

    configured = _routing_node_line_id(G, node)
    if configured:
        return configured
    for line_id in ("L18", "L16", "L7", "L2", "Maglev"):
        if line_id in name:
            return line_id
    return ""


def _first_crossline_target_gates(G, start, queue_to_gate):
    """Find first target Gate facilities reachable from a transfer entry."""
    if start not in G.nodes:
        return set()
    found = set()
    frontier = [start]
    visited = set()
    while frontier:
        node = frontier.pop(0)
        if node in visited:
            continue
        visited.add(node)
        gate = queue_to_gate.get(node)
        node_type = str(G.nodes[node].get("type", "")).lower()
        if gate:
            found.add(gate)
            continue
        if node_type.startswith("gate") or str(node).startswith("Gate_"):
            found.add(str(node).removesuffix("_Queue"))
            continue
        for successor in G.successors(node):
            if G[node][successor].get("gate_switch_only"):
                continue
            if successor not in visited:
                frontier.append(successor)
    return {gate for gate in found if gate in G.nodes}


def _crossline_target_line_hint(u, v, source_line=""):
    """Infer a target line from a transfer edge name when available."""
    normalized = f"{u}_{v}".replace("-", "_").replace("to", "_")
    numeric_lines = {"2": "L2", "7": "L7", "16": "L16", "18": "L18"}
    candidates = []
    for token in normalized.split("_"):
        if token in ALL_LINE_IDS:
            candidates.append(token)
        elif token in numeric_lines:
            candidates.append(numeric_lines[token])
    for candidate in reversed(candidates):
        if candidate != source_line:
            return candidate
    return ""


def _improved_ordinary_crossline_controls(G, gate_states, queue_to_gate):
    """Build one density/backlog admission policy for every transfer branch."""
    controls = []
    for u, v, data in G.edges(data=True):
        edge_type = str(data.get("edge_type", "")).lower()
        if "transfer" not in edge_type or data.get("gate_switch_only"):
            continue
        entry_name = str(u).lower()
        target_name = str(v).lower()
        # Apply admission policy at a real cross-line entry only.  An
        # Arrival -> Entrance edge can be an internal continuation of a
        # branch that people have already entered; treating it as a new
        # admission point can deadlock those committed passengers.
        if not (
            "entrance" in entry_name
            or str(u).startswith("Platform_")
        ):
            continue
        source_line = _crossline_source_line_id(G, u)
        if not source_line:
            continue
        target_line_hint = _crossline_target_line_hint(u, v, source_line)
        target_gates = _first_crossline_target_gates(G, v, queue_to_gate)
        target_gates = {
            gate for gate in target_gates
            if not str(gate).startswith(f"Gate_{source_line}_")
            and (
                not target_line_hint
                or str(gate).startswith(f"Gate_{target_line_hint}_")
            )
        }
        if not target_gates:
            continue
        by_target_line = {}
        for gate in target_gates:
            target_line = _crossline_source_line_id(G, gate)
            if not target_line or target_line == source_line:
                continue
            by_target_line.setdefault(target_line, set()).add(gate)
        for target_line, gates in sorted(by_target_line.items()):
            source_states = [
                state for gate, state in gate_states.items()
                if str(gate).startswith(f"Gate_{source_line}_")
            ]
            eligible = {
                gate for gate in gates
                if float(gate_states.get(gate, {}).get(
                    "effective_density", float("inf")
                )) <= spr.PAPER_HIGH_DENSITY_THRESHOLD
                and float(gate_states.get(gate, {}).get(
                    "service_queue", float("inf")
                )) <= resource_capacity_per_second(
                    G, ("facility", gate)
                ) * float(G.graph.get("delta_t", DELTA_T))
            }
            control = {
                "entry_edge": (u, v),
                "source_line": source_line,
                "target_line": target_line,
                "target_gates": tuple(sorted(gates)),
                "eligible_target_gates": tuple(sorted(eligible)),
                "blocked_target_gates": tuple(sorted(gates - eligible)),
                "source_all_congested": bool(source_states) and all(
                    float(state.get("effective_density", 0.0))
                    > spr.PAPER_HIGH_DENSITY_THRESHOLD
                    for state in source_states
                ),
            }
            control["allowed"] = bool(
                control["source_all_congested"] and eligible
            )
            controls.append(control)
    return controls


def _paper_refresh_temporary_high_cost_weights(G):
    """Refresh Improved ``sim_weight`` from the current step only."""
    now = float(G.graph.get("_sim_time", 0.0))
    gate_states = {}
    for node, data in G.nodes(data=True):
        node_type = str(data.get("type", "")).strip().lower()
        if node_type.startswith("gate") or "gate" in node_type:
            state = _paper_gate_effective_state(G, node)
            gate_states[node] = state
            _log_paper_gate_state(G, node, state)

    queue_to_gate = {
        queue: gate
        for gate, queue in G.graph.get("gate_queue_area_nodes", {}).items()
    }
    # A crowded queue must stop accepting new upstream arrivals, but people
    # already inside that queue still need the physical Queue -> Gate service
    # edge to drain.  Its actual throughput is governed by the shared gate
    # resource; treating this service edge as a walking path creates a deadlock
    # because the queue can never fall back below the density threshold.
    gate_service_edges = {
        (queue, gate)
        for queue, gate in queue_to_gate.items()
        if G.has_edge(queue, gate)
    }
    crossline_controls = _improved_ordinary_crossline_controls(
        G, gate_states, queue_to_gate
    )
    controls_by_edge = {}
    for control in crossline_controls:
        controls_by_edge.setdefault(control["entry_edge"], []).append(control)
    blocked_crossline_target_gates = {
        gate
        for control in crossline_controls
        for gate in control["blocked_target_gates"]
    }
    crossline_entry_edge = (
        "VN_7to2_Entrance",
        "Transfer_L7-L2_Z",
    )
    l7_control = next(
        (
            control for control in crossline_controls
            if control["entry_edge"] == crossline_entry_edge
            and control["target_line"] == "L2"
        ),
        None,
    )
    l2_receiving_candidates = {
        gate: gate_states[gate]
        for gate in (l7_control or {}).get("eligible_target_gates", ())
        if gate in gate_states
    }
    l2_blocked_target_gates = set(
        (l7_control or {}).get("blocked_target_gates", ())
    )
    crossline_allowed = bool((l7_control or {}).get("allowed", False))
    G.graph["_improved_ordinary_crossline_controls"] = crossline_controls
    G.graph["_improved_ordinary_crossline_active_edges"] = tuple(
        sorted(
            control["entry_edge"]
            for control in crossline_controls
            if not control["allowed"]
        )
    )
    G.graph["_improved_ordinary_crossline_blocked_target_gates"] = tuple(
        sorted(blocked_crossline_target_gates)
    )
    G.graph["_improved_ordinary_l7_crossline_edge"] = crossline_entry_edge
    G.graph["_improved_ordinary_l7_crossline_allowed"] = crossline_allowed
    G.graph["_improved_ordinary_l7_crossline_target_gates"] = tuple(
        sorted(l2_receiving_candidates)
    )
    G.graph["_improved_ordinary_l7_crossline_blocked_target_gates"] = tuple(
        sorted(l2_blocked_target_gates)
    )
    G.graph["_improved_ordinary_l7_crossline_blocked"] = (
        G.has_edge(*crossline_entry_edge) and not crossline_allowed
    )

    current_active = set()
    control_densities = {}
    normal_costs = {}
    for u, v, data in G.edges(data=True):
        # Gate-approach lateral links belong exclusively to AA's explicit
        # reroute decision.  The Improved baseline must never make them
        # traversable by overwriting the infinity assigned by the normal
        # dynamic-weight updater.
        if data.get("gate_switch_only"):
            edge = (u, v)
            data["sim_weight"] = float("inf")
            control_densities[edge] = float("inf")
            normal_costs[edge] = float("inf")
            continue
        edge_controls = controls_by_edge.get((u, v), ())
        if edge_controls and not any(
            bool(control.get("allowed")) for control in edge_controls
        ):
            edge_density = spr.paper_effective_density(G, u, v)
            data["sim_weight"] = spr.PAPER_BLOCKED_EDGE_COST
            control_densities[(u, v)] = float("inf")
            normal_costs[(u, v)] = spr.paper_edge_cost_from_density(
                G,
                u,
                v,
                edge_density,
                apply_temporary_high_cost=False,
            )
            current_active.add((u, v))
            continue
        # Once a branch is open, prune only its target gates whose own density
        # or service backlog is invalid.  A valid target gate on the same
        # receiving line remains available.
        if (
            queue_to_gate.get(v, v) in blocked_crossline_target_gates
            and (u, v) not in gate_service_edges
        ):
            edge_density = spr.paper_effective_density(G, u, v)
            data["sim_weight"] = spr.PAPER_BLOCKED_EDGE_COST
            control_densities[(u, v)] = float("inf")
            normal_costs[(u, v)] = spr.paper_edge_cost_from_density(
                G,
                u,
                v,
                edge_density,
                apply_temporary_high_cost=False,
            )
            current_active.add((u, v))
            continue
        edge_density = spr.paper_effective_density(G, u, v)
        gate_density = (
            float(gate_states[v]["effective_density"])
            if v in gate_states
            else 0.0
        )
        source_queue_density = (
            _node_density(G, u)
            if str(G.nodes[u].get("type", "")).strip().lower() == "queue_area"
            else 0.0
        )
        destination_queue_density = (
            _node_density(G, v)
            if str(G.nodes[v].get("type", "")).strip().lower() == "queue_area"
            else 0.0
        )
        # A Queue is the receiving buffer for a specific Gate.  The
        # Queue->Gate service edge is intentionally kept available so that
        # people already inside the buffer can drain.  New upstream arrivals,
        # however, must still see the physical Gate density; otherwise a full
        # Gate can keep accepting people forever when its separate Queue area
        # is not yet crowded.
        approach_gate = queue_to_gate.get(v)
        approach_gate_density = (
            float(gate_states[approach_gate]["effective_density"])
            if approach_gate in gate_states
            else 0.0
        )
        control_density = max(
            (
                edge_density,
                gate_density,
                source_queue_density,
                destination_queue_density,
                approach_gate_density,
            )
            if (u, v) not in gate_service_edges
            else (edge_density,)
        )
        normal_cost = spr.paper_edge_cost_from_density(
            G,
            u,
            v,
            edge_density,
            apply_temporary_high_cost=False,
        )
        # The Q/mu gate-waiting term is NOT part of Meng et al.'s published
        # Improved cost.  It is disabled for the formal Improved baseline,
        # but can be enabled explicitly with
        #   G.graph["improved_gate_queue_term"] = True
        # to run the pure published baseline ("Improved") alongside the
        # enhanced one ("Improved+Q").
        if v in gate_states and bool(
            G.graph.get("improved_gate_queue_term", IMPROVED_GATE_QUEUE_TERM)
        ):
            service_rate = resource_capacity_per_second(
                G, ("facility", v)
            )
            queue_people = float(gate_states[v]["queue_people"])
            queue_wait_cost = (
                queue_people / service_rate
                if queue_people > 0.0 and service_rate > 0.0
                else float("inf")
                if queue_people > 0.0
                else 0.0
            )
            normal_cost += queue_wait_cost
        is_high_cost = (
            control_density > spr.PAPER_HIGH_DENSITY_THRESHOLD
        )
        data["sim_weight"] = (
            spr.PAPER_BLOCKED_EDGE_COST
            if is_high_cost
            else normal_cost
        )
        edge = (u, v)
        control_densities[edge] = control_density
        normal_costs[edge] = normal_cost
        if is_high_cost:
            current_active.add(edge)

    previous_active = set(
        G.graph.get("_paper_high_cost_active_edges", set())
    )
    newly_active = current_active - previous_active
    recovered = previous_active - current_active
    recovery_times = G.graph.setdefault(
        "_paper_high_cost_recovery_times", {}
    )
    for edge in recovered:
        recovery_times[edge] = now

    stale_count = 0
    for u, v, data in G.edges(data=True):
        edge = (u, v)
        actual = float(data.get("sim_weight", float("nan")))
        expected = (
            spr.PAPER_BLOCKED_EDGE_COST
            if edge in current_active
            else float(normal_costs[edge])
        )
        if math.isfinite(expected):
            matches = math.isfinite(actual) and math.isclose(
                actual, expected, rel_tol=0.0, abs_tol=1e-9
            )
        else:
            matches = math.isinf(actual) and actual > 0.0
        if not matches:
            stale_count += 1

    diagnostics = G.graph.setdefault(
        "_improved_temporary_high_cost_diagnostics",
        {},
    )
    diagnostics["temporary_high_cost_events"] = int(
        diagnostics.get("temporary_high_cost_events", 0)
    ) + len(newly_active)
    diagnostics["recovered_next_step_events"] = int(
        diagnostics.get("recovered_next_step_events", 0)
    ) + len(recovered)
    diagnostics["high_cost_active_edges"] = len(current_active)
    diagnostics["maximum_high_cost_active_edges"] = max(
        int(diagnostics.get("maximum_high_cost_active_edges", 0)),
        len(current_active),
    )
    diagnostics["stale_high_cost_state_count"] = int(
        diagnostics.get("stale_high_cost_state_count", 0)
    ) + stale_count
    diagnostics["last_refresh_time_seconds"] = now
    G.graph.setdefault(
        "_improved_temporary_high_cost_step_diagnostics", []
    ).append({
        "sim_time_seconds": now,
        "temporary_high_cost_events": len(newly_active),
        "recovered_next_step_events": len(recovered),
        "high_cost_active_edges": len(current_active),
        "stale_high_cost_state_count": stale_count,
    })

    G.graph["_paper_high_cost_active_edges"] = current_active
    G.graph["_paper_high_cost_control_densities"] = control_densities
    G.graph["_paper_high_cost_normal_costs"] = normal_costs
    G.graph["_dyn_weight_step"] = now
    return current_active, gate_states


def _paper_committed_transfer_edges(G, current_node, active_edges):
    """Return blocked admission edges downstream of an existing transfer."""
    if not str(current_node).startswith("Transfer_"):
        return set()
    control_edges = {
        tuple(control.get("entry_edge", ()))
        for control in G.graph.get(
            "_improved_ordinary_crossline_controls", []
        )
    }
    return {
        edge for edge in control_edges
        if edge in active_edges and len(edge) == 2 and G.has_edge(*edge)
    }


def _paper_committed_transfer_continuation(G, current_node):
    """Return the next hop for a batch already inside a known transfer branch."""
    if current_node != "VN_L16_to_Maglev_Arrival":
        return None
    source_groups = G.nodes.get(current_node, {}).get("source_group_dict", {})
    if any(
        str(source_group_id) == "L16_Maglev_transfer"
        and float(amount) > 0.0
        for source_group_id, amount in source_groups.items()
    ):
        next_node = "VN_Maglev_to_L2_Entrance"
        if G.has_edge(current_node, next_node):
            return next_node
    return None


def _paper_plan_path(G, current_node, allowed_active_edges=()):
    local_shortest = G.graph.get("_paper_full_shortest")
    if local_shortest is None:
        local_shortest = _shortest_distances_to_exits(G)
        G.graph["_paper_full_shortest"] = local_shortest
    allowed_active_edges = set(allowed_active_edges)
    original_weights = {}
    normal_costs = G.graph.get("_paper_high_cost_normal_costs", {})
    for edge in allowed_active_edges:
        if len(edge) != 2 or not G.has_edge(*edge):
            continue
        u, v = edge
        original_weights[edge] = G[u][v].get("sim_weight")
        G[u][v]["sim_weight"] = normal_costs.get(
            edge, G[u][v].get("sim_weight", float("inf"))
        )
    try:
        candidates = spr.enumerate_exit_paths(
            G,
            current_node,
            PAPER_SINGLE_PATH_METHOD,
            local_shortest,
            fruin_speed,
        )
    finally:
        for edge, weight in original_weights.items():
            G[edge[0]][edge[1]]["sim_weight"] = weight
    if not candidates:
        return None

    line_id = _routing_node_line_id(G, current_node)
    coverage_allowed = _paper_exit_coverage_allowed(G, current_node)
    coverage_candidate = (
        _select_exit_coverage_candidate(
            G,
            line_id,
            candidates,
            "_paper_exit_coverage_used",
        )
        if coverage_allowed
        else None
    )
    chosen = coverage_candidate or candidates[0]
    if coverage_candidate is not None:
        branch = _paper_path_via_unused_gate(
            G,
            current_node,
            str(coverage_candidate.get("target")),
            line_id,
        )
        if branch is not None:
            branch_cost, branch_gate, branch_path = branch
            chosen = {
                "target": coverage_candidate.get("target"),
                "cost": branch_cost,
                "path": branch_path,
            }
            _register_exit_coverage_gate(G, line_id, branch_gate)
        else:
            _register_exit_coverage_gate(
                G,
                line_id,
                _gate_facility_from_path(G, chosen.get("path")),
            )
        locked_paths = G.graph.setdefault(
            "_paper_exit_coverage_locked_paths", {}
        )
        selected_path = list(chosen.get("path") or [])
        for index, selected_node in enumerate(selected_path):
            locked_paths[selected_node] = selected_path[index:]
    if coverage_allowed:
        _register_exit_coverage_target(
            G,
            line_id,
            chosen.get("target"),
            "_paper_exit_coverage_used",
        )
    if coverage_candidate is not None:
        diagnostics = G.graph.setdefault(
            "_improved_exit_coverage_diagnostics", {}
        )
        diagnostics["override_count"] = int(
            diagnostics.get("override_count", 0)
        ) + 1
        diagnostics["override_people"] = int(
            diagnostics.get("override_people", 0)
        ) + int(round(float(G.nodes[current_node].get("people", 0.0))))
        diagnostics.setdefault("overrides", []).append({
            "sim_time": float(G.graph.get("_sim_time", 0.0)),
            "line_id": line_id,
            "node": str(current_node),
            "amount": int(round(float(G.nodes[current_node].get("people", 0.0)))),
            "target_exit": str(chosen.get("target")),
            "path": list(chosen.get("path") or []),
        })
    return list(chosen.get("path") or [])


def _paper_path_has_temporary_high_cost(path, active_edges):
    if not path:
        return True
    return any(
        (u, v) in active_edges
        for u, v in zip(path, path[1:])
    )


def _l7_hall_candidate_state(G, queue_node, amount=1):
    hall = "VN_L7_Hall_Arrival"
    gate = G.nodes[queue_node].get("queue_for_gate")
    queue_people = float(G.nodes[queue_node].get("people", 0.0))
    queue_area = max(float(effective_node_area(G, queue_node)), 0.1)
    gate_queue = (
        float(spr.current_resource_queue(G, ("facility", gate)))
        if gate in G.nodes else 0.0
    )
    service_rate = (
        float(resource_capacity_per_second(G, ("facility", gate)))
        if gate in G.nodes else 0.0
    )
    gate_entry_time = float(G.graph.get("_sim_time", 0.0))
    if G.has_edge(hall, queue_node):
        gate_entry_time += float(
            physical_edge_travel_time(G, hall, queue_node)
        )
    if gate in G.nodes and G.has_edge(queue_node, gate):
        gate_entry_time += float(
            physical_edge_travel_time(G, queue_node, gate)
        )
    predicted_gate_queue = (
        float(spr.predicted_resource_queue_at_time(
            G, ("facility", gate), gate_entry_time
        ))
        if gate in G.nodes else 0.0
    )
    return {
        "queue": queue_node,
        "gate": gate,
        "queue_people": queue_people,
        "queue_density_p_per_m2": queue_people / queue_area,
        "gate_queue_people": gate_queue,
        "gate_current_wait_seconds": (
            gate_queue / service_rate
            if service_rate > 0.0 else None
        ),
        "predicted_gate_entry_time": gate_entry_time,
        "predicted_gate_queue_people": predicted_gate_queue,
        "predicted_gate_wait_seconds": (
            predicted_gate_queue / service_rate
            if service_rate > 0.0 else None
        ),
        "decision_batch_amount": int(amount),
    }


def _append_l7_hall_decision_diagnostic(
    G,
    *,
    method,
    batch_id,
    batch_amount,
    old_queue,
    selected_queue,
    candidate_costs,
    candidate_paths,
    improvement_ratio,
    decision_people,
):
    hall = "VN_L7_Hall_Arrival"
    candidate_states = {
        queue: _l7_hall_candidate_state(
            G, queue, amount=batch_amount
        )
        for queue in G.successors(hall)
        if G.nodes[queue].get("queue_for_gate")
    }
    old_gate = (
        candidate_states.get(old_queue, {}).get("gate")
        if old_queue else None
    )
    selected_gate = candidate_states.get(selected_queue, {}).get("gate")
    rows = G.graph.setdefault("_l7_hall_decision_diagnostics", [])
    row = {
        "sim_time": float(G.graph.get("_sim_time", 0.0)),
        "method": method,
        "decision_node": hall,
        "batch_id": batch_id,
        "batch_amount": int(batch_amount),
        "old_queue": old_queue,
        "old_gate": old_gate,
        "selected_queue": selected_queue,
        "selected_gate": selected_gate,
        "candidate_queue_states": json.dumps(
            candidate_states, ensure_ascii=False, sort_keys=True
        ),
        "candidate_path_costs": json.dumps(
            {
                str(key): (
                    float(value) if math.isfinite(float(value)) else None
                )
                for key, value in candidate_costs.items()
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        "candidate_paths": json.dumps(
            {
                str(key): list(value or [])
                for key, value in candidate_paths.items()
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        "improvement_ratio": (
            float(improvement_ratio)
            if improvement_ratio is not None else None
        ),
        "decision_people": int(decision_people),
        "accepted_people": 0,
        "residual_people": int(batch_amount),
    }
    rows.append(row)
    return len(rows) - 1


def _finalize_l7_hall_decision_diagnostic(G, row_index, accepted_people):
    rows = G.graph.get("_l7_hall_decision_diagnostics", [])
    if row_index is None or not 0 <= int(row_index) < len(rows):
        return
    row = rows[int(row_index)]
    accepted_people = max(int(accepted_people), 0)
    row["accepted_people"] = accepted_people
    row["residual_people"] = max(
        int(row.get("batch_amount", 0)) - accepted_people,
        0,
    )


def _paper_candidate_path_and_cost(G, hall, queue_node):
    exits = [
        node for node, data in G.nodes(data=True)
        if data.get("type") == "exit"
    ]
    best_path = []
    best_cost = float("inf")
    for exit_node in exits:
        try:
            suffix_cost, suffix_path = nx.single_source_dijkstra(
                G,
                queue_node,
                target=exit_node,
                weight="sim_weight",
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        first_cost = float(
            G[hall][queue_node].get("sim_weight", float("inf"))
        )
        total_cost = first_cost + float(suffix_cost)
        if total_cost < best_cost:
            best_cost = total_cost
            best_path = [hall] + list(suffix_path)
    return best_path, best_cost


def _paper_record_target_high_cost_trace(
    G,
    gate_states,
    active_edges,
    selected_paths,
):
    now = float(G.graph.get("_sim_time", 0.0))
    recovery_times = G.graph.get(
        "_paper_high_cost_recovery_times", {}
    )
    trace = G.graph.setdefault(
        "_improved_temporary_high_cost_trace", []
    )
    for gate, (target_type, exit_name) in (
        _PAPER_TARGET_GATE_DIRECTIONS.items()
    ):
        if gate not in G.nodes:
            continue
        incoming = list(G.in_edges(gate))
        high_cost = any(edge in active_edges for edge in incoming)
        recovered_at = [
            float(recovery_times[edge])
            for edge in incoming
            if edge in recovery_times
        ]
        chosen_people = 0.0
        selected_costs = []
        for _, path, people in selected_paths:
            if gate not in path:
                continue
            chosen_people += float(people)
            cost = _path_total_cost(
                G,
                path,
                PAPER_SINGLE_PATH_METHOD,
            )
            if math.isfinite(cost):
                selected_costs.append(float(cost))
        if selected_costs:
            current_path_cost = min(selected_costs)
        else:
            incoming_costs = [
                float(G[u][v].get("sim_weight", float("inf")))
                for u, v in incoming
            ]
            current_path_cost = min(
                incoming_costs, default=float("inf")
            )
        state = gate_states.get(gate)
        density = (
            float(state["effective_density"])
            if state is not None
            else 0.0
        )
        trace.append({
            "sim_time_seconds": now,
            "target_type": target_type,
            "target_gate": gate,
            "exit_direction": exit_name,
            "current_density_p_per_m2": density,
            "temporary_high_cost_active": bool(high_cost),
            "latest_recovery_time_seconds": (
                max(recovered_at) if recovered_at else None
            ),
            "current_path_cost": current_path_cost,
            "selected_people_this_step": chosen_people,
        })


def _get_paper_step_moves(G, active_nodes):
    active_edges, gate_states = (
        _paper_refresh_temporary_high_cost_weights(G)
    )
    active_signature = tuple(sorted(active_edges))
    cached_signature = G.graph.get("_paper_high_cost_signature")
    paper_paths = G.graph.setdefault("_paper_path_by_node", {})
    paper_next = G.graph.setdefault("_paper_fixed_next_by_node", {})

    if cached_signature != active_signature:
        paper_paths.clear()
        paper_next.clear()
        G.graph["_paper_high_cost_signature"] = active_signature

    moves = []
    selected_paths = []
    hall_rows_by_edge = {}
    for u in active_nodes:
        committed_continuation = _paper_committed_transfer_continuation(
            G, u
        )
        if committed_continuation is not None:
            flow = float(G.nodes[u].get("people", 0.0))
            if flow > 0.0:
                forced_path = [u, committed_continuation]
                paper_next[u] = committed_continuation
                paper_paths[u] = forced_path
                moves.append((u, committed_continuation, flow))
                selected_paths.append((u, forced_path, flow))
                continuation_diagnostics = G.graph.setdefault(
                    "_improved_temporary_high_cost_diagnostics", {}
                )
                continuation_diagnostics[
                    "committed_transfer_continuation_events"
                ] = int(
                    continuation_diagnostics.get(
                        "committed_transfer_continuation_events", 0
                    )
                ) + 1
                continuation_diagnostics[
                    "committed_transfer_continuation_people"
                ] = float(
                    continuation_diagnostics.get(
                        "committed_transfer_continuation_people", 0.0
                    )
                ) + flow
                continue
        # The cross-line condition controls admission to the one-way branch,
        # not the physical completion of people already admitted to its entry
        # node.  Keep the edge removed from A* so new upstream choices remain
        # blocked; directly execute the only downstream continuation for the
        # people currently waiting at the branch entry.
        crossline_edges = {
            tuple(control.get("entry_edge"))
            for control in G.graph.get(
                "_improved_ordinary_crossline_controls", []
            )
            if tuple(control.get("entry_edge", ())) in active_edges
        }
        forced_crossline_edge = next(
            (
                edge for edge in sorted(crossline_edges, key=str)
                if len(edge) == 2
                and edge[0] == u
                and G.has_edge(*edge)
            ),
            None,
        )
        if forced_crossline_edge is not None:
            crossline_edge = forced_crossline_edge
            flow = float(G.nodes[u].get("people", 0.0))
            if flow > 0.0:
                forced_path = [u, crossline_edge[1]]
                paper_next[u] = crossline_edge[1]
                paper_paths[u] = forced_path
                moves.append((u, crossline_edge[1], flow))
                selected_paths.append((u, forced_path, flow))
                continuation_diagnostics = G.graph.setdefault(
                    "_improved_temporary_high_cost_diagnostics", {}
                )
                continuation_diagnostics[
                    "crossline_committed_continuation_events"
                ] = int(
                    continuation_diagnostics.get(
                        "crossline_committed_continuation_events", 0
                    )
                ) + 1
                continuation_diagnostics[
                    "crossline_committed_continuation_people"
                ] = float(
                    continuation_diagnostics.get(
                        "crossline_committed_continuation_people", 0.0
                    )
                ) + flow
                continue
        path = paper_paths.get(u)
        previous_path = list(path or [])
        committed_transfer_edges = _paper_committed_transfer_edges(
            G, u, active_edges
        )
        path_active_edges = active_edges - committed_transfer_edges
        coverage_locked_path = (
            G.graph.get("_paper_exit_coverage_locked_paths", {}).get(u)
        )
        coverage_locked = bool(
            coverage_locked_path
            and coverage_locked_path[0] == u
            and all(
                G.has_edge(left, right)
                for left, right in zip(
                    coverage_locked_path,
                    coverage_locked_path[1:],
                )
            )
        )
        if coverage_locked:
            path = list(coverage_locked_path)
            previous_path = list(path)
            for idx, node in enumerate(path[:-1]):
                paper_next[node] = path[idx + 1]
                paper_paths[node] = path[idx:]
        elif _paper_path_has_temporary_high_cost(path, path_active_edges):
            path = _paper_plan_path(
                G,
                u,
                allowed_active_edges=committed_transfer_edges,
            )
            # A* must return an admissible route.  NetworkX can otherwise
            # return a topological path whose total weight is +inf when all
            # remaining alternatives are density-blocked.
            if (
                not path
                or len(path) <= 1
                or _paper_path_has_temporary_high_cost(path, path_active_edges)
            ):
                continue
            for idx, node in enumerate(path[:-1]):
                paper_next[node] = path[idx + 1]
                paper_paths[node] = path[idx:]

        v = paper_next.get(u)
        if v and G.has_edge(u, v):
            flow = float(G.nodes[u]["people"])
            if flow > 0:
                moves.append((u, v, flow))
                selected_paths.append((u, path, flow))
                if u == "VN_L7_Hall_Arrival":
                    candidate_costs = {}
                    candidate_paths = {}
                    for queue_node in G.successors(u):
                        if not G.nodes[queue_node].get("queue_for_gate"):
                            continue
                        candidate_path, candidate_cost = (
                            _paper_candidate_path_and_cost(
                                G, u, queue_node
                            )
                        )
                        candidate_paths[queue_node] = candidate_path
                        candidate_costs[queue_node] = candidate_cost
                    old_queue = (
                        previous_path[1]
                        if len(previous_path) >= 2 else None
                    )
                    selected_queue = v
                    old_cost = candidate_costs.get(
                        old_queue, float("inf")
                    )
                    selected_cost = candidate_costs.get(
                        selected_queue, float("inf")
                    )
                    improvement = (
                        (old_cost - selected_cost) / old_cost
                        if (
                            old_queue
                            and math.isfinite(old_cost)
                            and old_cost > 0.0
                            and math.isfinite(selected_cost)
                        )
                        else None
                    )
                    switched = bool(
                        old_queue and old_queue != selected_queue
                    )
                    row_index = _append_l7_hall_decision_diagnostic(
                        G,
                        method="Improved-density-only" if not bool(
                            G.graph.get(
                                "improved_gate_queue_term",
                                IMPROVED_GATE_QUEUE_TERM,
                            )
                        ) else "Improved+Q",
                        batch_id=f"paper:{u}:{G.graph.get('_sim_time', 0.0)}",
                        batch_amount=int(flow),
                        old_queue=old_queue,
                        selected_queue=selected_queue,
                        candidate_costs=candidate_costs,
                        candidate_paths=candidate_paths,
                        improvement_ratio=improvement,
                        decision_people=int(flow) if switched else 0,
                    )
                    hall_rows_by_edge.setdefault(
                        (u, v), []
                    ).append(row_index)
                    summary = G.graph.setdefault(
                        "_l7_hall_common_decision_summary", {}
                    )
                    if switched:
                        summary[
                            "hall_gate_switch_decision_count"
                        ] = int(summary.get(
                            "hall_gate_switch_decision_count", 0
                        )) + 1
                        summary[
                            "hall_gate_switch_decision_people"
                        ] = int(summary.get(
                            "hall_gate_switch_decision_people", 0
                        )) + int(flow)
                        summary[
                            "improved_density_triggered_switch_count"
                        ] = int(summary.get(
                            "improved_density_triggered_switch_count", 0
                        )) + 1

    _paper_record_target_high_cost_trace(
        G,
        gate_states,
        active_edges,
        selected_paths,
    )
    integer_moves = _integerize_moves(G, moves)
    for u, v, accepted in integer_moves:
        row_indices = hall_rows_by_edge.get((u, v), [])
        if not row_indices:
            continue
        remaining = int(accepted)
        for row_index in row_indices:
            row = G.graph["_l7_hall_decision_diagnostics"][row_index]
            row_accepted = min(
                int(row.get("batch_amount", 0)), remaining
            )
            _finalize_l7_hall_decision_diagnostic(
                G, row_index, row_accepted
            )
            if row.get("decision_people", 0) and row_accepted > 0:
                summary = G.graph.setdefault(
                    "_l7_hall_common_decision_summary", {}
                )
                summary["hall_gate_switch_executed_count"] = int(
                    summary.get("hall_gate_switch_executed_count", 0)
                ) + 1
                summary["hall_gate_switch_executed_people"] = int(
                    summary.get("hall_gate_switch_executed_people", 0)
                ) + row_accepted
            remaining -= row_accepted
    return integer_moves


def _ensure_transit_state(G):
    if "_sim_time" not in G.graph:
        G.graph["_sim_time"] = 0.0
    if "_transit_queue" not in G.graph:
        G.graph["_transit_queue"] = []
        G.graph["_transit_queue_version"] = 0
    G.graph.setdefault("_transit_queue_version", 0)
    return G.graph["_sim_time"], G.graph["_transit_queue"]


def _mark_transit_queue_changed(G, appended_item=None):
    previous_version = int(G.graph.get("_transit_queue_version", 0))
    next_version = previous_version + 1
    resource_cache = G.graph.get("_aa_resource_event_indices_cache")
    previous_resource_key = (
        float(G.graph.get("_sim_time", 0.0)),
        previous_version,
    )
    G.graph["_transit_queue_version"] = next_version
    G.graph.pop("_aa_transit_spatial_events_cache", None)
    G.graph.pop("_aa_spatial_occupancy_prefix_cache", None)
    G.graph.pop("_confirmed_resource_arrivals_cache", None)
    if (
        appended_item is None
        or resource_cache is None
        or resource_cache.get("key") != previous_resource_key
    ):
        G.graph.pop("_aa_resource_event_indices_cache", None)
        return

    resource_cache["key"] = (
        previous_resource_key[0],
        next_version,
    )
    pending_resource = appended_item.get(
        "confirmed_arrival_resource_id"
    )
    if (
        pending_resource is None
        and not appended_item.get(
            "service_capacity_consumed",
            False,
        )
    ):
        pending_resource = appended_item.get("resource_id")
        if pending_resource is None:
            destination = appended_item.get(
                "dest",
                appended_item.get("v"),
            )
            if (
                destination is not None
                and spr.is_capacity_service_node(G, destination)
            ):
                pending_resource = ("facility", destination)
    amount = max(int(appended_item.get("amount", 0)), 0)
    if pending_resource is not None and amount > 0:
        spr.insert_resource_prediction_event(
            G,
            pending_resource,
            max(
                float(
                    appended_item.get(
                        "arrive_time",
                        previous_resource_key[0],
                    )
                ),
                previous_resource_key[0],
            ),
            amount,
        )


def _initialize_executed_route_tracking(G):
    """Initialize optional aggregate route tracing from actual source stocks.

    The sidecar is observational only. It never supplies movement demand,
    capacity, priorities, or routing decisions.
    """
    if not G.graph.get("_track_executed_routes", False):
        G.graph.pop("_executed_route_batches_by_node", None)
        G.graph.pop("_completed_executed_routes", None)
        G.graph.pop("_route_tracking_errors", None)
        return
    by_node = {}
    for node, data in G.nodes(data=True):
        batches = {}
        for source_group, amount in data.get("source_group_dict", {}).items():
            amount_int = max(int(round(float(amount))), 0)
            if amount_int > 0:
                batches[(str(source_group), (node,))] = amount_int
        if batches:
            by_node[node] = batches
    G.graph["_executed_route_batches_by_node"] = by_node
    G.graph["_completed_executed_routes"] = {}
    G.graph["_route_tracking_errors"] = []


def _take_executed_route_batches(G, source_node, destination_node, group_shares):
    """Move traced integer batches in the same quantities already accepted."""
    if not G.graph.get("_track_executed_routes", False):
        return []
    by_node = G.graph.setdefault("_executed_route_batches_by_node", {})
    node_batches = by_node.setdefault(source_node, {})
    moved = []
    for source_group, requested in group_shares.items():
        remaining = max(int(requested), 0)
        for key in list(node_batches):
            batch_group, path = key
            if batch_group != source_group or remaining <= 0:
                continue
            available = max(int(node_batches.get(key, 0)), 0)
            take = min(available, remaining)
            if take <= 0:
                continue
            node_batches[key] = available - take
            if node_batches[key] <= 0:
                del node_batches[key]
            moved.append({
                "source_group": source_group,
                "path": tuple(path) + (destination_node,),
                "amount": take,
            })
            remaining -= take
        if remaining:
            G.graph.setdefault("_route_tracking_errors", []).append({
                "kind": "missing_upstream_trace",
                "node": source_node,
                "destination": destination_node,
                "source_group": source_group,
                "amount": remaining,
            })
    if not node_batches:
        by_node.pop(source_node, None)
    return moved


def _take_aa_batch_executed_routes(batch, destination_node, amount):
    remaining = max(int(amount), 0)
    moved = []
    retained = []
    for item in batch.get("executed_route_batches", ()):
        available = max(int(item.get("amount", 0)), 0)
        take = min(available, remaining)
        if take > 0:
            moved.append({
                "source_group": item["source_group"],
                "path": tuple(item.get("path") or ()) + (destination_node,),
                "amount": take,
            })
            remaining -= take
        if available > take:
            retained.append({
                **item,
                "amount": available - take,
            })
    if remaining:
        raise RuntimeError(
            f"AA executed-route state is short by {remaining} people"
        )
    batch["executed_route_batches"] = retained
    return moved


def _deposit_executed_route_batches(G, destination_node, batches):
    if not G.graph.get("_track_executed_routes", False) or not batches:
        return
    destination_type = str(G.nodes[destination_node].get("type", "")).lower()
    if destination_type == "exit":
        completed = G.graph.setdefault("_completed_executed_routes", {})
        for batch in batches:
            key = (batch["source_group"], tuple(batch["path"]))
            completed[key] = completed.get(key, 0) + int(batch["amount"])
        return
    by_node = G.graph.setdefault("_executed_route_batches_by_node", {})
    destination_batches = by_node.setdefault(destination_node, {})
    for batch in batches:
        key = (batch["source_group"], tuple(batch["path"]))
        destination_batches[key] = (
            destination_batches.get(key, 0) + int(batch["amount"])
        )


def _compute_physical_edge_travel_time(G, u, v):
    """Return the one shared physical travel time used by every method.

    Edge type, not the type of an endpoint alone, determines whether a segment
    is horizontal or inside a vertical facility. Density is taken only from
    passengers physically travelling on this edge.
    """
    data = G[u][v]
    length = max(float(data.get("length", 0.0)), 0.0)
    if length <= 0.0:
        return 0.0
    density = _edge_density(G, u, v)

    u_type = str(G.nodes[u].get("type", "")).lower()
    v_type = str(G.nodes[v].get("type", "")).lower()
    edge_type = str(data.get("edge_type", "")).lower()

    flat_speed = _density_adjusted_speed(FACILITY_BASE_SPEED_M_PER_S["flat"], density)

    if edge_type in {"platform_to_vertical", "platform_zone_to_vertical"}:
        line_ids = sorted(_infer_node_line_ids_strict(u) | _infer_node_line_ids_strict(v))
        vertical_length = 0.0
        if line_ids:
            line_id = line_ids[0]
            if line_id in STATION_LEVELS:
                vertical_length = min(2.0 * get_delta_h(line_id), length)
        horizontal_length = max(length - vertical_length, 0.0)
        if "stair" in v_type:
            vertical_speed = FACILITY_BASE_SPEED_M_PER_S["stair"]
        elif "escalator" in v_type:
            vertical_speed = FACILITY_BASE_SPEED_M_PER_S["escalator"]
        else:
            vertical_speed = FACILITY_BASE_SPEED_M_PER_S["flat"]
        vertical_speed = _density_adjusted_speed(vertical_speed, density)
        if (horizontal_length > 0 and flat_speed <= 0.0) or (
            vertical_length > 0 and vertical_speed <= 0.0
        ):
            return float("inf")
        travel_time = horizontal_length / flat_speed + vertical_length / max(vertical_speed, 0.001)
        return max(0.0, travel_time)

    flat_edge_types = {
        "vertical_to_gate",
        "vertical_to_virtual",
        "gate_to_virtual",
        "virtual_to_gate",
        "gate_to_exit",
        "gate_to_vertical",
        "hall_to_gate",
        "transfer_to_gate",
        "exit_channel",
        "virtual_channel",
    }
    if edge_type in flat_edge_types:
        if flat_speed <= 0.0:
            return float("inf")
        return max(0.0, length / flat_speed)

    # Realized propagation speed depends on true facility traversal. Edges that
    # merely start/end at a facility but represent a hall corridor are handled above.
    if "stair" in u_type or "stair" in v_type or "stair" in edge_type:
        speed = FACILITY_BASE_SPEED_M_PER_S["stair"]
    elif "escalator" in u_type or "escalator" in v_type or "escalator" in edge_type:
        speed = FACILITY_BASE_SPEED_M_PER_S["escalator"]
    else:
        speed = FACILITY_BASE_SPEED_M_PER_S["flat"]
    speed = _density_adjusted_speed(speed, density)

    if speed <= 0.0:
        return float("inf")
    travel_time = length / speed
    return max(0.0, travel_time)


def physical_edge_travel_time(G, u, v):
    """Cached shared physical time; edge density is fixed within one step."""
    data = G[u][v]
    simulation_time = float(G.graph.get("_sim_time", 0.0))
    if data.get("_physical_travel_time_cache_step") == simulation_time:
        return float(data["_physical_travel_time_cache"])
    travel_time = _compute_physical_edge_travel_time(G, u, v)
    data["_physical_travel_time_cache_step"] = simulation_time
    data["_physical_travel_time_cache"] = travel_time
    return travel_time


def _edge_travel_time(G, u, v):
    """Backward-compatible wrapper for the shared physical travel time."""
    return physical_edge_travel_time(G, u, v)


def _accepted_edge_travel_time(G, u, v):
    """Require every capacity-accepted movement to have a finite arrival."""
    travel_time = _edge_travel_time(G, u, v)
    if not math.isfinite(travel_time):
        raise RuntimeError(
            f"Capacity allocator accepted non-finite edge travel time: {u} -> {v}"
        )
    return travel_time


def _process_transit_arrivals(
    G,
    current_time,
    evacuated_by_line=None,
    evacuated_by_source_group=None,
    exit_usage_dict=None,
    exit_usage_by_source_group=None,
    node_throughput_by_sg=None,
):
    arrival_epoch = int(
        G.graph.get(
            "_aa_arrival_merge_epoch",
            0,
        )
    ) + 1

    G.graph[
        "_aa_arrival_merge_epoch"
    ] = arrival_epoch

    transit_queue = G.graph.setdefault("_transit_queue", [])
    service_arrivals = {}
    if not transit_queue:
        return 0.0

    remaining = []
    evac_total = 0.0

    for item in transit_queue:
        arrive_time = float(item["arrive_time"])
        if not math.isfinite(arrive_time):
            raise RuntimeError(
                "Non-finite transit arrival detected: "
                f"{item.get('u')} -> {item.get('v')}, "
                f"amount={item.get('amount')}, arrive_time={arrive_time}"
            )
        if arrive_time > current_time + 1e-9:
            remaining.append(item)
            continue

        dest = item.get("dest", item.get("v"))
        if dest is None or dest not in G.nodes:
            continue
        amount = item["amount"]
        line_shares = item["line_shares"]
        source_group_shares = item.get("source_group_shares", {})
        dest_type = G.nodes[dest].get("type", "")
        if not item.get("aa_batch_state") or dest_type == "exit":
            _deposit_executed_route_batches(
                G, dest, item.get("executed_route_batches", [])
            )

        if dest_type == "exit":
            for line_id, flow in line_shares.items():
                if flow <= 0:
                    continue
                if evacuated_by_line is not None:
                    evacuated_by_line[line_id] += flow
                if exit_usage_dict is not None and dest in exit_usage_dict:
                    exit_usage_dict[dest][line_id] += flow

            if exit_usage_by_source_group is not None and dest in exit_usage_by_source_group:
                for source_group_id, flow in source_group_shares.items():
                    if flow > 0:
                        exit_usage_by_source_group[dest][source_group_id] = (
                            exit_usage_by_source_group[dest].get(source_group_id, 0) + flow
                        )
                        if evacuated_by_source_group is not None:
                            evacuated_by_source_group[source_group_id] = (
                            evacuated_by_source_group.get(source_group_id, 0.0) + flow
                        )

            event_log = G.graph.setdefault("_evacuation_arrival_events", [])
            for source_group_id, flow in source_group_shares.items():
                if flow > 0:
                    event_log.append({
                        "time": float(current_time),
                        "amount": int(flow),
                        "source_group": source_group_id,
                        "from_node": item.get("u"),
                        "exit": dest,
                        "resource_id": resource_id_text(item.get("resource_id")),
                        "cohort_id": item.get("cohort_state", {}).get("cohort_id"),
                    })

            evac_total += amount
            continue

        if spr.is_capacity_service_node(G, dest):
            service_arrivals[dest] = service_arrivals.get(dest, 0.0) + float(amount)
        if is_point_service_resource(G, dest):
            gate_diag = G.graph.setdefault("_gate_service_diagnostics", {})
            gate_stat = gate_diag.setdefault(dest, {})
            gate_stat["gate_arrival_people"] = (
                float(gate_stat.get("gate_arrival_people", 0.0))
                + float(amount)
            )

        for line_id, flow in line_shares.items():
            if flow <= 0:
                continue
            G.nodes[dest]["people_dict"][line_id] += flow

        for source_group_id, flow in source_group_shares.items():
            if flow <= 0:
                continue
            G.nodes[dest].setdefault("source_group_dict", {})
            G.nodes[dest]["source_group_dict"][source_group_id] = (
                G.nodes[dest]["source_group_dict"].get(source_group_id, 0) + flow
            )
            # 累积追踪：设施节点的来源组通过人数
            if node_throughput_by_sg is not None:
                node_throughput_by_sg.setdefault(dest, {})
                node_throughput_by_sg[dest][source_group_id] = (
                    node_throughput_by_sg[dest].get(source_group_id, 0.0) + flow
                )

        cohort_state = item.get("cohort_state")
        if cohort_state and amount > 0:
            cohort = dict(cohort_state)
            cohort["amount"] = int(amount)
            cohort["arrival_time"] = float(current_time)
            segment = list(cohort.get("committed_segment", []))
            index = int(cohort.get("segment_index", 0))
            if index < len(segment) and segment[index] != dest:
                try:
                    index = segment.index(dest, max(index - 1, 0))
                except ValueError:
                    index = 0
            cohort["segment_index"] = index
            if dest == cohort.get("next_decision_node") or G.nodes[dest].get("type") == "exit":
                cohort["committed"] = False
                cohort["committed_segment"] = []
                cohort["segment_index"] = 0
                cohort["next_decision_node"] = None
            G.nodes[dest].setdefault("_mesoscopic_cohorts", []).append(cohort)

        aa_batch_state = item.get("aa_batch_state")
        if aa_batch_state and amount > 0:
            batch = dict(aa_batch_state)
            batch["amount"] = int(amount)
            batch["arrival_time"] = float(current_time)
            batch["current_node"] = dest
            if G.graph.get("_track_executed_routes", False):
                batch["executed_route_batches"] = list(
                    item.get("executed_route_batches", ())
                )
            remaining_path = list(batch.get("current_path") or [])
            if remaining_path and remaining_path[0] != dest:
                try:
                    remaining_path = remaining_path[remaining_path.index(dest):]
                except ValueError:
                    remaining_path = []
            batch["waiting_resource"] = (
                edge_resource_id(G, dest, remaining_path[1])
                if len(remaining_path) > 1 and G.has_edge(dest, remaining_path[1])
                else None
            )
            # A transported child has reached a new node. Preserve the valid
            # suffix as the fallback route, but allow one fresh decision when
            # that node is an explicit AA selection stage.
            batch["planned_selection_node"] = None
            if batch.get("plan_history_node") != dest:
                batch["plan_history_node"] = None
                batch["selected_first_hops"] = []
                batch["step4b2_opportunity_best"] = {}
            batch["current_path"] = remaining_path
            if (
                batch.get("gate_switch_in_progress")
                and dest == batch.get("gate_switch_target_queue")
            ):
                batch["gate_switch_in_progress"] = False
                batch["gate_switch_completed"] = True
                batch["gate_switch_target_queue"] = None
            _append_aa_batch(G, dest, batch)

        G.nodes[dest]["people"] += amount

    G.graph["_transit_queue"] = remaining
    _mark_transit_queue_changed(G)
    return evac_total


def _schedule_moves_as_transit(G, moves):
    aa_allocations = G.graph.pop("_aa_accepted_allocations", None)
    if aa_allocations is not None:
        return _schedule_aa_batch_moves_as_transit(G, moves, aa_allocations)
    mesoscopic_allocations = G.graph.pop("_mesoscopic_accepted_allocations", None)
    if mesoscopic_allocations is not None:
        return _schedule_mesoscopic_moves_as_transit(G, moves, mesoscopic_allocations)
    _, transit_queue = _ensure_transit_state(G)
    current_time = float(G.graph.get("_sim_time", 0.0))
    scheduled = []

    for u, v, amount in moves:
        sum_u = max(int(math.floor(float(G.nodes[u].get("people", 0.0)) + 1e-9)), 0)
        amount = max(int(amount), 0)
        if sum_u <= 0 or amount <= 0:
            continue
        travel_time = _accepted_edge_travel_time(G, u, v)

        line_shares = {}
        source_group_shares = {}
        source_group_dict = G.nodes[u].get("source_group_dict", {})
        active_groups = []
        group_weights = []
        group_caps = []

        for source_group_id, ppl in source_group_dict.items():
            ppl_int = max(int(math.floor(float(ppl) + 1e-9)), 0)
            if ppl_int <= 0:
                continue
            active_groups.append(source_group_id)
            group_weights.append(ppl_int)
            group_caps.append(ppl_int)

        if active_groups:
            group_alloc = _integer_capped_allocation(amount, group_weights, group_caps)
            for source_group_id, flow in zip(active_groups, group_alloc):
                if flow <= 0:
                    continue
                source_group_shares[source_group_id] = flow
                G.nodes[u]["source_group_dict"][source_group_id] = max(
                    int(G.nodes[u]["source_group_dict"].get(source_group_id, 0)) - flow,
                    0,
                )
                line_id = _source_group_line_id(source_group_id)
                line_shares[line_id] = line_shares.get(line_id, 0) + flow

            for line_id, flow in line_shares.items():
                G.nodes[u]["people_dict"][line_id] = max(
                    int(G.nodes[u]["people_dict"].get(line_id, 0)) - flow,
                    0,
                )
        else:
            active_lines = []
            line_weights = []
            line_caps = []
            for line_id, ppl in G.nodes[u].get("people_dict", {}).items():
                ppl_int = max(int(math.floor(float(ppl) + 1e-9)), 0)
                if ppl_int <= 0:
                    continue
                active_lines.append(line_id)
                line_weights.append(ppl_int)
                line_caps.append(ppl_int)

            line_alloc = _integer_capped_allocation(amount, line_weights, line_caps)
            for line_id, flow in zip(active_lines, line_alloc):
                if flow <= 0:
                    continue
                line_shares[line_id] = flow
                G.nodes[u]["people_dict"][line_id] = max(int(G.nodes[u]["people_dict"][line_id]) - flow, 0)

        G.nodes[u]["people"] = max(sum_u - amount, 0)
        executed_route_batches = _take_executed_route_batches(
            G, u, v, source_group_shares
        )

        guidance = G.graph.get("_our_guidance_state", {}).get(u, {})
        commitment = {
            "depart_time": current_time,
            "arrive_time": current_time + travel_time,
            "u": u,
            "v": v,
            "amount": amount,
            "resource_id": edge_resource_id(G, u, v),
            # This entrance resource was already admitted by the shared
            # integer capacity allocator. The traveller is now in service,
            # not a future customer waiting to consume the same capacity.
            "service_capacity_consumed": True,
            "source_node": u,
            "path_version": int(guidance.get("path_version", 0)),
            "line_shares": line_shares,
            "source_group_shares": source_group_shares,
            "executed_route_batches": executed_route_batches,
            "travel_time": travel_time,
        }
        transit_queue.append(commitment)
        _mark_transit_queue_changed(G, commitment)
        scheduled.append({
            "u": u,
            "v": v,
            "amount": amount,
            "travel_time": travel_time,
            "line_shares": line_shares,
            "source_group_shares": source_group_shares,
            "executed_route_batches": executed_route_batches,
        })

    return scheduled


def _schedule_mesoscopic_moves_as_transit(G, moves, allocations):
    """Schedule exact accepted cohorts; rejected people remain uncommitted upstream."""
    _, transit_queue = _ensure_transit_state(G)
    current_time = float(G.graph.get("_sim_time", 0.0))
    scheduled = []
    diagnostics = G.graph.setdefault("_mesoscopic_diagnostics", {})
    for u, v, total_amount in moves:
        remaining = int(total_amount)
        for allocation in allocations.get((u, v), []):
            amount = min(int(allocation["amount"]), remaining)
            if amount <= 0:
                continue
            travel_time = _accepted_edge_travel_time(G, u, v)
            cohorts = _ensure_node_mesoscopic_cohorts(G, u)
            cohort = next(
                (c for c in cohorts if c.get("cohort_id") == allocation["cohort_id"]),
                None,
            )
            if cohort is None or int(cohort.get("amount", 0)) < amount:
                raise RuntimeError(
                    f"Mesoscopic cohort state mismatch at {u}: {allocation['cohort_id']}; "
                    f"accepted={amount}, cohort={cohort}, allocations={allocations.get((u, v), [])}"
                )
            cohort["amount"] = int(cohort["amount"]) - amount
            source_group = cohort["source_group"]
            line_id = _source_group_line_id(source_group)
            G.nodes[u]["people"] = max(int(G.nodes[u].get("people", 0)) - amount, 0)
            G.nodes[u]["source_group_dict"][source_group] = max(
                int(G.nodes[u]["source_group_dict"].get(source_group, 0)) - amount, 0
            )
            G.nodes[u]["people_dict"][line_id] = max(
                int(G.nodes[u]["people_dict"].get(line_id, 0)) - amount, 0
            )
            cohort_state = {
                # The physically admitted part becomes a new natural departure
                # batch. The upstream remainder keeps the parent id and stays
                # uncommitted, so later arrivals cannot share an ambiguous id.
                "cohort_id": _next_cohort_id(G),
                "source_group": source_group,
                "arrival_time": cohort.get("arrival_time", current_time),
                "amount": amount,
                "committed_segment": list(allocation["committed_segment"]),
                "segment_index": int(allocation["segment_index"]) + 1,
                "next_decision_node": allocation.get("next_decision_node"),
                "committed": True,
            }
            commitment = {
                "depart_time": current_time,
                "arrive_time": current_time + travel_time,
                "u": u,
                "v": v,
                "amount": amount,
                "resource_id": edge_resource_id(G, u, v),
                "service_capacity_consumed": True,
                "source_node": u,
                "path_version": 0,
                "line_shares": {line_id: amount},
                "source_group_shares": {source_group: amount},
                "travel_time": travel_time,
                "cohort_state": cohort_state,
            }
            transit_queue.append(commitment)
            _mark_transit_queue_changed(G, commitment)
            scheduled.append({
                "u": u,
                "v": v,
                "amount": amount,
                "travel_time": travel_time,
                "line_shares": {line_id: amount},
                "source_group_shares": {source_group: amount},
                "cohort_id": cohort["cohort_id"],
            })
            diagnostics["segment_commitment_count"] = int(
                diagnostics.get("segment_commitment_count", 0)
            ) + 1
            remaining -= amount
        if remaining:
            raise RuntimeError(f"Unattributed mesoscopic accepted flow {u}->{v}: {remaining}")
        G.nodes[u]["_mesoscopic_cohorts"] = [
            c for c in G.nodes[u].get("_mesoscopic_cohorts", []) if int(c.get("amount", 0)) > 0
        ]
    return scheduled


def _schedule_aa_batch_moves_as_transit(G, moves, allocations):
    """Schedule exact predictive-AA batches without changing common capacity."""
    _, transit_queue = _ensure_transit_state(G)
    now = float(G.graph.get("_sim_time", 0.0))
    scheduled = []
    batch_index_by_node = {}
    for u, v, total_amount in moves:
        remaining = int(total_amount)
        for allocation in allocations.get((u, v), []):
            amount = min(int(allocation["amount"]), remaining)
            if amount <= 0:
                continue
            travel_time = _accepted_edge_travel_time(G, u, v)
            batches = _ensure_node_aa_batches(G, u)
            batch_index = batch_index_by_node.get(u)
            if batch_index is None:
                batch_index = {
                    item.get("batch_id"): item
                    for item in batches
                }
                batch_index_by_node[u] = batch_index
            batch = batch_index.get(allocation["batch_id"])
            if batch is None or int(batch.get("amount", 0)) < amount:
                raise RuntimeError(f"AA batch state mismatch at {u}: {allocation['batch_id']}")
            batch["amount"] = int(batch["amount"]) - amount
            source_group = batch["source_group"]
            line_id = _source_group_line_id(source_group)
            G.nodes[u]["people"] = max(int(G.nodes[u].get("people", 0)) - amount, 0)
            G.nodes[u]["source_group_dict"][source_group] = max(
                int(G.nodes[u]["source_group_dict"].get(source_group, 0)) - amount, 0
            )
            G.nodes[u]["people_dict"][line_id] = max(
                int(G.nodes[u]["people_dict"].get(line_id, 0)) - amount, 0
            )
            if "executed_route_batches" in batch:
                executed_route_batches = _take_aa_batch_executed_routes(
                    batch, v, amount
                )
            else:
                executed_route_batches = _take_executed_route_batches(
                    G,
                    u,
                    v,
                    {source_group: amount},
                )
            actual_queue = spr.current_resource_queue(G, edge_resource_id(G, u, v))
            predicted_queue = float(allocation.get("predicted_queue_at_entry", 0.0))
            if G.graph.get("_active_simulation_method") == OUR_SINGLE_PATH_METHOD:
                G.graph.setdefault("_aa_prediction_accuracy", []).append({
                    "batch_id": allocation["batch_id"],
                    "source_group": source_group,
                    "resource_id": resource_id_text(edge_resource_id(G, u, v)),
                    "predicted_time": float(allocation.get("predicted_entry_time", now)),
                    "actual_time": now,
                    "predicted_queue": predicted_queue,
                    "actual_queue": actual_queue,
                    "error": predicted_queue - actual_queue,
                    "absolute_error": abs(predicted_queue - actual_queue),
                })
            if allocation.get("rerouted_this_step"):
                diagnostics = G.graph.setdefault("_aa_diagnostics", {})
                diagnostics["effective_reroute_count"] = int(
                    diagnostics.get("effective_reroute_count", 0)
                ) + 1
            gate_switch = allocation.get("gate_approach_switch")
            if G[u][v].get("gate_switch_only") and not gate_switch:
                raise RuntimeError(
                    f"Unauthorized gate-switch edge traversal: {u}->{v}; "
                    f"batch_id={allocation.get('batch_id')}; "
                    f"rerouted={allocation.get('rerouted_this_step')}; "
                    f"path={allocation.get('current_path')}"
                )
            if gate_switch:
                diagnostics = G.graph.setdefault("_aa_diagnostics", {})
                diagnostics["gate_approach_rerouted_people"] = int(
                    diagnostics.get("gate_approach_rerouted_people", 0)
                ) + amount
                diagnostics["gate_switch_people"] = int(
                    diagnostics.get("gate_switch_people", 0)
                ) + amount
                matrix = diagnostics.setdefault("gate_switch_matrix", {})
                key = (
                    f"{gate_switch.get('current_gate')}"
                    f"->{gate_switch.get('target_gate')}"
                )
                matrix[key] = int(matrix.get(key, 0)) + amount
            remaining_predictions = list(allocation.get("path_predictions") or [])[1:]
            child_state = {
                "batch_id": _next_aa_batch_id(G),
                "source_group": source_group,
                "arrival_time": batch.get("arrival_time", now),
                "amount": amount,
                "current_node": v,
                "current_path": list(allocation["current_path"])[1:],
                "waiting_resource": None,
                "queue_enter_time": None,
                "last_reroute_step": None,
                "previous_waiting_resource": batch.get("previous_waiting_resource"),
                "path_predictions": remaining_predictions,
                "planned_selection_node": None,
                "step4b2_opportunity_best": dict(
                    batch.get("step4b2_opportunity_best") or {}
                ),
                "plan_history_node": batch.get("plan_history_node"),
                "selected_first_hops": list(
                    batch.get("selected_first_hops") or []
                ),
                "has_rerouted": bool(
                    batch.get("has_rerouted", False)
                ),
                # Queue->Gate service commitment ends after Gate admission.
                "service_committed": False,
                "precommit_pending": False,
                "gate_switch_in_progress": bool(
                    batch.get("gate_switch_in_progress", False)
                    or gate_switch
                ),
                "gate_switch_completed": bool(
                    batch.get("gate_switch_completed", False)
                ),
                "gate_switch_target_queue": (
                    gate_switch.get("target_queue")
                    if gate_switch
                    else batch.get("gate_switch_target_queue")
                ),
            }
            commitment = {
                "depart_time": now,
                "arrive_time": now + travel_time,
                "u": u, "v": v, "amount": amount,
                "resource_id": edge_resource_id(G, u, v),
                "service_capacity_consumed": True,
                "source_node": u, "path_version": 0,
                "line_shares": {line_id: amount},
                "source_group_shares": {source_group: amount},
                "executed_route_batches": executed_route_batches,
                "travel_time": travel_time,
                "aa_batch_state": child_state,
            }
            transit_queue.append(commitment)
            _mark_transit_queue_changed(G, commitment)
            scheduled.append({
                "u": u, "v": v, "amount": amount,
                "travel_time": travel_time,
                "line_shares": {line_id: amount},
                "source_group_shares": {source_group: amount},
                "executed_route_batches": executed_route_batches,
                "batch_id": child_state["batch_id"],
            })
            remaining -= amount
        if remaining:
            raise RuntimeError(f"Unattributed AA accepted flow {u}->{v}: {remaining}")
        G.nodes[u]["_aa_batches"] = [
            batch for batch in G.nodes[u].get("_aa_batches", [])
            if int(batch.get("amount", 0)) > 0
        ]
    return scheduled


def _node_edge_types(G, node):
    edge_types = []
    for pred in G.predecessors(node):
        edge_types.append(G[pred][node].get("edge_type", ""))
    for succ in G.successors(node):
        edge_types.append(G[node][succ].get("edge_type", ""))
    return edge_types


def _is_queue_node(G, node):
    """
    排队节点的操作性定义：
    - 闸机
    - 楼扶梯 / 楼梯
    - 窄通道
    - 与 gate / exit 直接相连、承担入口等待功能的 virtual 节点

    注意：exit 在本模型里是 sink，真正的等待通常体现在出口前一级的节点。
    """
    node_type = G.nodes[node].get("type", "")
    node_type_l = str(node_type).lower()
    node_name_l = str(node).lower()

    if node_type_l.startswith("gate"):
        return True
    if node_type_l == "queue_area":
        return True
    if node_type_l in {"stair", "escalator"}:
        return True
    if node_type_l == "passageway":
        width = float(G.nodes[node].get("width", float("inf")))
        return width <= 8.0

    if node_type_l == "virtual":
        if "entrance" in node_name_l or "exit" in node_name_l:
            return True
        edge_types = _node_edge_types(G, node)
        if any(("gate" in et.lower()) or ("exit" in et.lower()) for et in edge_types):
            return True

    return False


def _infer_node_line_ids(G, node):
    """根据节点名和邻接平台，推断该节点可能对应的线路集合。"""
    node_name_l = str(node).lower()
    line_ids = set()

    for line_id in ALL_LINE_IDS:
        if line_id.lower() in node_name_l:
            line_ids.add(line_id)
        platform_node = f"platform_{line_id}".lower()
        if node_name_l == platform_node:
            line_ids.add(line_id)

    if node in G.nodes:
        for pred in G.predecessors(node):
            pred_name_l = str(pred).lower()
            for line_id in ALL_LINE_IDS:
                if f"platform_{line_id}".lower() == pred_name_l or line_id.lower() in pred_name_l:
                    line_ids.add(line_id)
        for succ in G.successors(node):
            succ_name_l = str(succ).lower()
            for line_id in ALL_LINE_IDS:
                if f"platform_{line_id}".lower() == succ_name_l or line_id.lower() in succ_name_l:
                    line_ids.add(line_id)

    return line_ids


def _infer_node_line_ids_strict(node):
    """仅根据节点名直接包含的线路标识判断归属，避免跨线串扰。"""
    node_name_l = str(node).lower()
    line_ids = set()
    for line_id in ALL_LINE_IDS:
        if line_id.lower() in node_name_l:
            line_ids.add(line_id)
    return line_ids


def _physical_line_ids_for_node(G, node):
    explicit = G.nodes[node].get("physical_line_ids") if node in G.nodes else None
    if explicit:
        if isinstance(explicit, str):
            return {explicit}
        return set(explicit)
    return _infer_node_line_ids_strict(node)


def _physical_line_ids_for_edge(G, u, v):
    line_ids = set()
    if u in G.nodes:
        line_ids.update(_physical_line_ids_for_node(G, u))
    if v in G.nodes:
        line_ids.update(_physical_line_ids_for_node(G, v))
    return line_ids


def _format_physical_occupancy_items(items, limit=6):
    if not items:
        return ""
    ordered = sorted(items.items(), key=lambda item: item[1], reverse=True)
    return "; ".join(f"{name}:{value:.1f}" for name, value in ordered[:limit])


def _update_physical_line_occupancy_metrics(G, metrics, current_time):
    cache = G.graph.setdefault("_physical_line_cache", {})
    node_line_ids = cache.get("node_line_ids")
    if node_line_ids is None:
        node_line_ids = {node: _physical_line_ids_for_node(G, node) for node in G.nodes}
        cache["node_line_ids"] = node_line_ids
    edge_line_ids = cache.get("edge_line_ids")
    if edge_line_ids is None:
        edge_line_ids = {
            _edge_key(u, v): _physical_line_ids_for_edge(G, u, v)
            for u, v in G.edges
        }
        cache["edge_line_ids"] = edge_line_ids

    stats_by_line = metrics.setdefault(
        "physical_area_stats_by_line",
        {
            line: {
                "physical_clearance_time": None,
                "peak_node_people": 0.0,
                "peak_edge_people": 0.0,
                "peak_total_people": 0.0,
                "last_occupied_nodes": "",
                "last_occupied_edges": "",
            }
            for line in ALL_LINE_IDS
        },
    )

    node_people_by_line = {line: 0.0 for line in ALL_LINE_IDS}
    edge_people_by_line = {line: 0.0 for line in ALL_LINE_IDS}
    node_items_by_line = {line: {} for line in ALL_LINE_IDS}
    edge_items_by_line = {line: {} for line in ALL_LINE_IDS}
    occupied_until_by_line = {line: None for line in ALL_LINE_IDS}

    for node, data in G.nodes(data=True):
        if data.get("type") == "exit":
            continue
        people = float(data.get("people", 0.0) or 0.0)
        if people <= 1e-9:
            continue
        for line_id in node_line_ids.get(node, set()):
            if line_id not in node_people_by_line:
                continue
            node_people_by_line[line_id] += people
            node_items_by_line[line_id][node] = node_items_by_line[line_id].get(node, 0.0) + people
            occupied_until_by_line[line_id] = max(
                occupied_until_by_line[line_id] or current_time,
                current_time,
            )

    for item in G.graph.get("_transit_queue", []):
        depart_time = float(item.get("depart_time", 0.0) or 0.0)
        arrive_time = float(item.get("arrive_time", 0.0) or 0.0)
        if depart_time > current_time + 1e-9:
            continue
        if arrive_time <= current_time + 1e-9:
            continue
        amount = float(item.get("amount", 0.0) or 0.0)
        if amount <= 1e-9:
            continue
        u = item.get("u")
        v = item.get("v")
        edge_name = _edge_key(u, v)
        for line_id in edge_line_ids.get(edge_name, set()):
            if line_id not in edge_people_by_line:
                continue
            edge_people_by_line[line_id] += amount
            edge_items_by_line[line_id][edge_name] = edge_items_by_line[line_id].get(edge_name, 0.0) + amount
            occupied_until_by_line[line_id] = max(
                occupied_until_by_line[line_id] or arrive_time,
                arrive_time,
            )

    for line_id, stats in stats_by_line.items():
        node_people = node_people_by_line.get(line_id, 0.0)
        edge_people = edge_people_by_line.get(line_id, 0.0)
        total_people = node_people + edge_people
        stats["peak_node_people"] = max(float(stats.get("peak_node_people", 0.0)), node_people)
        stats["peak_edge_people"] = max(float(stats.get("peak_edge_people", 0.0)), edge_people)
        stats["peak_total_people"] = max(float(stats.get("peak_total_people", 0.0)), total_people)
        occupied_until = occupied_until_by_line.get(line_id)
        if occupied_until is None:
            continue
        previous = stats.get("physical_clearance_time")
        if previous is None or occupied_until >= float(previous) - 1e-9:
            stats["physical_clearance_time"] = occupied_until
            stats["last_occupied_nodes"] = _format_physical_occupancy_items(node_items_by_line[line_id])
            stats["last_occupied_edges"] = _format_physical_occupancy_items(edge_items_by_line[line_id])


def _get_node_series(metrics, node, key):
    node_series = metrics.get("node_series", {}).get(node, {})
    return (
        np.array(node_series.get("times", []), dtype=float),
        np.array(node_series.get(key, []), dtype=float),
    )


def _select_critical_queue_node(G, metrics, line_id):
    """为每条线路选一个最关键的排队节点，优先用传统算法下的队列累积。"""
    node_stats = metrics.get("node_stats", {})
    candidates = []

    for node in metrics.get("node_series", {}).keys():
        if not _is_queue_node(G, node):
            continue
        if line_id not in _infer_node_line_ids_strict(node):
            continue

        stat = node_stats.get(node, {})
        q_seconds = float(stat.get("queue_seconds", 0.0))
        peak_people = float(stat.get("peak_people", 0.0))
        candidates.append((q_seconds, peak_people, node))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def _smooth_display_series(values, window=5):
    series = pd.Series(values, dtype=float).replace(0.0, np.nan).interpolate(limit_direction="both")
    if window and window > 1:
        series = series.rolling(window=window, min_periods=1).mean()
    return series.to_numpy()


MONITORED_EDGE_TYPES = {
    "platform_zone_to_vertical",
    "platform_to_vertical",
    "vertical_to_gate",
    "gate_to_vertical",
    "gate_to_exit",
    "gate_to_virtual",
    "vertical_to_exit",
    "vertical_to_transfer",
    "vertical_to_virtual",
    "transfer_to_gate",
    "transfer_to_exit",
    "transfer_to_vertical",
    "transfer_to_virtual",
    "virtual_to_exit",
    "virtual_to_gate",
}


def _edge_key(u, v):
    return f"{u} -> {v}"


def _is_monitored_edge(data):
    edge_type = str(data.get("edge_type", "")).lower()
    if edge_type in EDGE_DENSITY_EXEMPT_TYPES:
        return False
    # Evaluation must cover every spatial edge that can physically contain
    # in-transit passengers.  MONITORED_EDGE_TYPES remains a plotting subset;
    # using it for exposure accounting omitted valid types such as hall_to_gate.
    return float(data.get("length", 0.0) or 0.0) > 0.0


def _edge_width_proxy(G, u, v):
    data = G[u][v]
    width_limit = data.get("width_limit")
    if width_limit is not None and float(width_limit) > 0:
        return float(width_limit)

    capacity = float(data.get("capacity", 0.0))
    if capacity > 0:
        return max(capacity / (5000.0 / 3600.0), 0.6)

    return 1.0


def _edge_effective_area(G, u, v):
    data = G[u][v]
    cached_area = data.get("_effective_area_cache")
    if cached_area is not None:
        return float(cached_area)
    explicit_area = float(data.get("edge_area", 0.0) or 0.0)
    if explicit_area > 0:
        area = max(explicit_area, 0.1)
    else:
        length = max(float(data.get("length", 0.0)), 0.5)
        width = max(_edge_width_proxy(G, u, v), 0.1)
        area = max(length * width, 0.1)
    data["_effective_area_cache"] = area
    return area


def _edge_active_passengers(G, u, v, current_time=None):
    if current_time is None:
        current_time = float(G.graph.get("_sim_time", 0.0))
    total = 0.0
    for item in G.graph.get("_transit_queue", []):
        if item.get("u") != u or item.get("v") != v:
            continue
        if item.get("depart_time", 0.0) > current_time + 1e-9:
            continue
        if item.get("arrive_time", 0.0) <= current_time + 1e-9:
            continue
        total += float(item.get("amount", 0.0))
    return total


def _edge_density(G, u, v, current_time=None):
    edge_type = str(G[u][v].get("edge_type", "")).lower()
    if edge_type in EDGE_DENSITY_EXEMPT_TYPES:
        return 0.0
    if current_time is None:
        simulation_time = float(G.graph.get("_sim_time", 0.0))
        refreshed_at = G.graph.get("_runtime_density_time")
        if refreshed_at is not None and abs(float(refreshed_at) - simulation_time) <= 1e-9:
            # Zero is a valid cached density. The former ``> 0`` check caused
            # every empty edge-cost query to rescan the entire transit queue.
            return float(G[u][v].get("runtime_density", 0.0) or 0.0)
    return _edge_active_passengers(G, u, v, current_time) / _edge_effective_area(G, u, v)


def _density_adjusted_speed(speed_cap, density):
    speed_cap = max(float(speed_cap), 0.0)
    if density <= 0:
        return speed_cap
    return max(min(speed_cap, spr.paper_speed_from_density(density)), 0.0)


def _edge_effective_flow_capacity(G, u, v):
    """Density-aware admission capacity consistent with the Fruin speed law."""
    capacity = float(G[u][v].get("capacity", 0.0))
    if (
        not G.graph.get("density_dependent_flow", False)
        or capacity <= 0.0
        or math.isinf(capacity)
    ):
        return capacity

    edge_type = str(G[u][v].get("edge_type", "")).lower()
    if edge_type in EDGE_DENSITY_EXEMPT_TYPES:
        return capacity

    width = _edge_width_proxy(G, u, v)
    density = _edge_density(G, u, v)
    if density <= spr.PAPER_DENSITY_FREE:
        return capacity
    speed = spr.paper_speed_from_density(density)
    if speed <= 0.0:
        return 0.0
    return min(capacity, max(density * speed * width, 0.0))


def _refresh_edge_runtime_densities(G, current_time=None):
    if current_time is None:
        current_time = float(G.graph.get("_sim_time", 0.0))
    for _, _, data in G.edges(data=True):
        data["runtime_passengers"] = 0.0
        data["runtime_density"] = 0.0

    for item in G.graph.get("_transit_queue", []):
        u = item.get("u")
        v = item.get("v")
        if u not in G.nodes or v not in G.nodes or not G.has_edge(u, v):
            continue
        if item.get("depart_time", 0.0) > current_time + 1e-9:
            continue
        if item.get("arrive_time", 0.0) <= current_time + 1e-9:
            continue
        G[u][v]["runtime_passengers"] += float(item.get("amount", 0.0))

    for u, v, data in G.edges(data=True):
        edge_type = str(data.get("edge_type", "")).lower()
        if edge_type in EDGE_DENSITY_EXEMPT_TYPES:
            continue
        data["runtime_density"] = float(data.get("runtime_passengers", 0.0)) / _edge_effective_area(G, u, v)
    G.graph["_runtime_density_time"] = float(current_time)


def _select_top_edges(edge_stats, top_k=12):
    rows = []
    for edge_key, stat in edge_stats.items():
        rows.append((float(stat.get("flow_total", 0.0)), float(stat.get("peak_passengers", 0.0)), edge_key))
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [edge_key for _, _, edge_key in rows[:top_k]]


def _select_top_queue_nodes(metrics, top_k=8):
    rows = []
    for node, stat in metrics.get("node_stats", {}).items():
        if stat.get("queue_seconds", 0.0) <= 0:
            continue
        rows.append((float(stat.get("queue_seconds", 0.0)), float(stat.get("peak_people", 0.0)), node))
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [node for _, _, node in rows[:top_k]]


def _edge_line_ids(G, edge_key):
    try:
        u, v = [part.strip() for part in edge_key.split("->", 1)]
    except ValueError:
        return set()
    return _infer_node_line_ids_strict(u) | _infer_node_line_ids_strict(v)


def _edge_line_ids_from_key(edge_key):
    try:
        u, v = [part.strip() for part in edge_key.split("->", 1)]
    except ValueError:
        return set()
    return _infer_node_line_ids_strict(u) | _infer_node_line_ids_strict(v)


def _select_representative_edges_for_line(G, metrics, line_id, top_k=2):
    def _safe_nanstd(arr):
        arr = np.asarray(arr, dtype=float)
        arr = arr[~np.isnan(arr)]
        if arr.size <= 1:
            return 0.0
        return float(np.std(arr))

    rows = []
    for edge_key, series in metrics.get("edge_series", {}).items():
        if line_id not in _edge_line_ids(G, edge_key):
            continue
        passengers = np.array(series.get("passengers", []), dtype=float)
        speed = np.array(series.get("speed", []), dtype=float)
        if passengers.size == 0:
            continue
        valid_passengers = passengers[~np.isnan(passengers)]
        if valid_passengers.size == 0:
            continue

        peak_passengers = float(np.nanmax(valid_passengers))
        mean_passengers = float(np.nanmean(valid_passengers))
        passenger_std = _safe_nanstd(valid_passengers)
        speed_std = _safe_nanstd(speed)
        finite_speed = speed[np.isfinite(speed)]
        min_speed = float(np.nanmin(finite_speed)) if finite_speed.size > 0 else 1.427
        active_ratio = float(np.mean(valid_passengers > 0.5))

        # 优先选“真正有载荷、且会发生拥挤波动”的链路，而不是自由流边
        if peak_passengers < 1.0 and mean_passengers < 0.5:
            continue

        line_count = len(_edge_line_ids(G, edge_key))
        multi_line_penalty = 0.75 if line_count > 1 else 1.0

        score = (
            2.2 * peak_passengers
            + 1.4 * mean_passengers
            + 6.0 * passenger_std
            + 10.0 * speed_std
            + 20.0 * max(0.0, 1.427 - min_speed)
            + 2.0 * active_ratio
        ) * multi_line_penalty
        rows.append((score, peak_passengers, mean_passengers, line_count, edge_key))

    if any(item[3] == 1 for item in rows):
        rows = [item for item in rows if item[3] == 1]
    rows.sort(key=lambda x: x[0], reverse=True)
    return [edge_key for _, _, _, _, edge_key in rows[:top_k]]


def _select_snapshot_time_for_edges(metrics, edge_keys):
    if not edge_keys:
        return float(metrics.get("time", 0.0))

    ref_times = None
    for edge_key in edge_keys:
        series = metrics.get("edge_series", {}).get(edge_key, {})
        times = np.array(series.get("times", []), dtype=float)
        if times.size > 0:
            ref_times = times
            break

    if ref_times is None or ref_times.size == 0:
        return float(metrics.get("time", 0.0))

    total = np.zeros_like(ref_times, dtype=float)
    for edge_key in edge_keys:
        series = metrics.get("edge_series", {}).get(edge_key, {})
        times = np.array(series.get("times", []), dtype=float)
        passengers = np.array(series.get("passengers", []), dtype=float)
        if times.size == 0 or passengers.size == 0:
            continue
        if times.size != ref_times.size or not np.allclose(times, ref_times):
            passengers = np.interp(ref_times, times, np.nan_to_num(passengers, nan=0.0), left=0.0, right=0.0)
        else:
            passengers = np.nan_to_num(passengers, nan=0.0)
        total += passengers

    return float(ref_times[int(np.argmax(total))])


def _select_representative_nodes_for_line(G, metrics, line_id, top_k=2):
    rows = []
    for node in metrics.get("node_series", {}).keys():
        if line_id not in _infer_node_line_ids_strict(node):
            continue
        stat = metrics.get("node_stats", {}).get(node, {})
        q_seconds = float(stat.get("queue_seconds", 0.0))
        peak_people = float(stat.get("peak_people", 0.0))
        if q_seconds <= 0 and peak_people <= 0:
            continue
        rows.append((q_seconds + 0.25 * peak_people, node))
    rows.sort(key=lambda x: x[0], reverse=True)
    return [node for _, node in rows[:top_k]]


def _select_global_critical_queue_node(metrics):
    nodes = _select_top_queue_nodes(metrics, top_k=1)
    return nodes[0] if nodes else None


def _nearest_index(times, target_time):
    if len(times) == 0:
        return None
    times = np.asarray(times, dtype=float)
    return int(np.argmin(np.abs(times - float(target_time))))


def _capture_edge_snapshot(G, current_time, monitored_edges):
    transit_queue = G.graph.get("_transit_queue", [])
    monitored = set(monitored_edges)
    snapshot = {
        edge_key: {"passengers": 0.0, "speed_sum": 0.0, "line_shares": {line: 0.0 for line in ALL_LINE_IDS}}
        for edge_key in monitored
    }

    for item in transit_queue:
        if item.get("depart_time", 0.0) > current_time + 1e-9:
            continue
        if item.get("arrive_time", 0.0) <= current_time + 1e-9:
            continue

        u = item.get("u")
        v = item.get("v")
        edge_key = _edge_key(u, v)
        if edge_key not in snapshot:
            continue

        amount = float(item.get("amount", 0.0))
        if amount <= 0:
            continue

        travel_time = float(item["travel_time"]) if "travel_time" in item else _edge_travel_time(G, u, v)
        travel_time = max(travel_time, 0.001)
        length = max(float(G[u][v].get("length", 0.0)), 0.0)
        speed = length / travel_time if length > 0 else 0.0

        snapshot[edge_key]["passengers"] += amount
        snapshot[edge_key]["speed_sum"] += amount * speed
        for line_id, flow in item.get("line_shares", {}).items():
            if line_id in snapshot[edge_key]["line_shares"]:
                snapshot[edge_key]["line_shares"][line_id] += float(flow)

    return snapshot


def _update_edge_state_diagnostics(G, metrics, current_time, scheduled_moves):
    """Observe accepted transit without changing movement or capacity state.

    Batch travel times are fixed when the batch enters an edge.  Exact transit
    and low-speed person-seconds are therefore accumulated once from accepted
    batches.  Density-band person-seconds use the formal one-second simulation
    state after the current step's accepted moves have entered transit.
    """
    stats = metrics.get("edge_state_diagnostics", {})
    for item in scheduled_moves:
        u = item.get("u")
        v = item.get("v")
        edge_key = _edge_key(u, v)
        stat = stats.get(edge_key)
        if stat is None:
            continue
        amount = max(float(item.get("amount", 0.0)), 0.0)
        travel_time = max(float(item.get("travel_time", 0.0)), 0.0)
        if amount <= 0.0 or travel_time <= 0.0:
            continue
        length = max(float(G[u][v].get("length", 0.0)), 0.0)
        speed = length / travel_time if length > 0.0 else 0.0
        person_seconds = amount * travel_time
        stat["cumulative_in_transit_person_seconds"] += person_seconds
        stat["minimum_speed_m_per_s"] = (
            speed
            if stat["minimum_speed_m_per_s"] is None
            else min(float(stat["minimum_speed_m_per_s"]), speed)
        )
        if speed < 0.3:
            stat["speed_below_0_3_person_seconds"] += person_seconds
        if speed < 0.1:
            stat["speed_below_0_1_person_seconds"] += person_seconds
        if speed < 0.05:
            stat["speed_below_0_05_person_seconds"] += person_seconds
        for line_id, line_people in item.get("line_shares", {}).items():
            line_people = max(float(line_people), 0.0)
            if line_people <= 0.0:
                continue
            line_stat = metrics[
                "edge_low_speed_person_seconds_by_line"
            ].setdefault(
                line_id,
                {
                    "cumulative_in_transit_person_seconds": 0.0,
                    "speed_below_0_3_person_seconds": 0.0,
                    "speed_below_0_1_person_seconds": 0.0,
                    "speed_below_0_05_person_seconds": 0.0,
                },
            )
            line_person_seconds = line_people * travel_time
            line_stat[
                "cumulative_in_transit_person_seconds"
            ] += line_person_seconds
            if speed < 0.3:
                line_stat[
                    "speed_below_0_3_person_seconds"
                ] += line_person_seconds
            if speed < 0.1:
                line_stat[
                    "speed_below_0_1_person_seconds"
                ] += line_person_seconds
            if speed < 0.05:
                line_stat[
                    "speed_below_0_05_person_seconds"
                ] += line_person_seconds

    edge_keys = list(stats)
    snapshot = _capture_edge_snapshot(G, current_time, edge_keys)
    any_in_transit = False
    for edge_key, state in snapshot.items():
        passengers = max(float(state.get("passengers", 0.0)), 0.0)
        if passengers <= 0.0:
            continue
        stat = stats[edge_key]
        area = float(stat["effective_area_m2"])
        density = (
            passengers / area
            if math.isfinite(area) and area > 0.0
            else 0.0
        )
        stat["maximum_density_p_per_m2"] = max(
            float(stat["maximum_density_p_per_m2"]),
            density,
        )
        stat["maximum_in_transit_people"] = max(
            float(stat["maximum_in_transit_people"]),
            passengers,
        )
        stat["last_occupied_time_seconds"] = float(current_time)
        stat["last_observed_in_transit_people"] = passengers
        density_person_seconds = passengers * DELTA_T
        if 2.0 <= density < 3.0:
            stat["density_2_0_to_3_0_person_seconds"] += density_person_seconds
        elif 3.0 <= density < 3.5:
            stat["density_3_0_to_3_5_person_seconds"] += density_person_seconds
        elif 3.5 <= density < 4.0:
            stat["density_3_5_to_4_0_person_seconds"] += density_person_seconds
        any_in_transit = True

    if any_in_transit:
        metrics["last_in_transit_snapshot_time_seconds"] = float(current_time)


def _apply_node_disruption(G, node, factor=0.35):
    """节点中断：将目标节点及其相邻连边完全切断。"""
    if node not in G.nodes:
        return
    G.nodes[node]["capacity"] = 0.0
    G.nodes[node]["blocked"] = True

    # 原文的设定是“节点中断 + 与该节点相连的连接中断”，这里直接移除入边/出边。
    for pred, _ in list(G.in_edges(node)):
        if G.has_edge(pred, node):
            G.remove_edge(pred, node)
    for _, succ in list(G.out_edges(node)):
        if G.has_edge(node, succ):
            G.remove_edge(node, succ)
    spr.invalidate_aa_routing_caches(G)


def _collect_line_queue_nodes(G, metrics, line_id):
    """收集某条线对应的所有排队节点，按排队累计从高到低排序。"""
    nodes = []
    node_stats = metrics.get("node_stats", {})
    for node in metrics.get("node_series", {}).keys():
        if not _is_queue_node(G, node):
            continue
        if line_id not in _infer_node_line_ids_strict(node):
            continue
        stat = node_stats.get(node, {})
        q_seconds = float(stat.get("queue_seconds", 0.0))
        peak_people = float(stat.get("peak_people", 0.0))
        nodes.append((q_seconds, peak_people, node))

    nodes.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [node for _, _, node in nodes]


def _select_critical_node_for_line(G, metrics, line_id):
    nodes = _collect_line_queue_nodes(G, metrics, line_id)
    return nodes[0] if nodes else None


def _select_article_links(metrics, top_k=16):
    """按论文 Fig.13/Fig.15 的口径，选出全局最关键的 link。"""
    rows = []
    for edge_key, series in metrics.get("edge_series", {}).items():
        passengers = np.array(series.get("passengers", []), dtype=float)
        speed = np.array(series.get("speed", []), dtype=float)
        if passengers.size == 0:
            continue

        valid_passengers = passengers[np.isfinite(passengers)]
        if valid_passengers.size == 0:
            continue
        finite_speed = speed[np.isfinite(speed)]
        if finite_speed.size < 8:
            continue

        peak_passengers = float(np.nanmax(valid_passengers))
        mean_passengers = float(np.nanmean(valid_passengers))
        passenger_std = float(np.nanstd(valid_passengers)) if valid_passengers.size > 1 else 0.0
        speed_std = float(np.nanstd(finite_speed)) if finite_speed.size > 1 else 0.0
        min_speed = float(np.nanmin(finite_speed)) if finite_speed.size > 0 else 1.427
        speed_range = float(np.nanmax(finite_speed) - np.nanmin(finite_speed)) if finite_speed.size > 0 else 0.0
        active_ratio = float(np.mean(valid_passengers > 0.5))

        if peak_passengers < 1.0 and mean_passengers < 0.5:
            continue
        # 只保留真正“会动”的 link，避免 Fig.13 里出现几乎贴自由流的直线。
        if speed_range < 0.05 and passenger_std < 0.5 and mean_passengers < 1.0:
            continue

        score = (
            2.3 * peak_passengers
            + 1.1 * mean_passengers
            + 4.8 * passenger_std
            + 12.0 * speed_std
            + 24.0 * speed_range
            + 16.0 * max(0.0, 1.427 - min_speed)
            + 2.0 * active_ratio
        )
        rows.append((score, peak_passengers, edge_key))

    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [edge_key for _, _, edge_key in rows[:top_k]]


def _select_article_nodes(metrics, top_k=16):
    """按论文 Fig.14 的口径，选出全局最关键的 queue nodes。"""
    rows = []
    for node, series in metrics.get("node_series", {}).items():
        queue = np.array(series.get("queue", []), dtype=float)
        if queue.size == 0:
            continue
        valid_queue = queue[np.isfinite(queue)]
        if valid_queue.size == 0:
            continue

        stat = metrics.get("node_stats", {}).get(node, {})
        q_seconds = float(stat.get("queue_seconds", 0.0))
        peak_people = float(stat.get("peak_people", 0.0))
        queue_std = float(np.nanstd(valid_queue)) if valid_queue.size > 1 else 0.0
        if q_seconds <= 0 and peak_people <= 0:
            continue

        score = 1.2 * q_seconds + 1.0 * peak_people + 4.0 * queue_std
        rows.append((score, q_seconds, node))

    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [node for _, _, node in rows[:top_k]]


def _select_snapshot_edges_for_comparison(base_metrics, disrupted_metrics, snapshot_time, top_k=14, focus_line_ids=None):
    """按 Fig.15 的口径，选出在观察时刻真正有客流、且正常/扰动差异最大的 link。

    如果提供 focus_line_ids，则优先保留与故障设施所在线路相关的 link，
    避免全局筛选把局部故障效应冲淡。
    """
    rows = []
    base_series_map = base_metrics.get("edge_series", {})
    dis_series_map = disrupted_metrics.get("edge_series", {}) if disrupted_metrics else {}
    all_edges = sorted(set(base_series_map.keys()) | set(dis_series_map.keys()))
    focus_line_ids = set(focus_line_ids or [])

    for edge_key in all_edges:
        if focus_line_ids:
            edge_line_ids = _edge_line_ids_from_key(edge_key)
            if edge_line_ids.isdisjoint(focus_line_ids):
                continue
        base_series = base_series_map.get(edge_key, {})
        dis_series = dis_series_map.get(edge_key, {})
        base_times = np.array(base_series.get("times", []), dtype=float)
        dis_times = np.array(dis_series.get("times", []), dtype=float)
        base_pass = np.array(base_series.get("passengers", []), dtype=float)
        dis_pass = np.array(dis_series.get("passengers", []), dtype=float)

        if base_times.size == 0 and dis_times.size == 0:
            continue

        idx_base = _nearest_index(base_times, snapshot_time) if base_times.size > 0 else None
        idx_dis = _nearest_index(dis_times, snapshot_time) if dis_times.size > 0 else None

        base_val = float(base_pass[idx_base]) if idx_base is not None and idx_base < len(base_pass) else 0.0
        dis_val = float(dis_pass[idx_dis]) if idx_dis is not None and idx_dis < len(dis_pass) else 0.0
        combined = base_val + dis_val
        delta = abs(dis_val - base_val)

        # 观察时刻没有客流的边不进入 Fig.15。
        if combined < 0.5:
            continue

        rows.append((delta, combined, edge_key))

    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [edge_key for _, _, edge_key in rows[:top_k]]


def _select_representative_snapshot_time_for_comparison(base_metrics, disrupted_metrics, edge_keys):
    """
    给 Fig.15 选一个差异最大时刻：
    - 同一组 link 在正常/扰动两边都要有流量
    - 优先挑“正常/扰动差异最大、同时不至于空载”的活跃时刻

    这比把 period 固定成 15 min 更符合疏散场景中的故障影响展示。
    """
    if not edge_keys:
        return float(base_metrics.get("time", 0.0))

    base_series_map = base_metrics.get("edge_series", {})
    dis_series_map = disrupted_metrics.get("edge_series", {}) if disrupted_metrics else {}
    candidate_times = []

    for edge_key in edge_keys:
        for series_map in (base_series_map, dis_series_map):
            times = np.array(series_map.get(edge_key, {}).get("times", []), dtype=float)
            if times.size > 0:
                candidate_times.append(times)

    if not candidate_times:
        return float(base_metrics.get("time", 0.0))

    ref_times = np.unique(np.concatenate(candidate_times))
    best_time = float(ref_times[0])
    best_score = -1.0

    for t in ref_times:
        base_total = 0.0
        dis_total = 0.0
        for edge_key in edge_keys:
            base_series = base_series_map.get(edge_key, {})
            dis_series = dis_series_map.get(edge_key, {})

            base_times = np.array(base_series.get("times", []), dtype=float)
            dis_times = np.array(dis_series.get("times", []), dtype=float)
            base_pass = np.array(base_series.get("passengers", []), dtype=float)
            dis_pass = np.array(dis_series.get("passengers", []), dtype=float)

            idx_base = _nearest_index(base_times, t) if base_times.size > 0 else None
            idx_dis = _nearest_index(dis_times, t) if dis_times.size > 0 else None

            if idx_base is not None and idx_base < len(base_pass):
                base_total += float(base_pass[idx_base])
            if idx_dis is not None and idx_dis < len(dis_pass):
                dis_total += float(dis_pass[idx_dis])

        combined = base_total + dis_total
        delta = abs(dis_total - base_total)
        # 差异优先，但保留一个轻微的总流量加权，避免选到噪声型低流时刻。
        score = delta + 0.08 * combined
        if combined < 1.0:
            continue
        if score > best_score:
            best_score = score
            best_time = float(t)

    return best_time


def _aggregate_line_node_series(G, metrics, line_id, key, normalize_by_area=False):
    """把某条线的多个排队节点时间序列聚合成一条均值曲线。"""
    nodes = _collect_line_queue_nodes(G, metrics, line_id)
    if not nodes:
        return np.array([]), np.array([]), []

    ref_node = nodes[0]
    ref_times = np.array(metrics.get("node_series", {}).get(ref_node, {}).get("times", []), dtype=float)
    if ref_times.size == 0:
        return np.array([]), np.array([]), nodes

    stack = []
    for node in nodes:
        node_series = metrics.get("node_series", {}).get(node, {})
        values = np.array(node_series.get(key, []), dtype=float)
        if values.size == 0:
            continue
        if normalize_by_area:
            if spr.is_capacity_service_node(G, node):
                denom = spr.node_service_capacity(G, node) * spr.SERVICE_QUEUE_HORIZON_SECONDS
            else:
                denom = max(float(G.nodes[node].get("area", 1.0)), 0.001)
            values = values / max(denom, 0.001)
        stack.append(values[:ref_times.size])

    if not stack:
        return ref_times, np.full(ref_times.shape, np.nan), nodes

    matrix = np.vstack([row if row.size == ref_times.size else np.pad(row, (0, max(0, ref_times.size - row.size)), constant_values=np.nan)[:ref_times.size] for row in stack])
    valid_counts = np.sum(~np.isnan(matrix), axis=0)
    summed = np.nansum(matrix, axis=0)
    agg = np.divide(summed, valid_counts, out=np.full(ref_times.shape, np.nan), where=valid_counts > 0)

    return ref_times, agg, nodes


# 🌟 从配置文件导入纯数据
from lines_config import (
    NODES_DATA,
    EDGES_DATA,
    STATION_LEVELS,
    PLATFORM_VERTICAL_SPECS,
    PLATFORM_WAITING_ZONE_SPECS,
    PRECALCULATED_PLATFORM_DISTS,
    OBSTACLE_AREAS,
)
# ==============================================================================
# 0. 中文支持与全局参数
# ==============================================================================
system_name = platform.system()
if system_name == "Windows":
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
elif system_name == "Darwin":
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS']
else:
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

MODE = "EVACUATION"
DELTA_T = 1.0

# 对照开关：Improved 基线是否在闸机入边加 Q/μ 排队成本（即 "Improved+Q"）。
# 默认 False = 正式 Improved 基线不包含 Q/μ；需要做消融时显式设为 True。
# 用于归因 mode4 中 Improved 因 Q/μ「用当前队列滞后一步」而羊群涌入慢闸机的问题。
# 显式 G.graph["improved_gate_queue_term"] 仍可逐图覆盖此默认。
IMPROVED_GATE_QUEUE_TERM = (
    os.environ.get("IMPROVED_GATE_QUEUE_TERM", "0").strip().lower()
    not in {"0", "false", "no", "off"}
)
# Formal Improved uses the literature density-speed travel-time term. True is
# reserved for the shared-travel-time attribution variant.
IMPROVED_SHARED_TRAVEL_TIME = False
METRIC_SAMPLE_INTERVAL_SECONDS = 2.0
PROFILE_AA = False
FAST_EXACT_AA = True
COLLECT_DETAILED_SERIES_DEFAULT = False
PATHFINDER_CAPACITY_CALIBRATION_FACTOR = 1.0

ALL_LINE_IDS = ["L2", "L7", "L16", "L18", "Maglev"]
MODERATE_CONGESTION_DENSITY_THRESHOLD = 3.0
# Diagnostic bands inside the existing Fruin 4.0 p/m² jam boundary. 3.5 is
# an internal reporting threshold, not a new fundamental-diagram parameter.
SEVERE_CONGESTION_DENSITY_THRESHOLD = 3.5
EDGE_DENSITY_EXEMPT_TYPES = {"car_to_door", "train_door"}

SOURCE_GROUP_SUFFIXES = {
    "train_1": "train1",
    "train_2": "train2",
    "platform_waiting": "platform",
    "hall_people": "hall",
    "transfer_people": "transfer",
}

SOURCE_GROUP_LABELS = {
    "train1": "train_1",
    "train2": "train_2",
    "platform": "platform_waiting",
    "hall": "hall_people",
    "transfer": "transfer_people",
}

HALL_STAGING_SPECS = {
    "L7": [
        {
            "name": "VN_L7_Hall_Arrival",
            "targets": ["Gate_L7_N_West", "Gate_L7_N_Mid", "Gate_L7_N_East", "Gate_L7_West_Vert"],
            "manual_area": 90.0,
        }
    ],
    "L2": [
        {
            "name": "VN_L2_Hall_Arrival",
            "targets": ["Gate_L2_N_West", "Gate_L2_N_East", "Gate_L2_S_West", "Gate_L2_S_East"],
            "manual_area": 120.0,
        }
    ],
    "L16": [
        {
            "name": "VN_L16_Hall_Arrival",
            "targets": ["Gate_L16_N1", "Gate_L16_N2", "Gate_L16_S1", "Gate_L16_S2"],
            "manual_area": 110.0,
        }
    ],
    "L18": [
        {
            "name": "VN_L18_Hall_Arrival_Base",
            "targets": ["VN_L18_Hall_Split_A", "VN_L18_Hall_Split_B"],
            "manual_area": 250.0,
        }
    ],
}
HALL_STAGING_LENGTH_SCALE_BY_LINE = {
    # These three staging nodes are generated from CAD coordinates at runtime,
    # so their inferred hall-to-gate lengths require the common CAD-to-metre
    # conversion.  L18 uses explicit pre-built hall edges and must not be
    # scaled a second time.
    "L7": 0.01,
    "L2": 0.01,
    "L16": 0.01,
}

L7_HALL_COMMON_DECISION_UPSTREAMS = (
    "Stair_L7_1",
    "Escalator_L7_up1",
    "Stair_L7_2",
    "Stair_L7_3",
    "Escalator_L7_down1",
)


EVAC_STAGE_RANKS = {
    "platform_train": 0,
    "vertical_transfer": 1,
    "hall_distribution": 2,
    "gate_choice": 3,
    "post_gate_exit": 4,
}

AA_LEGAL_DOWNSTREAM_STAGE_TRANSITIONS = {
    (
        "VN_L18_to_L16_Hall_Arrival",
        "VN_L16_to_Maglev_Entrance",
    ),
}


def _aa_node_evac_stage(node, data):
    name = str(node)
    lowered_name = name.lower()
    node_type = str(data.get("type", "")).strip().lower()
    if node_type == "exit":
        return "post_gate_exit"
    if node_type.startswith("gate") or "gate" in node_type:
        return "gate_choice"
    if (
        node_type in {
            "train", "train_car", "platform", "platform_waiting_zone"
        }
        or lowered_name.startswith(("train_", "platform_"))
    ):
        return "platform_train"
    if "hall_arrival" in lowered_name or "split" in lowered_name:
        return "hall_distribution"
    if (
        node_type in {"stair", "escalator", "transfer", "passageway"}
        or "stair" in lowered_name
        or "escalator" in lowered_name
        or "transfer" in lowered_name
        or "passageway" in lowered_name
        or "bridge" in lowered_name
        or "_to_" in lowered_name
    ):
        return "vertical_transfer"
    if (
        "corner" in lowered_name
        or "exit" in lowered_name
        or "entrance" in lowered_name
    ):
        return "post_gate_exit"
    return "hall_distribution"


def _is_l2_upstream_release_node(G, node):
    """Return whether *node* is a real L2 upstream release position.

    Only passengers still physically at a train/platform release position may
    use this scope. The routing-decision check is applied by the scope
    annotator because it needs the graph's actual downstream branches.
    """
    if node not in G.nodes:
        return False
    data = G.nodes[node]
    line_id = data.get("line_id")
    if line_id != "L2" and not str(node).startswith(("Train_L2", "Platform_L2")):
        return False
    if data.get("evac_stage") != "platform_train":
        return False
    return str(data.get("type", "")).strip().lower() in {
        "platform_waiting_zone",
        "train_car",
        "train",
        "platform",
    }


def _annotate_aa_evacuation_stages_and_replan_scope(G):
    """Add AA-only monotone evacuation stages and explicit decision scope."""
    for node, data in G.nodes(data=True):
        stage = _aa_node_evac_stage(node, data)
        data["evac_stage"] = stage
        data["evac_stage_rank"] = EVAC_STAGE_RANKS[stage]
        data["aa_active_replan_allowed"] = False
        data["aa_replan_successors"] = ()
        data["aa_replan_successor_groups"] = {}
        data["aa_replan_return_blocked"] = False
        data.pop("aa_l2_upstream_release_node", None)
        data.pop("aa_current_gate", None)
        data.pop("aa_alternative_target_resources", None)
        data.pop("aa_configured_alternative_target_resources", None)

    # Entering this downstream transfer branch is a commitment: the entrance
    # and its internal passageway are not active-replanning locations.
    maglev_branch_nodes = {
        "VN_L16_to_Maglev_Entrance",
        "Transfer_L16_Maglev_Passageway",
    }
    for node in maglev_branch_nodes:
        if node in G.nodes:
            G.nodes[node]["aa_replan_return_blocked"] = True

    exits = {
        node for node, data in G.nodes(data=True)
        if data.get("type") == "exit"
    }
    exit_reachable = set(exits)
    for exit_node in exits:
        exit_reachable.update(nx.ancestors(G, exit_node))

    allowed_count = 0
    blocked_nondecision_count = 0
    blocked_upstream_stage_count = 0
    blocked_single_successor_count = 0
    gate_approach_count = 0
    l2_upstream_release_count = 0
    missing_gate_switch_connections = []
    l7_to_l2_node = "VN_L7toL2_Hall_Arrival"
    l7_to_l2_gates = {
        "Gate_L2_N_West",
        "Gate_L2_N_East",
        "Gate_L2_S_West",
        "Gate_L2_S_East",
    }
    gate_groups = {
        gate: tuple(items)
        for group_name, items in NODES_DATA.items()
        if group_name.endswith("_GATES") and isinstance(items, dict)
        for gate in items
    }

    for node, data in G.nodes(data=True):
        name = str(node)
        lowered_name = name.lower()
        is_gate_queue = (
            str(data.get("type", "")).strip().lower() == "queue_area"
            or bool(data.get("queue_for_gate"))
        )
        is_gate_approach = _is_gate_approach_node(G, node)
        if is_gate_approach:
            current_gate = _gate_for_approach_node(G, node)
            if current_gate in gate_groups:
                configured_alternative_gates = tuple(
                    sorted(
                        gate
                        for gate in gate_groups[current_gate]
                        if gate != current_gate
                    )
                )
                configured_set = set(configured_alternative_gates)
                alternative_gates = tuple(sorted({
                    target_gate
                    for successor in G.successors(node)
                    if G[node][successor].get("gate_switch_only")
                    and _is_gate_approach_node(G, successor)
                    for target_gate in (_gate_for_approach_node(G, successor),)
                    if target_gate in configured_set
                }))
            else:
                # Preserve explicitly constructed mechanism-test graphs that do
                # not use the formal station configuration.
                configured_alternative_gates = tuple(sorted(
                    gate
                    for gate in G.graph.get("gate_queue_area_nodes", {})
                    if gate != current_gate
                ))
                alternative_gates = configured_alternative_gates
            data["evac_stage"] = "gate_choice"
            data["evac_stage_rank"] = EVAC_STAGE_RANKS["gate_choice"]
            data["aa_selection_stage"] = True
            data["aa_active_replan_allowed"] = True
            data["aa_current_gate"] = current_gate
            data["aa_configured_alternative_target_resources"] = (
                configured_alternative_gates
            )
            data["aa_alternative_target_resources"] = alternative_gates
            candidates = []
            successor_groups = {}
            parallel_group = f"{node}:gate_switch_choices"
            for successor in G.successors(node):
                if successor not in exit_reachable:
                    continue
                candidates.append(successor)
                successor_groups[successor] = parallel_group
                G[node][successor]["aa_parallel_choice_group"] = parallel_group
            data["aa_replan_successors"] = tuple(candidates)
            data["aa_replan_successor_groups"] = successor_groups
            gate_approach_count += 1
            allowed_count += 1
            if len(candidates) < 2 and configured_alternative_gates:
                for target_gate in configured_alternative_gates:
                    missing_gate_switch_connections.append({
                        "approach_node": node,
                        "current_gate": current_gate,
                        "target_gate": target_gate,
                        "outgoing_successors": tuple(G.successors(node)),
                        "direct_edge_exists": G.has_edge(node, target_gate),
                        "length_m": None,
                        "width_m": data.get("width"),
                    })
            continue
        if _is_l2_upstream_release_node(G, node) and is_routing_decision_node(G, node):
            options = routing_decision_options(G, node)
            candidates = []
            signatures = set()
            for successor, signature in options:
                if successor not in exit_reachable:
                    continue
                current_rank = int(data["evac_stage_rank"])
                successor_rank = int(G.nodes[successor]["evac_stage_rank"])
                if successor_rank < current_rank:
                    continue
                candidates.append(successor)
                signatures.add(tuple(signature))
            if len(candidates) >= 2 and len(signatures) >= 2:
                parallel_group = f"{node}:L2_upstream_release_choices"
                successor_groups = {}
                for successor in candidates:
                    successor_groups[successor] = parallel_group
                    G[node][successor][
                        "aa_parallel_choice_group"
                    ] = parallel_group
                data["aa_selection_stage"] = True
                data["aa_l2_upstream_release_node"] = True
                data["aa_active_replan_allowed"] = True
                data["aa_replan_successors"] = tuple(candidates)
                data["aa_replan_successor_groups"] = successor_groups
                allowed_count += 1
                l2_upstream_release_count += 1
                continue
        is_named_decision = (
            "hall_arrival" in lowered_name
            or "split" in lowered_name
        ) and "corner" not in lowered_name
        if not is_named_decision:
            blocked_nondecision_count += 1
            continue

        current_rank = int(data["evac_stage_rank"])
        candidates = []
        upstream_blocked_here = False
        for successor in G.successors(node):
            if successor not in exit_reachable:
                continue
            successor_rank = int(G.nodes[successor]["evac_stage_rank"])
            transition = (node, successor)
            legal_downstream_transition = (
                transition in AA_LEGAL_DOWNSTREAM_STAGE_TRANSITIONS
            )
            if successor_rank < current_rank and not legal_downstream_transition:
                upstream_blocked_here = True
                continue
            if legal_downstream_transition:
                G[node][successor][
                    "aa_stage_transition"
                ] = "downstream_transfer_branch"
                G[node][successor]["aa_commits_downstream_branch"] = True
            if successor_rank == current_rank:
                # Same-stage movement is allowed only when this explicit
                # decision node defines the parallel-choice group.
                G[node][successor]["aa_parallel_choice_group"] = str(node)
            candidates.append(successor)

        if node == l7_to_l2_node:
            candidates = [
                successor for successor in candidates
                if successor in l7_to_l2_gates
            ]
        if upstream_blocked_here:
            blocked_upstream_stage_count += 1
        if len(candidates) < 2:
            blocked_single_successor_count += 1
            continue

        successor_groups = {}
        if node == "VN_L18_to_L16_Hall_Arrival":
            l16_gate_group = f"{node}:L16_parallel_gates"
            maglev_branch_group = f"{node}:Maglev_transfer_branch"
            for successor in candidates:
                if successor == "VN_L16_to_Maglev_Entrance":
                    group = maglev_branch_group
                    G[node][successor][
                        "aa_downstream_branch_group"
                    ] = group
                    G[node][successor].pop(
                        "aa_parallel_choice_group", None
                    )
                else:
                    group = l16_gate_group
                    G[node][successor][
                        "aa_parallel_choice_group"
                    ] = group
                successor_groups[successor] = group
        else:
            parallel_group = f"{node}:parallel_choices"
            for successor in candidates:
                successor_groups[successor] = parallel_group
                G[node][successor][
                    "aa_parallel_choice_group"
                ] = parallel_group

        data["aa_active_replan_allowed"] = True
        data["aa_replan_successors"] = tuple(candidates)
        data["aa_replan_successor_groups"] = successor_groups
        allowed_count += 1

    G.graph["aa_replan_scope_diagnostics"] = {
        "replan_allowed_node_count": allowed_count,
        "gate_approach_replan_node_count": gate_approach_count,
        "l2_upstream_release_replan_node_count": l2_upstream_release_count,
        "missing_gate_switch_connections": missing_gate_switch_connections,
        "replan_blocked_nondecision_node_count": blocked_nondecision_count,
        "replan_blocked_upstream_stage_count": blocked_upstream_stage_count,
        "replan_blocked_single_successor_count": blocked_single_successor_count,
    }


def _aa_active_replan_successors(G, node):
    if node not in G.nodes:
        return ()
    if not G.nodes[node].get("aa_active_replan_allowed", False):
        return ()
    return tuple(G.nodes[node].get("aa_replan_successors", ()))


def _source_group_id(line_id, bucket_key):
    suffix = SOURCE_GROUP_SUFFIXES.get(bucket_key, bucket_key)
    return f"{line_id}_{suffix}"


def _train_zone_source_group_id(line_id, train_idx, zone_key):
    return f"{line_id}_train{int(train_idx)}_{zone_key}"


def _l2_train_zone_key_for_car(car_idx):
    car_idx = int(car_idx)
    if car_idx <= 2:
        return "Z1"
    if car_idx <= 4:
        return "Z2"
    if car_idx <= 6:
        return "Z3"
    return "Z4"


def _platform_waiting_zone_source_group_id(line_id, zone_name):
    return f"{_source_group_id(line_id, 'platform_waiting')}::{zone_name}"


def _transfer_relation_source_group_id(line_id, transfer_node_name):
    normalized = transfer_node_name.replace("-", "_")
    tokens = [token for token in normalized.split("_") if token]
    line_tokens = [token for token in ALL_LINE_IDS if token in tokens]
    counterpart = ""
    for token in line_tokens:
        if token != line_id:
            counterpart = token
            break
    if not counterpart:
        return _source_group_id(line_id, "transfer_people")
    return f"{line_id}_{counterpart}_transfer"


def _transfer_source_line(transfer_node_name):
    prefix = "Transfer_"
    if not transfer_node_name.startswith(prefix):
        return ""
    tail = transfer_node_name[len(prefix):]
    if not tail:
        return ""
    first_chunk = tail.split("_", 1)[0]
    if "-" in first_chunk:
        return first_chunk.split("-", 1)[0]
    return first_chunk


def _transfer_nodes_for_source_line(G, line_id):
    if "TRANSFERS" not in NODES_DATA:
        return []
    nodes = []
    for node_name in NODES_DATA["TRANSFERS"].keys():
        if node_name not in G.nodes:
            continue
        if _transfer_source_line(node_name) == line_id:
            nodes.append(node_name)
    return nodes


def _parse_source_group_id(source_group_id):
    zone_name = ""
    base_group_id = source_group_id
    if "::" in source_group_id:
        base_group_id, zone_name = source_group_id.split("::", 1)
    if "_" not in base_group_id:
        return base_group_id, base_group_id, zone_name
    line_id, suffix = base_group_id.split("_", 1)
    if suffix in SOURCE_GROUP_LABELS:
        return line_id, SOURCE_GROUP_LABELS.get(suffix, suffix), zone_name
    if suffix.endswith("_transfer"):
        relation = suffix[: -len("_transfer")]
        if not zone_name:
            zone_name = relation
        return line_id, "transfer_people", zone_name
    return line_id, suffix, zone_name


def _source_group_line_id(source_group_id):
    line_id, _, _ = _parse_source_group_id(source_group_id)
    return line_id


def _source_group_totals_from_pop_dict(pop_dict):
    totals = {}
    for line_id, line_data in pop_dict.items():
        for bucket_key in SOURCE_GROUP_SUFFIXES:
            amount = int(round(float(line_data.get(bucket_key, 0))))
            if amount > 0:
                totals[_source_group_id(line_id, bucket_key)] = amount
    return totals


def _source_group_totals_from_graph(G):
    totals = {}
    for _, node_data in G.nodes(data=True):
        for source_group_id, amount in node_data.get("source_group_dict", {}).items():
            amount_int = int(round(float(amount)))
            if amount_int <= 0:
                continue
            totals[source_group_id] = totals.get(source_group_id, 0) + amount_int
    return totals
TRAIN_PHYSICS = {
    "L7": {
        "trains": 2,
        "cars": 6,
        "car_people": 270,
        "doors_per_car": 5,
        "door_w": 1.4,
        "area_per_car": 70.62,
        "train_spans": [
            _span_from_train_cfg(PATHFINDER_CONFIG["L7"]["trains"][0]),
            _span_from_train_cfg(PATHFINDER_CONFIG["L7"]["trains"][1]),
        ],
    },
    "L2": {
        "trains": 2,
        "cars": 8,
        "car_people": 300,
        "doors_per_car": 5,
        "door_w": 1.4,
        "area_per_car": 70.62,
        "train_spans": [
            _span_from_train_cfg(PATHFINDER_CONFIG["L2"]["trains"][0]),
            _span_from_train_cfg(PATHFINDER_CONFIG["L2"]["trains"][1]),
        ],
    },
    "L16": {
        "trains": 2,
        "cars": 6,
        "car_people": 205,
        "doors_per_car": 3,
        "door_w": 1.4,
        "area_per_car": 70.62,
        "train_spans": [
            _span_from_train_cfg(PATHFINDER_CONFIG["L16_Island1"]["trains"][0]),
            _span_from_train_cfg(PATHFINDER_CONFIG["L16_Island2"]["trains"][0]),
        ],
    },
    "L18": {
        "trains": 2,
        "cars": 6,
        "car_people": 275,
        "doors_per_car": 5,
        "door_w": 1.4,
        "area_per_car": 66,
        "train_spans": [
            _span_from_train_cfg(PATHFINDER_CONFIG["L18"]["trains"][0]),
            _span_from_train_cfg(PATHFINDER_CONFIG["L18"]["trains"][1]),
        ],
    },
    "Maglev": {
        "trains": 2,
        "cars": 5,
        "train_people": 959,
        "doors_per_car": 4,
        "door_w": 1.4,
        "area_per_car": 89,
        "train_spans": [
            _mid_span(PATHFINDER_CONFIG["Maglev"]["trains"][0], PATHFINDER_CONFIG["Maglev"]["trains"][1]),
            _mid_span(PATHFINDER_CONFIG["Maglev"]["trains"][2], PATHFINDER_CONFIG["Maglev"]["trains"][3]),
        ],
    },
}


def _platform_waiting_zone_config(line_id):
    return PLATFORM_WAITING_ZONE_SPECS.get(line_id, {})


def _platform_waiting_zone_defs(line_id):
    return _platform_waiting_zone_config(line_id).get("zones", [])


def _platform_waiting_zone_spec_complete(zone_def):
    return zone_def.get("area") is not None and zone_def.get("pos") is not None


def _platform_waiting_zone_defs_ready(line_id):
    zone_defs = _platform_waiting_zone_defs(line_id)
    return bool(zone_defs) and all(_platform_waiting_zone_spec_complete(zone_def) for zone_def in zone_defs)


def _platform_waiting_zone_name(line_id, train_idx, car_idx, band=None):
    for zone in _platform_waiting_zone_defs(line_id):
        car_indices = zone.get("car_indices")
        if car_indices is None:
            car_indices = [zone.get("car_index", -1)]
        if int(car_idx) not in {int(idx) for idx in car_indices}:
            continue
        zone_band = zone.get("band")
        if band is not None and zone_band is not None and str(zone_band).lower() != str(band).lower():
            continue
        train_indices = zone.get("train_indices")
        if train_indices is None:
            train_indices = [zone.get("train_index", 1)]
        if int(train_idx) in {int(idx) for idx in train_indices}:
            return zone["name"]
    return f"Platform_{line_id}_T{train_idx}_C{car_idx}_Wait"


def _platform_waiting_zone_area_weights(zone_defs):
    return [max(float(zone.get("area", 1.0)), 0.001) for zone in zone_defs]


def _pathfinder_distance(pos_a, pos_b):
    ax, ay = pos_a
    bx, by = pos_b
    return math.hypot(ax - bx, ay - by)


def _square_zone_average_distance(center_pos, area, target_pos, samples_per_side=5):
    """
    将等待区视为以 center_pos 为中心的正方形，
    用规则采样近似“区内均匀分布乘客”到 target_pos 的平均距离。
    """
    area = max(float(area), 0.001)
    side = math.sqrt(area)
    half = side / 2.0
    sample_n = max(int(samples_per_side), 1)
    step = side / sample_n
    cx, cy = center_pos
    tx, ty = target_pos

    total_dist = 0.0
    sample_count = 0
    for ix in range(sample_n):
        sx = cx - half + (ix + 0.5) * step
        for iy in range(sample_n):
            sy = cy - half + (iy + 0.5) * step
            total_dist += math.hypot(sx - tx, sy - ty)
            sample_count += 1

    if sample_count <= 0:
        return _pathfinder_distance(center_pos, target_pos)
    return total_dist / sample_count


def _platform_waiting_zone_pos(line_id, zone_def, fallback_pos):
    manual_pos = zone_def.get("pos")
    if manual_pos is None:
        raise ValueError(
            f"Platform waiting zone '{zone_def.get('name')}' is missing a Pathfinder midpoint position. "
            f"Please fill {line_id}_PLATFORM_WAITING_ZONE_CONFIG['{zone_def.get('zone_key')}']['pos'] in lines_config.py."
        )
    if manual_pos:
        return tuple(manual_pos)

    car_idx = int(zone_def.get("car_index", 1))
    train_indices = zone_def.get("train_indices")
    if train_indices is None:
        train_indices = [zone_def.get("train_index", 1)]
    physics = TRAIN_PHYSICS.get(line_id, {})
    train_spans = physics.get("train_spans", [])
    door_count = max(int(physics.get("doors_per_car", 1)), 1)
    car_count = max(int(physics.get("cars", 1)), 1)
    zone_positions = []
    for train_idx in train_indices:
        train_idx = int(train_idx)
        if train_idx - 1 >= len(train_spans):
            continue
        zone_positions.append(
            _layout_point_from_span(
                train_spans[train_idx - 1],
                car_idx,
                0,
                car_count,
                door_count,
                fallback_pos,
            )
        )
    if not zone_positions:
        return fallback_pos
    return (
        sum(pos[0] for pos in zone_positions) / len(zone_positions),
        sum(pos[1] for pos in zone_positions) / len(zone_positions),
    )


def _platform_vertical_pf_map(line_id, zone_def=None):
    if line_id == "L16":
        train_indices = zone_def.get("train_indices") if zone_def else None
        if train_indices:
            train_idx = int(train_indices[0])
            if train_idx == 1:
                return PATHFINDER_CONFIG.get("L16_Island1", {}).get("verticals", {})
            if train_idx == 2:
                return PATHFINDER_CONFIG.get("L16_Island2", {}).get("verticals", {})

        merged = {}
        merged.update(PATHFINDER_CONFIG.get("L16_Island1", {}).get("verticals", {}))
        merged.update(PATHFINDER_CONFIG.get("L16_Island2", {}).get("verticals", {}))
        return merged

    return PATHFINDER_CONFIG.get(line_id, {}).get("verticals", {})


def _platform_waiting_zone_nodes(G, line_id):
    return [
        zone["name"]
        for zone in _platform_waiting_zone_defs(line_id)
        if zone.get("name") in G.nodes
    ]


def _line_id_for_platform_parent(platform_node):
    for line_id, cfg in PLATFORM_WAITING_ZONE_SPECS.items():
        if cfg.get("parent_platform") == platform_node:
            return line_id
    return None


def _representative_routing_source(G, current_node):
    line_id = _line_id_for_platform_parent(current_node)
    if not line_id:
        return current_node

    zone_nodes = _platform_waiting_zone_nodes(G, line_id)
    if not zone_nodes:
        return current_node

    active_zone_nodes = [
        n for n in zone_nodes if float(G.nodes[n].get("people", 0.0)) > 0.1
    ]
    if not active_zone_nodes:
        return current_node

    active_zone_nodes.sort(
        key=lambda n: (
            float(G.nodes[n].get("people", 0.0)),
            -int(G.nodes[n].get("car_index", 0)),
        ),
        reverse=True,
    )
    return active_zone_nodes[0]


def _is_hidden_visual_node(data):
    return data.get("type") in {"train", "train_car", "platform_waiting_zone"}


def _visual_people_at_node(G, node, node_people):
    total = max(float(node_people.get(node, 0.0)), 0.0)
    line_id = _line_id_for_platform_parent(node)
    if not line_id:
        return total
    for zone_name in _platform_waiting_zone_nodes(G, line_id):
        total += max(float(node_people.get(zone_name, 0.0)), 0.0)
    return total


def _integer_capped_allocation(total_people, weights, caps=None):
    total_int = max(int(round(float(total_people))), 0)
    if total_int <= 0 or not weights:
        return [0] * len(weights)

    clean_weights = [max(float(w), 0.0) for w in weights]
    weight_sum = sum(clean_weights)
    if weight_sum <= 0:
        clean_weights = [1.0] * len(weights)
        weight_sum = float(len(weights))

    if caps is None:
        caps_int = [total_int] * len(weights)
    else:
        caps_int = []
        for cap in caps:
            if cap is None or math.isinf(float(cap)):
                caps_int.append(total_int)
            else:
                caps_int.append(max(int(math.floor(float(cap) + 1e-9)), 0))

    target_total = min(total_int, sum(caps_int))
    if target_total <= 0:
        return [0] * len(weights)

    raw_alloc = [target_total * (w / weight_sum) for w in clean_weights]
    alloc = [min(cap, int(math.floor(raw + 1e-9))) for raw, cap in zip(raw_alloc, caps_int)]
    remaining = target_total - sum(alloc)

    while remaining > 0:
        candidates = [i for i in range(len(alloc)) if alloc[i] < caps_int[i]]
        if not candidates:
            break
        candidates.sort(
            key=lambda i: (
                raw_alloc[i] - alloc[i],
                clean_weights[i],
                caps_int[i] - alloc[i],
                -i,
            ),
            reverse=True,
        )
        for idx in candidates:
            if remaining <= 0:
                break
            if alloc[idx] >= caps_int[idx]:
                continue
            alloc[idx] += 1
            remaining -= 1

    return alloc


def edge_resource_id(G, u, v):
    """Return the physical bottleneck consumed by movement ``u -> v``.

    All incoming edges of a stair, escalator or gate share the destination
    facility. Ordinary links retain their own independent edge resource.
    """
    data = G[u][v]
    cached = data.get("_resource_id_cache")
    if cached is not None:
        return cached
    if spr.is_capacity_service_node(G, v):
        resource_id = ("facility", v)
    else:
        resource_id = ("edge", u, v)
    data["_resource_id_cache"] = resource_id
    return resource_id


def resource_capacity_per_second(G, resource_id):
    simulation_time = float(G.graph.get("_sim_time", 0.0))
    cache = G.graph.get("_resource_capacity_cache")
    if not cache or cache.get("step") != simulation_time:
        cache = {"step": simulation_time, "values": {}}
        G.graph["_resource_capacity_cache"] = cache
    if resource_id in cache["values"]:
        return cache["values"][resource_id]
    kind = resource_id[0]
    if kind == "facility":
        node = resource_id[1]
        capacity = max(float(G.nodes[node].get("capacity", 0.0)), 0.0)
    else:
        _, u, v = resource_id
        capacity = _edge_effective_flow_capacity(G, u, v)
    cache["values"][resource_id] = capacity
    return capacity


def resource_id_text(resource_id):
    if not resource_id:
        return ""
    if resource_id[0] == "facility":
        return str(resource_id[1])
    return f"{resource_id[1]} -> {resource_id[2]}"


def resource_type(G, resource_id):
    if resource_id[0] == "facility":
        return str(G.nodes[resource_id[1]].get("type", "facility"))
    return str(G[resource_id[1]][resource_id[2]].get("edge_type", "edge") or "edge")


def resource_control_edges(G, resource_id):
    return [
        (u, v)
        for u, v in G.edges()
        if edge_resource_id(G, u, v) == resource_id
    ]


def iter_physical_resources(G):
    resources = {}
    for u, v in G.edges():
        resource_id = edge_resource_id(G, u, v)
        resources.setdefault(resource_id, []).append((u, v))
    return resources


def write_resource_mapping_report(G, output_path):
    """Write the auditable mapping from edges to independently metered resources."""
    lines = ["# Resource mapping report", ""]
    for resource_id, control_edges in sorted(iter_physical_resources(G).items(), key=lambda item: resource_id_text(item[0])):
        if resource_id[0] == "facility":
            node = resource_id[1]
            associated_nodes = [node]
            incoming_edges = list(G.in_edges(node))
            outgoing_edges = list(G.out_edges(node))
            spatial_enabled = uses_spatial_storage(G, node)
            density_exempt = bool(G.nodes[node].get("density_exempt", False))
        else:
            _, u, v = resource_id
            associated_nodes = [u, v]
            incoming_edges = [(u, v)]
            outgoing_edges = []
            spatial_enabled = False
            density_exempt = str(G[u][v].get("edge_type", "")).lower() in EDGE_DENSITY_EXEMPT_TYPES
        lines.extend([
            f"## {resource_id_text(resource_id)}",
            "",
            f"- resource_type: {resource_type(G, resource_id)}",
            f"- capacity_per_second: {resource_capacity_per_second(G, resource_id):.6f}",
            f"- associated_nodes: {', '.join(map(str, associated_nodes))}",
            f"- incoming_edges: {', '.join(f'{u} -> {v}' for u, v in incoming_edges) or 'None'}",
            f"- outgoing_edges: {', '.join(f'{u} -> {v}' for u, v in outgoing_edges) or 'None'}",
            f"- capacity_control_edges: {', '.join(f'{u} -> {v}' for u, v in control_edges)}",
            f"- number_of_capacity_control_edges: {len(control_edges)}",
            f"- spatial_storage_enabled: {str(spatial_enabled).lower()}",
            f"- density_exempt: {str(density_exempt).lower()}",
            "",
        ])
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def resource_integer_capacity_for_step(G, resource_id, demand=None):
    """Consume one shared fractional credit bucket for a physical resource."""
    credit_map = G.graph.setdefault("_resource_flow_credit", {})
    # Keep the old public graph field as an alias for readers outside this file.
    G.graph["_edge_flow_credit"] = credit_map
    capacity = resource_capacity_per_second(G, resource_id)
    if math.isinf(capacity):
        return max(int(demand or 0), 0)
    carry = float(credit_map.get(resource_id, 0.0))
    raw_credit = max(capacity, 0.0) * DELTA_T + carry
    whole_capacity = max(int(math.floor(raw_credit + 1e-9)), 0)
    credit_map[resource_id] = raw_credit - whole_capacity
    return whole_capacity


def _edge_integer_capacity_for_step(G, u, v):
    """Compatibility wrapper; callers should aggregate by resource first."""
    demand = int(math.floor(float(G.nodes[u].get("people", 0.0)) + 1e-9))
    return resource_integer_capacity_for_step(G, edge_resource_id(G, u, v), demand)


def _spillback_enabled(G):
    return bool(
        G.graph.get("density_dependent_flow", False)
        and G.graph.get("spillback_enabled", HIGH_LOAD_SPILLBACK_ENABLED)
    )


def edge_receiving_density_limit(G):
    return float(G.graph.get(
        EDGE_RECEIVING_DENSITY_PARAMETER_NAME,
        EDGE_RECEIVING_DENSITY_LIMIT_P_PER_M2,
    ))


def edge_receiving_hard_limit_enabled(G):
    return bool(
        _spillback_enabled(G)
        and G.graph.get(
            "edge_receiving_hard_limit_enabled",
            EDGE_RECEIVING_HARD_LIMIT_ENABLED_DEFAULT,
        )
    )


def is_point_service_resource(G, node):
    """Whether *node* is a throughput-only service point without storage."""
    if node not in G.nodes:
        return False
    node_type = str(G.nodes[node].get("type", "")).strip().lower()
    return node_type.startswith("gate") or "gate" in node_type


_FINITE_GATE_STORAGE_MODES = frozenset({"queue_area", "finite_gate_buffer"})


def _gate_storage_area_node(G, node):
    """Return the physical area node used for a finite Gate service buffer."""
    if node not in G.nodes or not is_point_service_resource(G, node):
        return node
    mode = str(
        G.graph.get("service_node_spatial_storage_mode", "exempt")
    ).lower()
    queue_node = G.graph.get("gate_queue_area_nodes", {}).get(node)
    if mode in _FINITE_GATE_STORAGE_MODES and queue_node in G.nodes:
        return queue_node
    return node


def uses_spatial_storage(G, node):
    """Whether node area constrains occupancy and contributes to density.

    ``legacy`` exists only to reproduce the pre-exemption diagnostic scenario.
    Formal station runs use ``queue_area``: a Gate has a finite service buffer
    with the corresponding physical queue footprint.  The Queue -> Gate edge
    still consumes the shared facility throughput resource; this flag only
    controls spatial receiving/storage at the destination Gate node.
    """
    if node not in G.nodes:
        return False
    data = G.nodes[node]
    if data.get("type") == "exit":
        return False
    mode = str(G.graph.get("service_node_spatial_storage_mode", "exempt")).lower()
    if mode == "legacy" and spr.is_capacity_service_node(G, node):
        return True
    if is_point_service_resource(G, node):
        return _gate_storage_area_node(G, node) != node
    if data.get("density_exempt", False):
        return False
    if not data.get("spatial_storage_enabled", True):
        return False
    return True


def effective_node_area(G, node):
    area_node = _gate_storage_area_node(G, node)
    data = G.nodes[area_node]
    area = max(float(data.get("area", 1.0)), 0.1)
    obstacle_area = min(
        max(float(data.get("obstacle_area", 0.0)), 0.0),
        max(area - 0.1, 0.0),
    )
    return max(area - obstacle_area, 0.1)


def _node_storage_capacity(G, node):
    """Physical receiving occupancy before upstream spillback starts."""
    if node not in G.nodes:
        return 0.0
    if G.nodes[node].get("type") == "exit":
        return float("inf")
    if not uses_spatial_storage(G, node):
        return float("inf")
    jam_density = min(
        max(float(G.graph.get("receiving_jam_density", HIGH_LOAD_JAM_DENSITY_P_PER_M2)), 0.1),
        spr.PAPER_DENSITY_JAM,
    )
    return max(effective_node_area(G, node) * jam_density, 1.0)


def _reserved_transit_to_node(G, node):
    """People already admitted upstream and therefore owed space at *node*."""
    total = 0.0
    for item in G.graph.get("_transit_queue", []):
        if item.get("dest", item.get("v")) == node:
            total += max(float(item.get("amount", 0.0)), 0.0)
    return total


def _reserved_transit_by_node(G):
    totals = {}
    for item in G.graph.get("_transit_queue", []):
        node = item.get("dest", item.get("v"))
        if node is not None:
            totals[node] = totals.get(node, 0.0) + max(float(item.get("amount", 0.0)), 0.0)
    return totals


def _node_receiving_slots(G, node, reserved=None):
    storage = _node_storage_capacity(G, node)
    if math.isinf(storage):
        return float("inf")
    occupied = max(float(G.nodes[node].get("people", 0.0)), 0.0)
    if reserved is None:
        reserved = _reserved_transit_to_node(G, node)
    return max(int(math.floor(storage - occupied - float(reserved) + 1e-9)), 0)


def _aa_spatial_static_event_index(G):
    """Build the confirmed spatial-arrival index once per simulation step."""
    now = float(G.graph.get("_sim_time", 0.0))
    transit_queue = G.graph.get("_transit_queue", [])
    cache_key = (
        now,
        int(G.graph.get("_transit_queue_version", 0)),
    )

    cache = G.graph.get("_aa_transit_spatial_events_cache")
    if cache is not None and cache.get("key") == cache_key:
        return cache

    events_by_node = {}

    for item in transit_queue:
        destination = item.get("dest", item.get("v"))
        if destination is None:
            continue

        event_time = float(item.get("arrive_time", now))
        event_amount = max(float(item.get("amount", 0.0)), 0.0)

        if event_amount <= 0.0 or event_time <= now:
            continue

        events_by_node.setdefault(destination, []).append(
            (event_time, event_amount)
        )

    times_by_node = {}

    for destination, events in events_by_node.items():
        events.sort(key=lambda item: item[0])
        times_by_node[destination] = [item[0] for item in events]

    cache = {
        "key": cache_key,
        "events_by_node": events_by_node,
        "times_by_node": times_by_node,
    }
    G.graph["_aa_transit_spatial_events_cache"] = cache
    return cache


def _aa_spatial_storage_and_step_out_rate(G, node):
    """Return immutable storage and an out-rate refreshed every sim step."""
    static_node_cache = G.graph.setdefault(
        "_aa_spatial_node_static_cache",
        {},
    )
    node_static = static_node_cache.get(node)
    if node_static is None:
        node_static = {
            "storage": _node_storage_capacity(G, node),
        }
        static_node_cache[node] = node_static

    now = float(G.graph.get("_sim_time", 0.0))
    step_cache = G.graph.get("_aa_spatial_node_out_rate_cache")
    if step_cache is None or step_cache.get("sim_time") != now:
        step_cache = {
            "sim_time": now,
            "rates": {},
        }
        G.graph["_aa_spatial_node_out_rate_cache"] = step_cache

    rates = step_cache["rates"]
    if node not in rates:
        diagnostics = G.graph.setdefault("_aa_diagnostics", {})
        resource_rates = {}
        for successor in G.successors(node):
            resource_id = edge_resource_id(G, node, successor)
            rate = resource_capacity_per_second(G, resource_id)
            if math.isfinite(rate) and rate > 0.0:
                resource_rates[resource_id] = rate
        out_rate = sum(resource_rates.values())
        if out_rate <= 0.0 and spr.is_capacity_service_node(G, node):
            service_rate = resource_capacity_per_second(G, ("facility", node))
            if math.isfinite(service_rate) and service_rate > 0.0:
                out_rate = service_rate
                diagnostics["spatial_out_rate_service_fallback_count"] = (
                    int(
                        diagnostics.get(
                            "spatial_out_rate_service_fallback_count",
                            0,
                        )
                    )
                    + 1
                )
        rates[node] = out_rate
        diagnostics["spatial_out_rate_refresh_count"] = (
            int(diagnostics.get("spatial_out_rate_refresh_count", 0)) + 1
        )
        previous_rates = G.graph.setdefault(
            "_aa_spatial_node_previous_out_rate", {}
        )
        previous = previous_rates.get(node)
        current = float(rates[node])
        if previous is not None and abs(float(previous) - current) > 1e-12:
            diagnostics["spatial_out_rate_change_count"] = (
                int(diagnostics.get("spatial_out_rate_change_count", 0)) + 1
            )
            if float(previous) <= 0.0 < current:
                diagnostics["spatial_out_rate_recovery_count"] = (
                    int(
                        diagnostics.get(
                            "spatial_out_rate_recovery_count", 0
                        )
                    )
                    + 1
                )
        previous_rates[node] = current

    return float(node_static["storage"]), float(rates[node])


def _predict_spatial_occupancy_linear(G, node, target_time):
    """
    Predict physical node occupancy at target_time.

    Only two kinds of physical state may be used:
    1. people currently located at the node;
    2. movements already accepted by the common allocator and stored in
       _transit_queue.

    Unaccepted AA planning intentions must never enter this calculation.
    """
    if node not in G.nodes or not uses_spatial_storage(G, node):
        return 0.0, float("inf"), 0.0

    storage, out_rate = _aa_spatial_storage_and_step_out_rate(G, node)

    now = float(G.graph.get("_sim_time", 0.0))
    target_time = max(float(target_time), now)

    if math.isinf(storage):
        return 0.0, storage, out_rate

    # Actual people physically located at this node now.
    occupancy = max(
        float(G.nodes[node].get("people", 0.0)),
        0.0,
    )

    # Only movements already accepted by the common physical allocator are
    # stored in _transit_queue and may become hard future spatial arrivals.
    static_index = _aa_spatial_static_event_index(G)
    confirmed_events = static_index["events_by_node"].get(node, ())
    confirmed_times = static_index["times_by_node"].get(node, ())

    confirmed_end = bisect_right(
        confirmed_times,
        target_time,
    )
    confirmed_events = confirmed_events[:confirmed_end]

    last_time = now

    for event_time, event_amount in confirmed_events:
        event_time = max(float(event_time), last_time)
        elapsed = event_time - last_time

        if out_rate > 0.0 and elapsed > 0.0:
            occupancy = max(
                occupancy - out_rate * elapsed,
                0.0,
            )

        occupancy += max(float(event_amount), 0.0)
        last_time = event_time

    remaining_time = max(target_time - last_time, 0.0)

    if out_rate > 0.0 and remaining_time > 0.0:
        occupancy = max(
            occupancy - out_rate * remaining_time,
            0.0,
        )

    return occupancy, storage, out_rate


def _predict_spatial_occupancy_indexed(G, node, target_time):
    if node not in G.nodes or not uses_spatial_storage(G, node):
        return 0.0, float("inf"), 0.0

    storage, out_rate = _aa_spatial_storage_and_step_out_rate(G, node)
    now = float(G.graph.get("_sim_time", 0.0))
    target_time = max(float(target_time), now)
    if math.isinf(storage):
        return 0.0, storage, out_rate

    people = max(float(G.nodes[node].get("people", 0.0)), 0.0)
    transit_version = int(G.graph.get("_transit_queue_version", 0))
    cache_key = (
        now,
        transit_version,
        node,
        people,
        out_rate,
    )
    prefix_cache = G.graph.setdefault(
        "_aa_spatial_occupancy_prefix_cache",
        {},
    )
    prefix = prefix_cache.get(node)
    if prefix is None or prefix.get("key") != cache_key:
        static_index = _aa_spatial_static_event_index(G)
        confirmed_events = static_index["events_by_node"].get(node, ())

        times = []
        occupancies_after_event = []
        occupancy = people
        last_time = now
        for event_time, event_amount in confirmed_events:
            event_time = max(float(event_time), now)
            event_amount = max(float(event_amount), 0.0)
            if event_amount <= 0.0:
                continue
            occupancy = max(
                occupancy - out_rate * max(event_time - last_time, 0.0),
                0.0,
            )
            occupancy += event_amount
            times.append(event_time)
            occupancies_after_event.append(occupancy)
            last_time = event_time

        prefix = {
            "key": cache_key,
            "times": times,
            "occupancies_after_event": occupancies_after_event,
        }
        prefix_cache[node] = prefix

    times = prefix["times"]
    end = bisect_right(times, target_time)
    if end <= 0:
        occupancy = max(
            people - out_rate * (target_time - now),
            0.0,
        )
    else:
        event_time = times[end - 1]
        occupancy = max(
            prefix["occupancies_after_event"][end - 1]
            - out_rate * max(target_time - event_time, 0.0),
            0.0,
        )
    return occupancy, storage, out_rate


def _predict_spatial_occupancy(G, node, target_time):
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    if bool(G.graph.get("_fast_exact_aa", True)):
        diagnostics["spatial_index_query_count"] = (
            int(diagnostics.get("spatial_index_query_count", 0)) + 1
        )
        return _predict_spatial_occupancy_indexed(
            G,
            node,
            target_time,
        )

    diagnostics["spatial_fallback_linear_scan_count"] = (
        int(
            diagnostics.get(
                "spatial_fallback_linear_scan_count",
                0,
            )
        )
        + 1
    )
    return _predict_spatial_occupancy_linear(
        G,
        node,
        target_time,
    )


def predicted_spatial_receiving_wait(G, node, target_time, amount=1):
    occupancy, storage, out_rate = _predict_spatial_occupancy(
        G,
        node,
        target_time,
    )

    if math.isinf(storage):
        return 0.0

    deficit = occupancy + max(int(amount), 1) - storage

    if deficit <= 0.0:
        return 0.0

    if out_rate <= 0:
        return float("inf")

    return deficit / out_rate


def predicted_spatial_density(G, node, target_time, amount=0):
    if (
        node not in G.nodes
        or G.nodes[node].get("type") == "exit"
        or not uses_spatial_storage(G, node)
    ):
        return 0.0

    occupancy, _, _ = _predict_spatial_occupancy(
        G,
        node,
        target_time,
    )

    area = max(float(effective_node_area(G, node)), 0.1)

    return (
        max(float(occupancy), 0.0)
        + max(float(amount), 0.0)
    ) / area


def _apply_destination_receiving_limits(G, moves):
    """Cap simultaneous merge inflow by shared downstream storage.

    Admission reserves downstream space at departure, so later inflows observe
    people already in transit and queues spill upstream instead of overfilling
    a merge node through independently constrained incoming edges.
    """
    G.graph.setdefault("_current_spatial_blocked_sources", {})
    if not moves or not _spillback_enabled(G):
        return moves

    by_destination = {}
    for idx, (u, v, amount) in enumerate(moves):
        if amount > 0:
            by_destination.setdefault(v, []).append((idx, u, int(amount)))

    accepted = [0] * len(moves)
    reserved_by_node = _reserved_transit_by_node(G)
    for v, incoming in by_destination.items():
        slots = _node_receiving_slots(G, v, reserved_by_node.get(v, 0.0))
        amounts = [amount for _, _, amount in incoming]
        if math.isinf(slots):
            allocation = amounts
        else:
            allocation = _integer_capped_allocation(
                min(int(slots), sum(amounts)),
                amounts,
                amounts,
            )
        for (idx, _, _), amount in zip(incoming, allocation):
            accepted[idx] = amount
        blocked_sources = G.graph["_current_spatial_blocked_sources"]
        rejected_by_edge = {}
        for (_, source, requested), amount in zip(incoming, allocation):
            source_rejected = requested - amount
            if source_rejected > 0:
                blocked_sources[source] = blocked_sources.get(source, 0) + source_rejected
                edge = (source, v)
                rejected_by_edge[edge] = (
                    rejected_by_edge.get(edge, 0.0)
                    + source_rejected
                )
        for (source, destination), edge_rejected in rejected_by_edge.items():
            _record_receiving_block_rejection(
                G,
                "destination_capacity_or_spillback",
                source,
                destination,
                edge_rejected,
            )
        rejected = sum(amounts) - sum(allocation)
        if rejected > 0 and uses_spatial_storage(G, v):
            rejected_map = G.graph.setdefault("_spatial_rejected_inflow", {})
            rejected_map[v] = rejected_map.get(v, 0.0) + float(rejected)
            if is_point_service_resource(G, v):
                current_gate_spillback = G.graph.setdefault(
                    "_current_gate_upstream_spillback", {}
                )
                current_gate_spillback[v] = (
                    float(current_gate_spillback.get(v, 0.0))
                    + float(rejected)
                )
                source_details = G.graph.setdefault(
                    "_current_gate_upstream_spillback_sources", {}
                ).setdefault(v, {})
                for (source, destination), edge_rejected in rejected_by_edge.items():
                    if destination == v:
                        source_details[source] = (
                            float(source_details.get(source, 0.0))
                            + float(edge_rejected)
                        )
                gate_diag = G.graph.setdefault("_gate_service_diagnostics", {})
                gate_stat = gate_diag.setdefault(v, {})
                gate_stat["gate_upstream_spillback_person_seconds"] = (
                    float(
                        gate_stat.get(
                            "gate_upstream_spillback_person_seconds", 0.0
                        )
                    )
                    + float(rejected) * DELTA_T
                )

    return [
        (u, v, accepted[idx])
        for idx, (u, v, _) in enumerate(moves)
        if accepted[idx] > 0
    ]


def _edge_critical_density(G):
    """Configured common edge-receiving density limit."""
    return edge_receiving_density_limit(G)


def _record_receiving_block_rejection(G, block_type, u, v, rejected_people):
    """Record one positive rejection event without affecting allocation."""
    rejected_people = max(float(rejected_people), 0.0)
    if rejected_people <= 0.0:
        return
    diagnostics = G.graph.setdefault("_receiving_block_diagnostics", {})
    per_type = diagnostics.setdefault(block_type, {})
    stat = per_type.setdefault(
        (u, v),
        {
            "rejection_event_count": 0,
            "rejected_people": 0.0,
            "blocked_person_seconds": 0.0,
        },
    )
    stat["rejection_event_count"] += 1
    stat["rejected_people"] += rejected_people
    stat["blocked_person_seconds"] += rejected_people * DELTA_T


def _apply_edge_receiving_limits(G, moves):
    """Keep link occupancy on the stable branch of the fundamental diagram.

    Congested excess demand remains upstream. Without this link-storage
    admission rule, a one-second batch can fill an edge to jam density and its
    entry-time speed is then frozen near zero for the whole traversal.
    """
    G.graph["_current_spatial_blocked_sources"] = {}
    G.graph["_current_gate_upstream_spillback"] = {}
    G.graph["_current_gate_upstream_spillback_sources"] = {}
    if not moves or not edge_receiving_hard_limit_enabled(G):
        return moves

    by_edge = {}
    for idx, (u, v, amount) in enumerate(moves):
        if amount > 0:
            by_edge.setdefault((u, v), []).append((idx, int(amount)))

    accepted = [0] * len(moves)
    critical_density = _edge_critical_density(G)
    blocked_sources = G.graph["_current_spatial_blocked_sources"]
    for (u, v), requests in by_edge.items():
        edge_type = str(G[u][v].get("edge_type", "")).lower()
        amounts = [amount for _, amount in requests]
        if edge_type in EDGE_DENSITY_EXEMPT_TYPES:
            allocation = amounts
        else:
            edge_area = float(_edge_effective_area(G, u, v))
            if not math.isfinite(edge_area):
                # Infinite-area/capacity links are topological connectors, not
                # finite pedestrian reservoirs.
                allocation = amounts
            else:
                storage = max(
                    int(
                        math.floor(
                            edge_area * critical_density
                            + 1e-9
                        )
                    ),
                    1,
                )
                occupied = int(
                    math.ceil(
                        _edge_active_passengers(
                            G,
                            u,
                            v,
                            float(G.graph.get("_sim_time", 0.0)),
                        )
                        - 1e-9
                    )
                )
                slots = max(storage - occupied, 0)
                allocation = _integer_capped_allocation(
                    min(slots, sum(amounts)),
                    amounts,
                    amounts,
                )
        for (idx, requested), amount in zip(requests, allocation):
            accepted[idx] = amount
            rejected = requested - amount
            if rejected > 0:
                blocked_sources[u] = blocked_sources.get(u, 0) + rejected
        edge_rejected = sum(
            requested - amount
            for (_, requested), amount in zip(requests, allocation)
        )
        if edge_rejected > 0:
            _record_receiving_block_rejection(
                G,
                "edge_receiving_hard_limit",
                u,
                v,
                edge_rejected,
            )

    return [
        (u, v, accepted[idx])
        for idx, (u, v, _) in enumerate(moves)
        if accepted[idx] > 0
    ]


def _integerize_moves(G, moves):
    """Integerise proposals and enforce each physical capacity exactly once.

    ``_resource_queues`` is the current step's waiting intent by resource; it
    is not a persistent FIFO population. People remain at their source node
    and may choose a different resource next step. No overflow is sent to an
    unselected edge. Requests are first bounded by
    source occupancy, then allocated proportionally within each shared
    facility/edge resource, and finally constrained by destination storage.
    """
    if not moves:
        G.graph["_resource_queues"] = {}
        return []

    grouped = {}
    for u, v, amount in moves:
        if amount <= 0 or u not in G.nodes or v not in G.nodes:
            continue
        grouped.setdefault(u, []).append((v, float(amount)))

    requests = []
    for u, proposals in grouped.items():
        available = max(int(math.floor(float(G.nodes[u].get("people", 0.0)) + 1e-9)), 0)
        if available <= 0:
            continue
        proposal_caps = [max(int(math.floor(amount + 1e-9)), 0) for _, amount in proposals]
        weights = [max(amount, 0.0) for _, amount in proposals]
        source_alloc = _integer_capped_allocation(
            min(available, sum(proposal_caps)),
            weights,
            proposal_caps,
        )
        for (v, _), requested in zip(proposals, source_alloc):
            if requested > 0:
                requests.append({
                    "u": u,
                    "v": v,
                    "requested": int(requested),
                    "resource_id": edge_resource_id(G, u, v),
                })

    by_resource = {}
    for request in requests:
        by_resource.setdefault(request["resource_id"], []).append(request)

    integer_moves = []
    waiting_by_resource = {}
    waiting_sources = {}
    step_capacity_by_resource = {}
    round_robin = G.graph.setdefault("_resource_round_robin_cursor", {})
    for resource_id in sorted(by_resource, key=str):
        resource_requests = by_resource[resource_id]
        total_demand = sum(item["requested"] for item in resource_requests)
        shared_step_capacity = G.graph.get("_aa_step_resource_capacity")
        if (
            isinstance(shared_step_capacity, dict)
            and resource_id in shared_step_capacity
        ):
            step_capacity = int(shared_step_capacity[resource_id])
        else:
            step_capacity = resource_integer_capacity_for_step(
                G, resource_id, total_demand
            )
            if isinstance(shared_step_capacity, dict):
                shared_step_capacity[resource_id] = int(step_capacity)
        step_capacity_by_resource[resource_id] = step_capacity
        cursor = int(round_robin.get(resource_id, 0)) % len(resource_requests)
        rotated = resource_requests[cursor:] + resource_requests[:cursor]
        # A shared facility may still have service capacity while one of its
        # incoming physical edges is jammed. Never admit passengers onto an
        # edge whose realized traversal time is non-finite: doing so removes
        # them from the source and creates an arrive_time=inf transit record.
        rotated_caps = [
            item["requested"]
            if math.isfinite(_edge_travel_time(G, item["u"], item["v"]))
            else 0
            for item in rotated
        ]
        rotated_accepted = _integer_capped_allocation(
            min(total_demand, step_capacity, sum(rotated_caps)),
            [item["requested"] for item in rotated],
            rotated_caps,
        )
        accepted = rotated_accepted[-cursor:] + rotated_accepted[:-cursor] if cursor else rotated_accepted
        round_robin[resource_id] = (cursor + max(step_capacity, 1)) % len(resource_requests)
        waiting = 0
        for item, amount in zip(resource_requests, accepted):
            rejected = item["requested"] - amount
            waiting += rejected
            if rejected > 0:
                source_map = waiting_sources.setdefault(resource_id, {})
                source_map[item["u"]] = source_map.get(item["u"], 0) + rejected
            if amount > 0:
                integer_moves.append((item["u"], item["v"], int(amount)))
        waiting_by_resource[resource_id] = waiting

    edge_limited_moves = _apply_edge_receiving_limits(G, integer_moves)
    limited_moves = _apply_destination_receiving_limits(G, edge_limited_moves)
    accepted_lookup = {(u, v): amount for u, v, amount in limited_moves}
    for u, v, amount in integer_moves:
        rejected = amount - accepted_lookup.get((u, v), 0)
        if rejected > 0:
            resource_id = edge_resource_id(G, u, v)
            waiting_by_resource[resource_id] = waiting_by_resource.get(resource_id, 0) + rejected
            source_map = waiting_sources.setdefault(resource_id, {})
            source_map[u] = source_map.get(u, 0) + rejected

    G.graph["_resource_queues"] = waiting_by_resource
    G.graph["_resource_queue_sources"] = waiting_sources
    G.graph["_last_resource_step_capacity"] = step_capacity_by_resource
    return limited_moves


def _update_gate_service_diagnostics(G, current_time, scheduled_moves):
    """Observe the Step 6 gate queue/service sequence without changing it."""
    diagnostics = G.graph.setdefault("_gate_service_diagnostics", {})
    entered_by_gate = {}
    for item in scheduled_moves:
        u = item.get("u")
        v = item.get("v")
        amount = max(float(item.get("amount", 0.0)), 0.0)
        if amount <= 0.0:
            continue
        if is_point_service_resource(G, v):
            entered_by_gate[v] = entered_by_gate.get(v, 0.0) + amount

    for gate, data in G.nodes(data=True):
        if not is_point_service_resource(G, gate):
            continue
        stat = diagnostics.setdefault(gate, {})
        # Gate service is metered on the incoming edge into the gate. An
        # outgoing corridor move means that service has already happened and
        # must not be compared with the gate's incoming capacity again.
        served = entered_by_gate.get(gate, 0.0)
        entered = entered_by_gate.get(gate, 0.0)
        stat["gate_service_people"] = (
            float(stat.get("gate_service_people", 0.0)) + served
        )
        queue_people = max(float(data.get("people", 0.0)), 0.0)
        stat["gate_queue_person_seconds"] = (
            float(stat.get("gate_queue_person_seconds", 0.0))
            + queue_people * DELTA_T
        )
        stat["gate_max_queue_people"] = max(
            float(stat.get("gate_max_queue_people", 0.0)),
            queue_people,
        )
        stat["last_observed_queue_people"] = queue_people
        stat["last_observed_time_seconds"] = float(current_time)

        available = float(
            G.graph.get("_last_resource_step_capacity", {}).get(
                ("facility", gate), 0.0
            )
        )
        if served > available + 1e-9:
            stat["gate_capacity_violation_count"] = int(
                stat.get("gate_capacity_violation_count", 0)
            ) + 1
        else:
            stat.setdefault("gate_capacity_violation_count", 0)

        # Gate service is intentionally metered on the entry edge into the
        # point-service gate. Outgoing gate edges are ordinary corridor links,
        # so this legacy diagnostic is kept as a zero-valued compatibility
        # field rather than flagging every valid gate entry as a violation.
        stat.setdefault("gate_double_service_violation_count", 0)

        storage = _node_storage_capacity(G, gate)
        reserved = _reserved_transit_to_node(G, gate)
        if math.isfinite(storage):
            storage_utilization = queue_people / max(storage, 1.0)
            stat["gate_storage_capacity_people"] = float(storage)
            stat["gate_peak_storage_utilization"] = max(
                float(stat.get("gate_peak_storage_utilization", 0.0)),
                storage_utilization,
            )
            stat["gate_storage_overflow_people"] = max(
                float(stat.get("gate_storage_overflow_people", 0.0)),
                max(queue_people + reserved - storage, 0.0),
            )
        else:
            # Keep the exported diagnostics numeric for legacy/custom graphs
            # that intentionally model a point Gate as storage-exempt.
            stat.setdefault("gate_storage_capacity_people", 0.0)
            stat.setdefault("gate_peak_storage_utilization", 0.0)
            stat.setdefault("gate_storage_overflow_people", 0.0)
        if (
            math.isfinite(storage)
            and queue_people + reserved > storage + 1e-9
        ):
            stat["gate_capacity_violation_count"] = int(
                stat.get("gate_capacity_violation_count", 0)
            ) + 1

        stat["scheduled_gate_entry_people"] = (
            float(stat.get("scheduled_gate_entry_people", 0.0)) + entered
        )
        backlog = gate_service_backlog_state(G, gate)
        backlog_stat = G.graph.setdefault(
            "_gate_backlog_diagnostics", {}
        ).setdefault(gate, {})
        service_rate = resource_capacity_per_second(G, ("facility", gate))
        if gate in {
            "Gate_L18_E1", "Gate_L18_E2", "Gate_L18_S1", "Gate_L18_S2",
            "Gate_L2_N_West", "Gate_L2_N_East",
            "Gate_L2_S_West", "Gate_L2_S_East",
        }:
            G.graph.setdefault("_gate_backlog_step_trace", []).append({
                "sim_time_seconds": float(current_time),
                "gate": gate,
                "gate_node_waiting_people": backlog[
                    "gate_node_waiting_people"
                ],
                "gate_node_occupancy_people": backlog[
                    "gate_node_waiting_people"
                ],
                "gate_upstream_blocked_people": backlog[
                    "upstream_blocked_people"
                ],
                "gate_spillback_queue_people": backlog[
                    "upstream_blocked_people"
                ],
                "gate_service_backlog_people": backlog["backlog_people"],
                "gate_routing_queue_people": backlog_stat.get(
                    "gate_routing_queue_people", 0.0
                ),
                "improved_queue_q_used": backlog_stat.get(
                    "improved_queue_q_used", 0.0
                ),
                "service_rate_people_per_second": service_rate,
                "queue_wait_cost_seconds": (
                    float(
                        backlog_stat.get("gate_routing_queue_people", 0.0)
                    ) / service_rate
                    if service_rate > 0.0 else float("inf")
                ),
                "selected_people_this_step": float(
                    G.graph.get(
                        "_gate_selected_people_this_step", {}
                    ).get(gate, 0.0)
                ),
                "served_people_this_step": served,
            })


def _add_people_to_nodes_by_weights(
    G,
    node_names,
    line_id,
    total_people,
    weights,
    source_group_id=None,
    source_group_ids=None,
):
    if total_people <= 0 or not node_names:
        return

    allocations = _integer_capped_allocation(total_people, weights)
    for idx, (node_name, amount) in enumerate(zip(node_names, allocations)):
        if amount <= 0:
            continue
        G.nodes[node_name]["people"] += amount
        G.nodes[node_name]["people_dict"][line_id] += amount
        active_source_group_id = source_group_id
        if source_group_ids is not None and idx < len(source_group_ids):
            active_source_group_id = source_group_ids[idx]
        if active_source_group_id is not None:
            G.nodes[node_name].setdefault("source_group_dict", {})
            G.nodes[node_name]["source_group_dict"][active_source_group_id] = (
                G.nodes[node_name]["source_group_dict"].get(active_source_group_id, 0) + amount
            )


def _add_platform_waiting_zone_nodes_and_edges(G):
    for line_id, cfg in PLATFORM_WAITING_ZONE_SPECS.items():
        if not _platform_waiting_zone_defs_ready(line_id):
            continue
        parent_platform = cfg.get("parent_platform", f"Platform_{line_id}")
        if parent_platform not in G.nodes:
            continue

        vertical_group = PLATFORM_VERTICAL_SPECS.get(line_id, {}).get("vertical_group")
        if not vertical_group or vertical_group not in NODES_DATA:
            continue

        fallback_pos = G.nodes[parent_platform].get("pos", (0.0, 0.0))
        delta_h = get_delta_h(line_id)

        for zone_def in cfg.get("zones", []):
            zone_name = zone_def["name"]
            zone_pos = _platform_waiting_zone_pos(line_id, zone_def, fallback_pos)
            vertical_pf_map = _platform_vertical_pf_map(line_id, zone_def)
            raw_area = zone_def.get("area")
            if raw_area is None:
                raise ValueError(
                    f"Platform waiting zone '{zone_name}' is missing an area value. "
                    f"Please fill {line_id}_PLATFORM_WAITING_ZONE_CONFIG['{zone_def.get('zone_key')}']['area'] in lines_config.py."
                )
            zone_area = max(float(raw_area), 1.0)
            G.add_node(
                zone_name,
                type="platform_waiting_zone",
                capacity=999999,
                area=zone_area,
                people=0.0,
                pos=zone_pos,
                pathfinder_pos=zone_pos,
                line_id=line_id,
                parent_platform=parent_platform,
                car_index=int(zone_def.get("car_index", 1)),
                car_indices=zone_def.get("car_indices"),
                band=zone_def.get("band"),
                train_indices=zone_def.get("train_indices"),
            )

            candidate_verticals = vertical_pf_map.keys() if vertical_pf_map else NODES_DATA[vertical_group].keys()
            for vertical_name in candidate_verticals:
                if vertical_name not in G.nodes:
                    continue
                vertical_pf_pos = vertical_pf_map.get(vertical_name)
                if not vertical_pf_pos:
                    continue
                horizontal_dist = _square_zone_average_distance(zone_pos, zone_area, vertical_pf_pos)
                total_edge_length = horizontal_dist + 2.0 * delta_h
                G.add_edge(
                    zone_name,
                    vertical_name,
                    length=total_edge_length,
                    capacity=G.nodes[vertical_name]["capacity"],
                    edge_type="platform_zone_to_vertical",
                )


def _hall_staging_nodes_for_line(G, line_id):
    specs = HALL_STAGING_SPECS.get(line_id, [])
    return [cfg["name"] for cfg in specs if cfg["name"] in G.nodes]


def _ensure_hall_staging_nodes(G):
    for line_id, staging_specs in HALL_STAGING_SPECS.items():
        for cfg in staging_specs:
            node_name = cfg["name"]
            target_nodes = [n for n in cfg.get("targets", []) if n in G.nodes]
            if not target_nodes:
                continue

            if node_name not in G.nodes:
                xs, ys = [], []
                cap_sum = 0.0
                for target in target_nodes:
                    pos = G.nodes[target].get("pos", (0.0, 0.0))
                    xs.append(float(pos[0]))
                    ys.append(float(pos[1]))
                    cap_sum += float(G.nodes[target].get("capacity", 1.0))

                center_x = float(sum(xs) / max(len(xs), 1))
                center_y = float(sum(ys) / max(len(ys), 1)) + 6.0
                staging_area = float(cfg.get("manual_area", 80.0))
                G.add_node(
                    node_name,
                    type="virtual",
                    people=0,
                    capacity=max(cap_sum, 1.0),
                    area=staging_area,
                    manual_area=staging_area,
                    pos=(center_x, center_y),
                    line_id=line_id,
                )

            source_pos = G.nodes[node_name].get("pos", (0.0, 0.0))
            for target in target_nodes:
                edge_target = G.graph.get("gate_queue_area_nodes", {}).get(
                    target,
                    target,
                )
                if edge_target not in G.nodes:
                    edge_target = target
                if G.has_edge(node_name, edge_target):
                    continue
                target_pos = G.nodes[edge_target].get(
                    "pos",
                    G.nodes[target].get("pos", source_pos),
                )
                raw_dist = float(np.linalg.norm(np.array(target_pos) - np.array(source_pos)))
                scale = HALL_STAGING_LENGTH_SCALE_BY_LINE.get(line_id, 1.0)
                length = max(raw_dist * scale, 4.0)
                capacity = _edge_capacity_for_new_link(G, node_name, edge_target)
                G.add_edge(
                    node_name,
                    edge_target,
                    length=length,
                    capacity=capacity,
                    edge_type="hall_to_gate",
                    gate_queue_target=target if edge_target != target else None,
                )


def _connect_l7_gate_queues_for_lateral_switching(G):
    """Add positive CAD-derived lateral walks between the four L7 queues."""
    queue_by_gate = dict(G.graph.get("gate_queue_area_nodes", {}))
    l7_gates = tuple(HALL_STAGING_SPECS["L7"][0]["targets"])
    queues = [
        queue_by_gate[gate]
        for gate in l7_gates
        if queue_by_gate.get(gate) in G.nodes
    ]
    scale = HALL_STAGING_LENGTH_SCALE_BY_LINE["L7"]
    connected_pairs = []
    for source in queues:
        source_pos = G.nodes[source].get("pos")
        if source_pos is None:
            raise ValueError(f"{source} is missing its CAD-derived position")
        for target in queues:
            if source == target:
                continue
            target_pos = G.nodes[target].get("pos")
            if target_pos is None:
                raise ValueError(
                    f"{target} is missing its CAD-derived position"
                )
            raw_distance = float(np.linalg.norm(
                np.array(source_pos, dtype=float)
                - np.array(target_pos, dtype=float)
            ))
            length = raw_distance * scale
            if length <= 0.0:
                raise ValueError(
                    f"Non-positive L7 gate-switch distance: "
                    f"{source}->{target}"
                )
            if not G.has_edge(source, target):
                G.add_edge(
                    source,
                    target,
                    length=length,
                    capacity=_edge_capacity_for_new_link(
                        G, source, target
                    ),
                    edge_type="gate_approach_lateral",
                    distance_source="cad_euclidean",
                    gate_switch_only=True,
                )
            connected_pairs.append((source, target))
    G.graph["l7_gate_switch_queue_nodes"] = tuple(queues)
    G.graph["l7_gate_switch_lateral_pairs"] = tuple(connected_pairs)


def _rewire_l7_verticals_to_common_hall(G):
    """Route L7 vertical-facility outflow through the common hall decision.

    The link length is derived from the existing CAD coordinates with the same
    L7 scale used by the hall-to-queue links. No new area or surveyed geometry
    is introduced.
    """
    hall = "VN_L7_Hall_Arrival"
    if hall not in G.nodes:
        raise ValueError(f"Missing required L7 common decision node: {hall}")

    queue_by_gate = dict(G.graph.get("gate_queue_area_nodes", {}))
    l7_gates = set(HALL_STAGING_SPECS["L7"][0]["targets"])
    l7_queues = {
        queue_by_gate.get(gate, gate)
        for gate in l7_gates
        if queue_by_gate.get(gate, gate) in G.nodes
    }
    hall_pos = G.nodes[hall].get("pos")
    if hall_pos is None:
        raise ValueError(f"{hall} is missing its CAD-derived position")

    audit_rows = []
    scale = HALL_STAGING_LENGTH_SCALE_BY_LINE["L7"]
    for upstream in L7_HALL_COMMON_DECISION_UPSTREAMS:
        if upstream not in G.nodes:
            raise ValueError(f"Missing configured L7 vertical node: {upstream}")
        removed = []
        for target in tuple(G.successors(upstream)):
            if target not in l7_queues and target not in l7_gates:
                continue
            removed.append({
                "target": target,
                "length": float(G[upstream][target].get("length", 0.0)),
                "capacity": float(
                    G[upstream][target].get("capacity", float("inf"))
                ),
            })
            G.remove_edge(upstream, target)

        upstream_pos = G.nodes[upstream].get("pos")
        if upstream_pos is None:
            raise ValueError(f"{upstream} is missing its configured CAD position")
        raw_distance = float(np.linalg.norm(
            np.array(upstream_pos, dtype=float)
            - np.array(hall_pos, dtype=float)
        ))
        length = raw_distance * scale
        if length <= 0.0:
            raise ValueError(
                f"Non-positive CAD-derived length for {upstream} -> {hall}"
            )
        capacity = _edge_capacity_for_new_link(G, upstream, hall)
        G.add_edge(
            upstream,
            hall,
            length=length,
            capacity=capacity,
            edge_type="vertical_to_common_hall",
            distance_source="cad_euclidean",
            common_decision_node=hall,
        )
        audit_rows.append({
            "upstream_node": upstream,
            "decision_node": hall,
            "length_m": length,
            "capacity_per_second": capacity,
            "removed_direct_targets": "; ".join(
                row["target"] for row in removed
            ),
            "removed_direct_target_count": len(removed),
        })

    G.graph["l7_common_hall_topology_audit"] = audit_rows

# ==============================================================================
# 1. 严格的线路检测器 (已恢复：nx.has_path 终极物理连通性检验)
# ==============================================================================
def get_real_active_lines(G):
    """极其严格的线路存活判定：节点必须存在，且拓扑必须物理连通至出口"""
    active_count = 0
    exits = [n for n, d in G.nodes(data=True) if d.get('type') == 'exit']

    if not exits:
        raise ValueError("\n[拓扑致命错误] 整个图中没有任何出口 (exit) 节点！")

    for line_id, spec in PLATFORM_VERTICAL_SPECS.items():
        p_node = spec["platform_node"]

        # 1. 如果连站台节点都没有，说明这条线完全没配，正常忽略
        if p_node not in G.nodes:
            print(f"⚠️ 忽略: 线路 {line_id} 未接入 (无站台节点)。")
            continue

        # 2. 终极连通性检验：站台是否能通达至少一个出口？
        is_connected = False
        for ext in exits:
            if nx.has_path(G, p_node, ext):
                is_connected = True
                break

        if is_connected:
            active_count += 1
            print(f"✔️ 检测到拓扑连通的有效线路: {line_id}")
        else:
            # 阻断式报错：有站台却没有连通出路，拓扑断裂！
            raise ValueError(
                f"\n[拓扑断裂致命错误] 线路 {line_id} 的站台已创建，但无法通达任何出口！请检查 EDGES_DATA 是否漏连了边！")

    return active_count


# ==============================================================================
# 2. 核心计算
# ==============================================================================
def get_delta_h(line_id):
    if line_id in STATION_LEVELS:
        return abs(STATION_LEVELS[line_id]["hall"] - STATION_LEVELS[line_id]["platform"])
    else:
        raise ValueError(f"\n[致命错误]：未找到线路 '{line_id}' 的标高配置！")



def calculate_gb_capacity_per_second(facility_type, width_or_count, direction="one_way"):
    direction = str(direction).strip().lower()
    if direction not in VALID_DIRECTIONS:
        raise ValueError(
            f"Invalid facility direction {direction!r}; expected one of "
            f"{sorted(VALID_DIRECTIONS)}"
        )
    facility_type = str(facility_type).strip().lower()
    cap_h = 0
    if facility_type == "stair":
        if direction in ["down", "stop down"]:
            cap_h = 4200 * width_or_count
        elif direction in ["up", "stop up"]:
            cap_h = 3700 * width_or_count
        else:
            cap_h = 3200 * width_or_count
    elif facility_type == "passageway":
        if direction in ["one_way", "up", "down", "out"]:
            cap_h = 5000 * width_or_count
        else:
            cap_h = 4000 * width_or_count
    elif facility_type == "escalator":
        if direction == "stop up":
            cap_h = 3900 * width_or_count
        elif direction == "stop down":
            cap_h = 4400 * width_or_count
        else:
            cap_h = 6720 * width_or_count
    elif "gate" in facility_type:
        count = width_or_count
        cap_h = 1200 * count if "tripod" in facility_type else 2500 * count
    else:
        cap_h = 5000 * width_or_count
    return cap_h / 3600.0


def _apply_pathfinder_capacity_calibration(G, factor=PATHFINDER_CAPACITY_CALIBRATION_FACTOR):
    factor = float(factor)
    if factor <= 0:
        return

    for _, data in G.nodes(data=True):
        capacity = float(data.get("capacity", 0.0) or 0.0)
        if capacity > 0 and math.isfinite(capacity) and capacity < 999999:
            data["raw_capacity"] = capacity
            data["capacity"] = capacity * factor

    for _, _, data in G.edges(data=True):
        capacity = float(data.get("capacity", 0.0) or 0.0)
        if capacity > 0 and math.isfinite(capacity) and capacity < 999999:
            data["raw_capacity"] = capacity
            data["capacity"] = capacity * factor


def _gate_queue_node_name(gate):
    return f"{gate}_Queue"


def _configured_gate_queue_lines(G):
    raw = G.graph.get("gate_queue_area_lines", GATE_QUEUE_AREA_LINES_DEFAULT)
    if isinstance(raw, str):
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return tuple(str(part).strip() for part in raw if str(part).strip())


def _edge_capacity_for_new_link(G, u, v, width_limit=None):
    if spr.is_capacity_service_node(G, v):
        cap = float(G.nodes[v].get("capacity", float("inf")))
    elif spr.is_capacity_service_node(G, u):
        cap = float(G.nodes[v].get("capacity", float("inf")))
    else:
        cap = min(
            float(G.nodes[u].get("capacity", float("inf"))),
            float(G.nodes[v].get("capacity", float("inf"))),
        )
    if width_limit is not None:
        cap = min(cap, calculate_gb_capacity_per_second("passageway", width_limit))
    return cap


def _scrub_edge_runtime_cache(data):
    for key in (
        "_resource_id_cache",
        "_effective_area_cache",
        "_physical_travel_time_cache",
        "_physical_travel_time_cache_step",
        "runtime_density",
    ):
        data.pop(key, None)
    return data


def _gate_physical_width_m(G, gate, incoming=None):
    """Return the physical width used to size a gate queue area.

    Gate configuration ``width`` is a unit count used by the capacity model,
    not a length in metres. Formal gate records therefore provide a separate
    physical bank width. Incoming passage widths are retained only as a
    compatibility fallback for custom graphs without that configuration.
    """
    gate_data = G.nodes[gate]
    for key in ("queue_width_m", "physical_width_m", "width_m"):
        value = gate_data.get(key)
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0.0:
            return value, f"configured:{key}"

    edges = incoming
    if edges is None:
        edges = list(G.in_edges(gate, data=True))
    widths = []
    for _, _, edge_data in edges:
        value = edge_data.get("width_limit")
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0.0:
            widths.append(value)
    if widths:
        return float(statistics.median(widths)), "edge_width_limit_m:median"

    # Keep hand-built regression graphs working when no geometric width exists.
    unit_count = gate_data.get("width", 1.0)
    try:
        unit_count = float(unit_count)
    except (TypeError, ValueError):
        unit_count = 1.0
    return max(unit_count, 0.1), "legacy_gate_unit_count_fallback"


def _insert_gate_queue_area_nodes(G):
    """Insert finite front-of-gate queue areas for configured gate groups.

    The area is an engineering approximation for stations without a surveyed
    queue polygon: queue area = physical gate width * configured line depth.
    Gate unit counts remain the source for service capacity and queue-edge
    capacity; they are not treated as metres.
    """
    if not bool(G.graph.get("gate_queue_areas_enabled", GATE_QUEUE_AREAS_ENABLED_DEFAULT)):
        G.graph["gate_queue_area_nodes"] = {}
        return

    fallback_depth_m = max(
        float(G.graph.get("gate_queue_depth_m", GATE_QUEUE_DEPTH_M_DEFAULT)),
        0.1,
    )
    configured_depths = dict(
        G.graph.get(
            "gate_queue_depth_m_by_line",
            GATE_QUEUE_DEPTH_M_BY_LINE_DEFAULT,
        )
    )
    line_ids = _configured_gate_queue_lines(G)
    queue_nodes = {}
    queue_widths_m = {}
    depth_by_line = {}

    for line_id in line_ids:
        depth_m = max(
            float(configured_depths.get(line_id, fallback_depth_m)),
            0.1,
        )
        depth_by_line[line_id] = depth_m
        gate_group = f"{line_id}_GATES"
        for gate in NODES_DATA.get(gate_group, {}):
            if gate not in G.nodes:
                continue
            queue_node = _gate_queue_node_name(gate)
            if queue_node in G.nodes:
                queue_nodes[gate] = queue_node
                continue

            incoming = [
                (u, gate, dict(data))
                for u, _, data in list(G.in_edges(gate, data=True))
                if u != queue_node
            ]
            if not incoming:
                continue

            gate_data = G.nodes[gate]
            queue_width_units = max(float(gate_data.get("width", 1.0)), 0.1)
            queue_width_m, width_source = _gate_physical_width_m(
                G, gate, incoming
            )
            queue_width_m = max(float(queue_width_m), 0.1)
            queue_area = max(queue_width_m * depth_m, 0.1)
            gate_pos = gate_data.get("pos")
            pred_positions = [
                G.nodes[u].get("pos")
                for u, _, _ in incoming
                if G.nodes[u].get("pos") is not None
            ]
            if gate_pos and pred_positions:
                avg_x = sum(pos[0] for pos in pred_positions) / len(pred_positions)
                avg_y = sum(pos[1] for pos in pred_positions) / len(pred_positions)
                queue_pos = (
                    0.75 * float(gate_pos[0]) + 0.25 * avg_x,
                    0.75 * float(gate_pos[1]) + 0.25 * avg_y,
                )
            else:
                queue_pos = gate_pos

            G.add_node(
                queue_node,
                pos=queue_pos,
                type="queue_area",
                width=queue_width_units,
                capacity=calculate_gb_capacity_per_second(
                    "passageway", queue_width_units
                ),
                area=queue_area,
                manual_area=queue_area,
                area_source="line_specific_gate_queue_depth",
                queue_width_m=queue_width_m,
                queue_width_source=width_source,
                gate_unit_count=queue_width_units,
                queue_depth_m=depth_m,
                queue_for_gate=gate,
                density_exempt=False,
                spatial_storage_enabled=True,
                people=0,
            )

            service_len = min(
                max(float(G.graph.get("gate_queue_service_edge_length_m", GATE_QUEUE_SERVICE_EDGE_LENGTH_M)), 0.0),
                depth_m,
            )
            for u, _, edge_data in incoming:
                original_len = max(float(edge_data.get("length", 0.0) or 0.0), 0.0)
                approach_len = max(original_len - service_len, 0.0)
                width_limit = edge_data.get("width_limit")
                approach_data = _scrub_edge_runtime_cache(edge_data)
                approach_data.update({
                    "length": approach_len,
                    "capacity": _edge_capacity_for_new_link(G, u, queue_node, width_limit),
                    "gate_queue_target": gate,
                })
                G.remove_edge(u, gate)
                G.add_edge(u, queue_node, **approach_data)

            G.add_edge(
                queue_node,
                gate,
                length=service_len,
                capacity=float(gate_data.get("capacity", float("inf"))),
                edge_type="queue_to_gate",
                width_limit=queue_width_m,
                distance_source="line_specific_gate_queue_depth",
                gate_queue_source=queue_node,
            )
            queue_nodes[gate] = queue_node
            queue_widths_m[gate] = queue_width_m

    G.graph["gate_queue_area_nodes"] = queue_nodes
    # Keep the scalar key for compatibility; the per-line map is authoritative.
    G.graph["gate_queue_area_depth_m"] = fallback_depth_m
    G.graph["gate_queue_area_depth_m_by_line"] = depth_by_line
    G.graph["gate_queue_physical_width_m"] = queue_widths_m


def fruin_speed(density):
    return spr.paper_speed_from_density(density)


# ==============================================================================
# 3. 动态建图与改进放人引擎
# ==============================================================================


def _median_positive(values, default=None):
    positive = [float(v) for v in values if v is not None and float(v) > 0]
    if not positive:
        return default
    return float(statistics.median(positive))


def _estimate_virtual_representative_length(G, node):
    """为通道型 virtual 节点估算其代表长度，用于 area = width * length。

    virtual 节点代表“到达该节点前的一段通道空间”，所以优先使用入边长度。
    例如 Gate -> VN_L7_Corner_1，VN 的面积就按闸机到该 VN 的通道长度估算。
    """
    in_lengths = [
        float(G[pred][node].get("length", 0.0))
        for pred in G.predecessors(node)
        if float(G[pred][node].get("length", 0.0)) > 0
    ]
    out_lengths = [
        float(G[node][succ].get("length", 0.0))
        for succ in G.successors(node)
        if float(G[node][succ].get("length", 0.0)) > 0
    ]

    in_med = _median_positive(in_lengths)
    out_med = _median_positive(out_lengths)
    if in_med is not None:
        return in_med, "incoming_edge_median"
    if out_med is not None:
        return out_med, "outgoing_edge_median"
    return 2.0, "fallback_2m"


def _estimate_virtual_area(G, node):
    """为 virtual 节点估算局部节点面积。

    每条入边的通道面积会单独写入 edge_area，不在这里相加，避免多条路径
    部分重合时把同一片空间重复计入节点面积。
    """
    incident_areas = []
    for pred in G.predecessors(node):
        edge_data = G[pred][node]
        length = float(edge_data.get("length", 0.0))
        if length <= 0:
            continue
        width = edge_data.get("width_limit")
        if width is None or float(width) <= 0:
            width = G.nodes[node].get("width", 0.0)
        width = float(width)
        if width <= 0:
            continue
        edge_data["edge_area"] = length * width
        incident_areas.append(edge_data["edge_area"])

    for succ in G.successors(node):
        edge_data = G[node][succ]
        length = float(edge_data.get("length", 0.0))
        if length <= 0:
            continue
        width = edge_data.get("width_limit")
        if width is None or float(width) <= 0:
            width = G.nodes[node].get("downstream_width") or G.nodes[node].get("width", 0.0)
        width = float(width)
        if width <= 0:
            continue
        edge_data["edge_area"] = length * width
        incident_areas.append(edge_data["edge_area"])

    explicit_area = float(G.nodes[node].get("manual_area", 0.0) or 0.0)
    if explicit_area > 0:
        width = max(float(G.nodes[node].get("width", 1.0)), 0.1)
        return explicit_area, explicit_area / width, "manual_local_area"

    if incident_areas:
        local_area = max(min(incident_areas), 0.1)
        width = max(float(G.nodes[node].get("width", 1.0)), 0.1)
        return local_area, local_area / width, "fallback_min_incident_edge_area"

    representative_length, source = _estimate_virtual_representative_length(G, node)
    width = max(float(G.nodes[node].get("width", 1.0)), 0.1)
    return max(width * representative_length, 0.1), representative_length, source


def _auto_update_virtual_node_areas(G):
    """virtual 节点保留局部面积；相邻通道面积逐条写入边属性 edge_area。"""
    for node, data in G.nodes(data=True):
        if data.get("type") != "virtual":
            continue
        width = float(data.get("width", 0.0))
        if width <= 0:
            width = _median_positive(
                [G[pred][node].get("width_limit") for pred in G.predecessors(node)]
                + [G[node][succ].get("width_limit") for succ in G.successors(node)],
                default=1.0,
            )
        auto_area, representative_length, source = _estimate_virtual_area(G, node)
        data["representative_length"] = representative_length
        data["area"] = auto_area
        data["area_source"] = f"auto_virtual:{source}"


def build_graph(*, enable_l7_common_hall_vertical_integration=False):
    global _CONFIG_WARNING_EMITTED
    G = nx.DiGraph()
    G.graph["improved_gate_queue_term"] = IMPROVED_GATE_QUEUE_TERM
    G.graph["improved_shared_travel_time"] = IMPROVED_SHARED_TRAVEL_TIME
    # Formal station runs use the corresponding physical Gate Queue footprint
    # as the finite service-buffer area.  Small hand-built test graphs that do
    # not set this mapping retain the historical exempt behavior.
    G.graph["service_node_spatial_storage_mode"] = "queue_area"

    # 1. 自动加平台与出口
    for name, attr in NODES_DATA.items():
        if isinstance(attr, dict) and attr.get("type") == "platform":
            G.add_node(name, **attr, people=0, capacity=999999)

    for name, attr in NODES_DATA.get("ALL_EXITS", {}).items():
        exit_width = attr.get("width")
        try:
            exit_width = float(exit_width)
        except (TypeError, ValueError):
            exit_width = 0.0
        G.add_node(
            name,
            **attr,
            type="exit",
            people=0,
            area=100.0,
            capacity=float("inf"),
            exit_opening_width_m=exit_width,
        )

    # 2. 自动加其他所有设施 (安全解析字典)
    for group_name, items in NODES_DATA.items():
        if group_name.endswith("_VERTICALS") or group_name == "TRANSFERS":
            for name, attr in items.items():
                ftype, w, direction, pos = attr[0], attr[1], attr[2], attr[3]
                direction = str(direction).strip().lower()
                area = attr[4] if len(attr) == 5 else w * 2.0
                cap_s = calculate_gb_capacity_per_second(ftype, w, direction)
                is_topological_service = str(ftype).strip().lower() in {"stair", "escalator"}
                G.add_node(
                    name,
                    pos=pos,
                    type=ftype,
                    width=w,
                    direction=direction,
                    capacity=cap_s,
                    area=area,
                    people=0,
                    density_exempt=is_topological_service,
                    spatial_storage_enabled=not is_topological_service,
                )
        elif group_name.endswith("_GATES"):
            for name, attr in items.items():
                ftype, count, direction, pos = attr[0], attr[1], attr[2], attr[3]
                direction = str(direction).strip().lower()
                cap_s = calculate_gb_capacity_per_second(ftype, count, direction)
                configured_area = attr[4] if len(attr) >= 5 else None
                configured_queue_width_m = attr[5] if len(attr) >= 6 else None
                area = (
                    float(configured_area)
                    if configured_area is not None
                    else float(count) * DEFAULT_GATE_AREA_PER_UNIT_M2
                )
                G.add_node(
                    name,
                    pos=pos,
                    type=ftype,
                    width=count,
                    direction=direction,
                    capacity=cap_s,
                    area=area,
                    area_source=("configured" if configured_area is not None else "default_gate_rule"),
                    queue_width_m=(
                        float(configured_queue_width_m)
                        if configured_queue_width_m is not None
                        else None
                    ),
                    density_exempt=True,
                    spatial_storage_enabled=False,
                    people=0,
                )
        elif group_name.endswith("_VIRTUALS"):
            for name, attr in items.items():
                ftype, w_down, measured_area, pos = attr[0], attr[1], attr[2], attr[3]
                downstream_width = float(attr[4]) if len(attr) >= 5 else None
                cap_out = calculate_gb_capacity_per_second("passageway", w_down)
                G.add_node(
                    name,
                    pos=pos,
                    type=ftype,
                    width=w_down,
                    capacity=cap_out,
                    area=measured_area,
                    manual_area=measured_area,
                    downstream_width=downstream_width,
                    people=0,
                )

    # 3. 为需要细分的站台动态构建“等待区分区节点”
    _add_platform_waiting_zone_nodes_and_edges(G)

    # 4. 动态构建 站台->垂直设施 的边
    for line_id, spec in PLATFORM_VERTICAL_SPECS.items():
        platform_node = spec["platform_node"]
        vertical_group = spec["vertical_group"]

        if _platform_waiting_zone_defs_ready(line_id):
            continue

        if vertical_group not in NODES_DATA:
            raise ValueError(f"\n[配置致命错误] 线路 '{line_id}' 引用了不存在的垂直设施组 '{vertical_group}'！")

        delta_h = get_delta_h(line_id)

        for v_name in NODES_DATA[vertical_group].keys():
            if v_name not in PRECALCULATED_PLATFORM_DISTS:
                raise ValueError(f"\n[数据缺失]：字典中未找到 '{v_name}' 的距离，请检查 calc_platform_dists.py！")

            horizontal_dist = PRECALCULATED_PLATFORM_DISTS[v_name]
            total_edge_length = horizontal_dist + 2.0 * delta_h
            G.add_edge(platform_node, v_name, length=total_edge_length, capacity=G.nodes[v_name]["capacity"], edge_type="platform_to_vertical")

    # 5. 读取其余静态边
    CAD_TO_METER_SCALE = 0.01
    undefined_edges = [
        (e["u"], e["v"], e.get("edge_type", ""))
        for e in EDGES_DATA
        if e["u"] not in G.nodes or e["v"] not in G.nodes
    ]
    if undefined_edges:
        details = "; ".join(
            f"{u} -> {v} [{group or 'unspecified'}], missing="
            f"{u if u not in G.nodes else v}"
            for u, v, group in undefined_edges
        )
        raise ValueError(f"Undefined nodes referenced by configured edges: {details}")

    euclidean_fallback_edges = []
    for e in EDGES_DATA:
        u, v, orig_dist, w_limit = e["u"], e["v"], e["length"], e.get("width_limit")
        edge_type = e.get("edge_type", "")

        distance_source = "configured"
        if (
            edge_type in ["vertical_to_exit", "virtual_to_exit"]
            and G.nodes[v].get("type") == "exit"
        ):
            line_key = None
            for key in sorted(STATION_LEVELS.keys(), key=len, reverse=True):
                if key in u:
                    line_key = key
                    break
            if line_key:
                hall_height = STATION_LEVELS[line_key]["hall"]
                stair_length = abs(hall_height - 0.0) * 2.0
                dist = stair_length + 2.0
            else:
                dist = 2.0
        elif orig_dist is None:
            pos_u = G.nodes[u].get("pos")
            pos_v = G.nodes[v].get("pos")
            if pos_u and pos_v:
                plane_dist = math.sqrt((pos_u[0] - pos_v[0]) ** 2 + (pos_u[1] - pos_v[1]) ** 2)
                dist = plane_dist * CAD_TO_METER_SCALE
                distance_source = "euclidean_fallback"
                euclidean_fallback_edges.append((u, v, dist))
            else:
                raise ValueError(f"\n[距离缺失致命错误] 边 {u} -> {v} 填了 None，但节点没有配置 pos 坐标！")
        else:
            dist = float(orig_dist)

        source_is_service = spr.is_capacity_service_node(G, u)
        destination_is_service = spr.is_capacity_service_node(G, v)
        if destination_is_service:
            # Admission into the destination facility consumes that facility's
            # shared resource exactly once.
            cap = float(G.nodes[v].get("capacity", float("inf")))
        elif source_is_service:
            # The source facility was already metered on entry. Its service
            # rate must not be copied onto the outgoing corridor resource.
            cap = float(G.nodes[v].get("capacity", float("inf")))
        else:
            cap = min(
                G.nodes[u].get("capacity", float("inf")),
                G.nodes[v].get("capacity", float("inf")),
            )
        if w_limit is not None:
            cap = min(cap, calculate_gb_capacity_per_second("passageway", w_limit))

        G.add_edge(
            u, v, length=dist, capacity=cap, edge_type=edge_type,
            width_limit=w_limit, distance_source=distance_source,
        )
    G.graph["euclidean_fallback_edges"] = euclidean_fallback_edges
    _insert_gate_queue_area_nodes(G)
    _auto_update_virtual_node_areas(G)
    # =================================================================
    # 🌟 动态构建“列车车厢节点”与“车门瓶颈连线”
    # =================================================================
    for line_id, physics in TRAIN_PHYSICS.items():
        p_node = f"Platform_{line_id}"
        if p_node not in G.nodes:
            continue

        door_capacity = calculate_gb_capacity_per_second("passageway", physics["door_w"])
        car_area = physics["area_per_car"]
        door_count = max(int(physics.get("doors_per_car", 1)), 1)
        car_count = max(int(physics.get("cars", 1)), 1)
        train_count = max(int(physics.get("trains", 2)), 1)
        train_spans = physics.get("train_spans", [])
        platform_pos = G.nodes[p_node].get("pos", (0, 0))

        for train_idx in range(1, train_count + 1):
            train_span = train_spans[train_idx - 1] if train_idx - 1 < len(train_spans) else None

            for car_idx in range(1, car_count + 1):
                car_node = f"Train_{line_id}_{train_idx}_Car{car_idx}"
                car_pos = _layout_point_from_span(train_span, car_idx, 0, car_count, door_count, platform_pos)

                G.add_node(
                    car_node,
                    type="train_car",
                    capacity=999999,
                    area=car_area,
                    people=0,
                    pos=car_pos,
                    line_id=line_id,
                    train_index=train_idx,
                    car_index=car_idx,
                )

                door_specs = []
                if line_id == "Maglev":
                    band_spans = _maglev_band_spans_by_train().get(train_idx, {})
                    if band_spans:
                        side_door_count = max(door_count // max(len(band_spans), 1), 1)
                        door_seq = 1
                        for band_name, side_span in band_spans.items():
                            for side_door_idx in range(1, side_door_count + 1):
                                door_specs.append(
                                    {
                                        "door_index": door_seq,
                                        "band": band_name,
                                        "pos": _layout_point_from_span(
                                            side_span,
                                            car_idx,
                                            side_door_idx,
                                            car_count,
                                            side_door_count,
                                            platform_pos,
                                        ),
                                    }
                                )
                                door_seq += 1

                if not door_specs:
                    for door_idx in range(1, door_count + 1):
                        door_specs.append(
                            {
                                "door_index": door_idx,
                                "band": None,
                                "pos": _layout_point_from_span(
                                    train_span,
                                    car_idx,
                                    door_idx,
                                    car_count,
                                    door_count,
                                    platform_pos,
                                ),
                            }
                        )

                for door_spec in door_specs:
                    door_idx = int(door_spec["door_index"])
                    door_node = f"{car_node}_Door{door_idx}"
                    door_pos = door_spec["pos"]
                    wait_zone_name = _platform_waiting_zone_name(
                        line_id,
                        train_idx,
                        car_idx,
                        band=door_spec.get("band"),
                    )
                    door_target = wait_zone_name if wait_zone_name in G.nodes else p_node

                    G.add_node(
                        door_node,
                        type="train",
                        capacity=999999,
                        area=max(car_area / max(len(door_specs), 1), 1.0),
                        people=0,
                        pos=door_pos,
                        line_id=line_id,
                        train_index=train_idx,
                        car_index=car_idx,
                        door_index=door_idx,
                        waiting_band=door_spec.get("band"),
                    )

                    G.add_edge(
                        car_node,
                        door_node,
                        length=0.2,
                        capacity=door_capacity,
                        edge_type="car_to_door",
                    )
                    G.add_edge(
                        door_node,
                        door_target,
                        length=1.0,
                        capacity=door_capacity,
                        edge_type="train_door",
                    )

    _ensure_hall_staging_nodes(G)
    _connect_l7_gate_queues_for_lateral_switching(G)
    G.graph["l7_common_hall_vertical_integration_enabled"] = bool(
        enable_l7_common_hall_vertical_integration
    )
    if enable_l7_common_hall_vertical_integration:
        _rewire_l7_verticals_to_common_hall(G)
    else:
        # The full-station baseline keeps the original vertical-to-gate
        # approaches.  The common-hall upstream integration is reserved for
        # the isolated mechanism trial until its topology is separately
        # accepted.
        G.graph["l7_common_hall_topology_audit"] = []
    _annotate_aa_evacuation_stages_and_replan_scope(G)
    G.graph["gate_approach_connectivity"] = _build_gate_approach_connectivity_report(G)
    _apply_obstacle_areas(G)
    _apply_pathfinder_capacity_calibration(G)
    default_gate_nodes = sorted(
        node
        for node, data in G.nodes(data=True)
        if data.get("area_source") == "default_gate_rule"
    )
    configuration_warnings = []
    if default_gate_nodes:
        configuration_warnings.append(
            f"{len(default_gate_nodes)} gate nodes use the centralized default area rule; "
            "see G.graph['default_gate_area_nodes'] for names"
        )
    if G.graph.get("euclidean_fallback_edges"):
        configuration_warnings.append(
            f"{len(G.graph['euclidean_fallback_edges'])} edges use euclidean_fallback distances"
        )
    G.graph["configuration_warnings"] = configuration_warnings
    G.graph["default_gate_area_nodes"] = default_gate_nodes
    if configuration_warnings and not _CONFIG_WARNING_EMITTED:
        warnings.warn("; ".join(configuration_warnings), RuntimeWarning, stacklevel=2)
        _CONFIG_WARNING_EMITTED = True
    return G


def write_configuration_validation_report(G, output_path):
    """Write every geometry fallback and centralized gate-area default."""
    lines = ["# Configuration validation report", ""]
    lines.append("## Gate areas using the centralized default")
    lines.append("")
    default_gates = G.graph.get("default_gate_area_nodes", [])
    if default_gates:
        lines.extend(f"- {node}" for node in default_gates)
    else:
        lines.append("- None")
    lines.extend(["", "## Euclidean fallback edges", ""])
    fallback_edges = G.graph.get("euclidean_fallback_edges", [])
    if fallback_edges:
        lines.extend(
            f"- {u} -> {v}: {distance:.3f} m"
            for u, v, distance in fallback_edges
        )
    else:
        lines.append("- None")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")



def init_people(G, pop_dict, apply_noise=False, rng=None):
    # 重置清空
    for n in G.nodes():
        G.nodes[n]["people"] = 0
        G.nodes[n]["people_dict"] = {l: 0 for l in ALL_LINE_IDS}
        G.nodes[n]["source_group_dict"] = {}
        G.nodes[n].pop("_mesoscopic_cohorts", None)
        G.nodes[n].pop("_aa_batches", None)

    has_detailed_train = any(d.get("type") == "train_car" for _, d in G.nodes(data=True))

    for line_id, spec in PLATFORM_VERTICAL_SPECS.items():
        p_node = spec["platform_node"]
        if p_node in G.nodes and line_id in pop_dict:
            line_data = pop_dict[line_id]
            physics = TRAIN_PHYSICS.get(line_id, {})
            train_count = max(int(physics.get("trains", 2)), 1)

            # 1. 放入车厢
            if has_detailed_train:
                for train_idx in range(1, train_count + 1):
                    key = f"train_{train_idx}"
                    source_group_id = _source_group_id(line_id, key)
                    car_nodes = _sorted_train_car_nodes(G, line_id, train_idx)
                    total_people = int(round(float(line_data.get(key, 0))))

                    if not car_nodes or total_people <= 0:
                        continue

                    car_alloc = _integer_capped_allocation(total_people, [1.0] * len(car_nodes))
                    for car_node, assigned in zip(car_nodes, car_alloc):
                        if assigned <= 0:
                            continue
                        active_source_group_id = source_group_id
                        if (
                            G.graph.get("split_l2_train_source_groups_by_zone")
                            and line_id == "L2"
                        ):
                            car_idx = 0
                            for part in str(car_node).split("_"):
                                if part.startswith("Car"):
                                    try:
                                        car_idx = int(part[3:])
                                    except ValueError:
                                        car_idx = 0
                                    break
                            if car_idx > 0:
                                active_source_group_id = _train_zone_source_group_id(
                                    line_id,
                                    train_idx,
                                    _l2_train_zone_key_for_car(car_idx),
                                )
                        G.nodes[car_node]["people"] = assigned
                        G.nodes[car_node]["people_dict"][line_id] = assigned
                        G.nodes[car_node]["source_group_dict"][active_source_group_id] = (
                            G.nodes[car_node]["source_group_dict"].get(active_source_group_id, 0)
                            + assigned
                        )
            else:
                if f"Train_{line_id}_1" in G.nodes:
                    assigned = int(round(float(line_data.get("train_1", 0))))
                    G.nodes[f"Train_{line_id}_1"]["people"] = assigned
                    G.nodes[f"Train_{line_id}_1"]["people_dict"][line_id] = assigned
                    if assigned > 0:
                        G.nodes[f"Train_{line_id}_1"]["source_group_dict"][_source_group_id(line_id, "train_1")] = assigned
                if f"Train_{line_id}_2" in G.nodes:
                    assigned = int(round(float(line_data.get("train_2", 0))))
                    G.nodes[f"Train_{line_id}_2"]["people"] = assigned
                    G.nodes[f"Train_{line_id}_2"]["people_dict"][line_id] = assigned
                    if assigned > 0:
                        G.nodes[f"Train_{line_id}_2"]["source_group_dict"][_source_group_id(line_id, "train_2")] = assigned

            # 2. 放入【站台等待区】
            platform_waiting = int(round(float(line_data.get("platform_waiting", 0))))
            waiting_zone_defs = _platform_waiting_zone_defs(line_id)
            waiting_zone_nodes = _platform_waiting_zone_nodes(G, line_id)
            if waiting_zone_defs and waiting_zone_nodes:
                waiting_zone_source_groups = [
                    _platform_waiting_zone_source_group_id(line_id, zone_name)
                    for zone_name in waiting_zone_nodes
                ]
                _add_people_to_nodes_by_weights(
                    G,
                    waiting_zone_nodes,
                    line_id,
                    platform_waiting,
                    _platform_waiting_zone_area_weights(waiting_zone_defs),
                    source_group_ids=waiting_zone_source_groups,
                )
            else:
                G.nodes[p_node]["people"] = platform_waiting
                G.nodes[p_node]["people_dict"][line_id] = platform_waiting
                if platform_waiting > 0:
                    G.nodes[p_node]["source_group_dict"][_source_group_id(line_id, "platform_waiting")] = platform_waiting

            # 3. 放入【站厅闸机区】
            hall_people = int(round(float(line_data.get("hall_people", 0))))
            gate_group_name = spec.get("gate_group", f"{line_id}_GATES")
            valid_gates = [n for n in NODES_DATA.get(gate_group_name, {}) if n in G.nodes]
            hall_staging_nodes = _hall_staging_nodes_for_line(G, line_id)

            # Initial conditions must not depend on whether spillback is enabled
            # for a diagnostic run. Hall occupants always start in the same
            # physical staging areas; only subsequent receiving rules differ.
            if hall_staging_nodes and hall_people > 0:
                staging_weights = [
                    max(float(G.nodes[n].get("area", 1.0)), 0.1)
                    for n in hall_staging_nodes
                ]
                _add_people_to_nodes_by_weights(
                    G,
                    hall_staging_nodes,
                    line_id,
                    hall_people,
                    staging_weights,
                    source_group_id=_source_group_id(line_id, "hall_people"),
                )
            elif valid_gates and hall_people > 0:
                base_weights = [G.nodes[n].get("capacity", 1.0) for n in valid_gates]
                _add_people_to_nodes_by_weights(
                    G,
                    valid_gates,
                    line_id,
                    hall_people,
                    base_weights,
                    source_group_id=_source_group_id(line_id, "hall_people"),
                )

            # 4. 放入【换乘通道区】
            transfer_people = int(round(float(line_data.get("transfer_people", 0))))
            valid_transfers = _transfer_nodes_for_source_line(G, line_id)

            if valid_transfers and transfer_people > 0:
                base_weights = [G.nodes[n].get("capacity", 1.0) for n in valid_transfers]
                transfer_source_groups = [
                    _transfer_relation_source_group_id(line_id, node_name)
                    for node_name in valid_transfers
                ]
                _add_people_to_nodes_by_weights(
                    G,
                    valid_transfers,
                    line_id,
                    transfer_people,
                    base_weights,
                    source_group_ids=transfer_source_groups,
                )

    # 每次初始化都重置仿真时钟和在途队列，避免上一次运行残留影响本次结果
    G.graph["_sim_time"] = 0.0
    G.graph["_transit_queue"] = []
    G.graph["_transit_queue_version"] = 0
    G.graph.pop("_aa_resource_event_indices_cache", None)
    G.graph.pop("_confirmed_resource_arrivals_cache", None)
    G.graph.pop("_aa_transit_spatial_events_cache", None)
    G.graph.pop("_aa_spatial_occupancy_prefix_cache", None)
    G.graph.pop("_aa_step_edge_records", None)
    G.graph.pop("_aa_step_edge_records_time", None)
    G.graph.pop("_aa_step_capacity_time", None)
    G.graph.pop("_aa_step_resource_capacity", None)
    G.graph.pop("_aa_queue_adjustment_versions", None)
    G.graph.pop("_aa_round_prediction_events", None)
    G.graph.pop("_aa_round_prediction_events_version", None)
    G.graph["_evacuation_arrival_events"] = []
    G.graph["_mesoscopic_cohort_sequence"] = 0
    G.graph["_aa_batch_sequence"] = 0
    G.graph["_aa_round_prediction_events"] = []
    G.graph["_aa_round_spatial_events"] = []
    G.graph.pop("_aa_accepted_allocations", None)
    G.graph.pop("_aa_diagnostics", None)
    G.graph.pop("_aa_gate_replan_diagnostics", None)
    G.graph.pop("_aa_gate_switch_events", None)
    G.graph.pop("_l7_hall_decision_diagnostics", None)
    G.graph.pop("_l7_hall_common_decision_summary", None)
    G.graph.pop("_gate_directed_path_cache", None)
    G.graph["_aa_prediction_accuracy"] = []
    G.graph["_aa_density_risk_stats"] = {}
    G.graph.pop("_mesoscopic_accepted_allocations", None)
    G.graph.pop("_mesoscopic_diagnostics", None)
    G.graph.pop("_routing_decision_option_cache", None)
    G.graph.pop("_mesoscopic_resource_execution", None)
    G.graph.pop("_mesoscopic_reachable_demand", None)
    G.graph.pop("_mesoscopic_entry_resources", None)
    G.graph.pop("_mesoscopic_descendants_cache", None)
    G.graph["_resource_flow_credit"] = {}
    G.graph["_edge_flow_credit"] = G.graph["_resource_flow_credit"]
    G.graph.pop("_aa_step_capacity_time", None)
    G.graph.pop("_aa_step_resource_capacity", None)
    G.graph["_resource_queues"] = {}
    G.graph["_resource_queue_sources"] = {}
    G.graph["_current_gate_upstream_spillback_sources"] = {}
    G.graph.pop("_gate_backlog_diagnostics", None)
    G.graph.pop("_gate_backlog_step_trace", None)
    G.graph["_resource_max_predicted_wait"] = {}
    G.graph["_spatial_rejected_inflow"] = {}
    G.graph.pop("_single_path_case_line", None)
    G.graph.pop("_paper_high_cost_signature", None)
    G.graph.pop("_paper_high_cost_active_edges", None)
    G.graph.pop("_paper_high_cost_control_densities", None)
    G.graph.pop("_paper_high_cost_normal_costs", None)
    G.graph.pop("_paper_high_cost_recovery_times", None)
    G.graph.pop("_improved_temporary_high_cost_diagnostics", None)
    G.graph.pop("_improved_temporary_high_cost_trace", None)
    G.graph.pop(
        "_improved_temporary_high_cost_step_diagnostics", None
    )
    G.graph.pop("_dyn_weight_step", None)
    G.graph.pop("_paper_path_by_node", None)
    G.graph.pop("_paper_fixed_next_by_node", None)
    G.graph.pop("_paper_exit_coverage_used", None)
    G.graph.pop("_paper_exit_coverage_used_gates", None)
    G.graph.pop("_paper_exit_coverage_locked_paths", None)
    G.graph.pop("_paper_gate_density_log_state", None)
    G.graph.pop("_our_guidance_state", None)
    _initialize_executed_route_tracking(G)



def apply_capacity_noise(G, rng, low=0.95, high=1.05):
    for u, v, edge_data in G.edges(data=True):
        if "capacity" in edge_data and edge_data["capacity"] != float("inf"):
            edge_data["capacity"] *= rng.uniform(low, high)


# ==============================================================================
# 4. 动态仿真与路径算法
# ==============================================================================
def get_best_next_node(G, current_node, method, shortest_dists):
    source_node = _representative_routing_source(G, current_node)
    return spr.get_best_next_node(G, source_node, method, shortest_dists, fruin_speed)


def get_best_path_to_exit(G, current_node, method, shortest_dists):
    source_node = _representative_routing_source(G, current_node)
    return spr.get_best_path_to_exit(G, source_node, method, shortest_dists, fruin_speed)

def simulate_to_time(G_base, pop_dict, method, target_time):
    G = copy.deepcopy(G_base)
    init_people(G, pop_dict, apply_noise=False)
    shortest_dists = _shortest_distances_to_exits(G)

    time = 0
    while time < target_time:
        advance_simulation_step(G, method, shortest_dists)
        time += DELTA_T

    return G, shortest_dists



def format_path(path):
    if not path:
        return "N/A"
    return " -> ".join([n.replace("Platform_", "").replace("Gate_", "").replace("Exit_", "") for n in path])


def first_divergence(path_a, path_b):
    if not path_a or not path_b:
        return "N/A"
    n = min(len(path_a), len(path_b))
    for i in range(n):
        if path_a[i] != path_b[i]:
            return path_a[i]
    return "None"


def save_route_comparison_table(
    G_baseline,
    G_guided,
    shortest_dists,
    source_nodes,
    filename,
    baseline_method=PAPER_SINGLE_PATH_METHOD,
    guided_method=OUR_SINGLE_PATH_METHOD,
):
    rows = []
    for src in source_nodes:
        baseline_path = get_best_path_to_exit(G_baseline, src, baseline_method, shortest_dists)
        guided_path = get_best_path_to_exit(G_guided, src, guided_method, shortest_dists)

        baseline_len = _path_total_length(G_baseline, baseline_path) if baseline_path else None
        guided_len = _path_total_length(G_guided, guided_path) if guided_path else None

        rows.append({
            "source": src,
            "baseline_method": _method_display_name(baseline_method),
            "baseline_path": format_path(baseline_path),
            "guided_method": _method_display_name(guided_method),
            "guided_path": format_path(guided_path),
            "first_divergence": first_divergence(baseline_path, guided_path),
            "baseline_length": baseline_len,
            "guided_length": guided_len,
            "length_reduction_pct": (
                ((baseline_len - guided_len) / baseline_len * 100)
                if baseline_len and guided_len and baseline_len > 0
                else 0.0
            ),
        })

    pd.DataFrame(rows).to_csv(_output_path(filename), index=False, encoding="utf-8-sig")
    return rows


def rank_bottlenecks(G, metrics, top_k=10):
    rows = []
    node_stats = metrics.get("node_stats", {})
    for n, stat in node_stats.items():
        if G.nodes[n].get("type") == "exit":
            continue
        rows.append({
            "node": n,
            "type": G.nodes[n].get("type", ""),
            "peak_people": stat.get("peak_people", 0.0),
            "peak_physical_people": stat.get("peak_physical_people", stat.get("peak_people", 0.0)),
            "peak_overflow_queue": stat.get("peak_overflow_queue", 0.0),
            "peak_density": stat.get("peak_density", 0.0),
            "peak_load_ratio": stat.get("peak_load_ratio", 0.0),
            "peak_congestion_index": stat.get("peak_congestion_index", stat.get("peak_density", 0.0)),
            "congestion_measure_type": stat.get("congestion_measure_type", ""),
            "congestion_index_seconds": stat.get("congestion_index_seconds", stat.get("density_seconds", 0.0)),
            "queue_seconds": stat.get("queue_seconds", 0.0),
            "congestion_seconds": stat.get("congestion_seconds", 0.0)
        })

    rows.sort(key=lambda x: (x["queue_seconds"], x["peak_congestion_index"]), reverse=True)
    return rows[:top_k]

def rank_instantaneous_bottlenecks(G_state, top_k=10):
    """专门针对特定时刻切片的瞬时瓶颈排名，使用空间密度或设施容量占用率。"""
    rows = []
    for n in G_state.nodes():
        if G_state.nodes[n].get("type") == "exit":
            continue
        ppl = G_state.nodes[n].get("people", 0)
        congestion_index, measure_type = _node_congestion_index(G_state, n)
        rows.append({
            "node": n,
            "type": G_state.nodes[n].get("type", ""),
            "instant_people": ppl,
            "instant_density": congestion_index,
            "instant_congestion_index": congestion_index,
            "congestion_measure_type": measure_type,
        })
    # 按瞬时排队人数降序排列
    rows.sort(key=lambda x: x["instant_congestion_index"], reverse=True)
    return rows[:top_k]

def advance_simulation_step(G, method, shortest_dists):
    """推进单个仿真步。支持在途旅行时间与多后继分流。"""
    current_time, _ = _ensure_transit_state(G)
    _process_transit_arrivals(G, current_time)
    _refresh_edge_runtime_densities(G, current_time)

    moves = get_step_moves(G, method, shortest_dists)
    _schedule_moves_as_transit(G, moves)

    G.graph["_sim_time"] = current_time + DELTA_T
    return moves



def collect_route_event_log(
    G_base,
    pop_dict,
    source_nodes,
    target_time,
    filename,
    baseline_method=PAPER_SINGLE_PATH_METHOD,
    compare_method=OUR_SINGLE_PATH_METHOD,
    verbose=False,
):
    """只记录“路由发生变化”的事件，不记录每一秒。"""
    G_baseline = copy.deepcopy(G_base)
    G_guided = copy.deepcopy(G_base)

    init_people(G_baseline, pop_dict, apply_noise=False)
    init_people(G_guided, pop_dict, apply_noise=False)

    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(G_base, weight="length"))
    prev_baseline = {src: None for src in source_nodes}
    prev_guided = {src: None for src in source_nodes}
    rows = []

    time = 0
    while time <= target_time:
        baseline_hot = rank_instantaneous_bottlenecks(G_baseline, top_k=1)
        guided_hot = rank_instantaneous_bottlenecks(G_guided, top_k=1)

        baseline_hot_node = baseline_hot[0]["node"] if baseline_hot else None
        baseline_hot_people = baseline_hot[0]["instant_people"] if baseline_hot else 0.0
        baseline_hot_density = baseline_hot[0]["instant_density"] if baseline_hot else 0.0

        guided_hot_node = guided_hot[0]["node"] if guided_hot else None
        guided_hot_people = guided_hot[0]["instant_people"] if guided_hot else 0.0
        guided_hot_density = guided_hot[0]["instant_density"] if guided_hot else 0.0

        for src in source_nodes:
            line = src.split("_")[1] if "_" in src else src

            baseline_path = get_best_path_to_exit(G_baseline, src, baseline_method, shortest_dists)
            guided_path = get_best_path_to_exit(G_guided, src, compare_method, shortest_dists)

            baseline_next = baseline_path[1] if baseline_path and len(baseline_path) > 1 else None
            guided_next = guided_path[1] if guided_path and len(guided_path) > 1 else None

            baseline_changed = baseline_next != prev_baseline[src]
            guided_changed = guided_next != prev_guided[src]
            route_diverged = baseline_next != guided_next

            if time == 0:
                event_type = "initial"
            else:
                flags = []
                if baseline_changed:
                    flags.append("baseline_change")
                if guided_changed:
                    flags.append("guided_change")
                if route_diverged:
                    flags.append("diverged")
                if not flags:
                    prev_baseline[src] = baseline_next
                    prev_guided[src] = guided_next
                    continue
                event_type = "+".join(flags)

            baseline_next_people = (
                G_baseline.nodes[baseline_next].get("people", 0.0) if baseline_next in G_baseline.nodes else 0.0
            )
            guided_next_people = G_guided.nodes[guided_next].get("people", 0.0) if guided_next in G_guided.nodes else 0.0

            if baseline_next in G_baseline.nodes:
                baseline_next_density, baseline_next_measure = _node_congestion_index(G_baseline, baseline_next)
            else:
                baseline_next_density, baseline_next_measure = 0.0, ""
            if guided_next in G_guided.nodes:
                guided_next_density, guided_next_measure = _node_congestion_index(G_guided, guided_next)
            else:
                guided_next_density, guided_next_measure = 0.0, ""

            baseline_len = _path_total_length(G_baseline, baseline_path) if baseline_path else None
            guided_len = _path_total_length(G_guided, guided_path) if guided_path else None

            reason = "same-route"
            if route_diverged and baseline_next and guided_next:
                if guided_next_density < baseline_next_density:
                    reason = "guided_detour_lower_density"
                elif guided_next_density < baseline_hot_density:
                    reason = "guided_avoids_baseline_bottleneck"
                else:
                    reason = "guided_reroute"
            elif baseline_changed and not guided_changed:
                reason = "baseline_changed_only"
            elif guided_changed and not baseline_changed:
                reason = "guided_changed_only"

            rows.append({
                "time": time,
                "line": line,
                "source": src,
                "event_type": event_type,
                "baseline_method": _method_display_name(baseline_method),
                "baseline_prev_next": prev_baseline[src],
                "baseline_curr_next": baseline_next,
                "guided_prev_next": prev_guided[src],
                "guided_curr_next": guided_next,
                "route_diverged": route_diverged,
                "baseline_path": format_path(baseline_path),
                "guided_method": _method_display_name(compare_method),
                "guided_path": format_path(guided_path),
                "first_divergence": first_divergence(baseline_path, guided_path),
                "baseline_path_length": baseline_len,
                "guided_path_length": guided_len,
                "baseline_next_people": baseline_next_people,
                "guided_next_people": guided_next_people,
                "baseline_next_density": baseline_next_density,
                "guided_next_density": guided_next_density,
                "baseline_next_congestion_measure": baseline_next_measure,
                "guided_next_congestion_measure": guided_next_measure,
                "baseline_bottleneck_node": baseline_hot_node,
                "baseline_bottleneck_people": baseline_hot_people,
                "baseline_bottleneck_density": baseline_hot_density,
                "guided_bottleneck_node": guided_hot_node,
                "guided_bottleneck_people": guided_hot_people,
                "guided_bottleneck_density": guided_hot_density,
                "reason": reason
            })

            if verbose and event_type != "initial":
                print(
                    f"[T={int(time)}s] {src} | Baseline={baseline_next or 'None'} | Guided={guided_next or 'None'} | "
                    f"分叉={route_diverged} | 基准瓶颈={baseline_hot_node or 'None'} | 引导瓶颈={guided_hot_node or 'None'}"
                )

            prev_baseline[src] = baseline_next
            prev_guided[src] = guided_next

        advance_simulation_step(G_baseline, baseline_method, shortest_dists)
        advance_simulation_step(G_guided, compare_method, shortest_dists)
        def still_has_people(G):
            return any(
                G.nodes[n].get("people", 0) > 0.1 and G.nodes[n].get("type") != "exit"
                for n in G.nodes()
            )

        if not still_has_people(G_baseline) and not still_has_people(G_guided):
            break

        time += DELTA_T

    route_log_df = pd.DataFrame(rows)
    route_log_df.to_csv(_output_path(filename), index=False, encoding="utf-8-sig")
    return route_log_df, G_baseline, G_guided, shortest_dists


    plt.figure(figsize=(16, 10))
    visible_nodes = [n for n, data in G_base.nodes(data=True) if not _is_hidden_visual_node(data)]
    H = G_base.subgraph(visible_nodes).copy()
    pos = nx.get_node_attributes(H, "pos")

    nx.draw_networkx_edges(H, pos, edge_color="#CFCFCF", width=1.0, alpha=0.35, arrows=True)
    nx.draw_networkx_nodes(H, pos, node_color="#E6E6E6", node_size=400, edgecolors="black", linewidths=0.6)

    if baseline_path and len(baseline_path) > 1:
        baseline_edges = [(u, v) for u, v in zip(baseline_path, baseline_path[1:]) if u in H.nodes and v in H.nodes]
        nx.draw_networkx_edges(H, pos, edgelist=baseline_edges, edge_color="red", width=3.0, style="dashed", arrows=True)

    if guided_path and len(guided_path) > 1:
        guided_edges = [(u, v) for u, v in zip(guided_path, guided_path[1:]) if u in H.nodes and v in H.nodes]
        nx.draw_networkx_edges(H, pos, edgelist=guided_edges, edge_color="blue", width=3.5, style="solid", arrows=True)

    labels = {}
    for n in H.nodes():
        if n == source or H.nodes[n].get("type") in {"exit", "gate"}:
            labels[n] = n.replace("Platform_", "").replace("Gate_", "").replace("Exit_", "")

    nx.draw_networkx_labels(H, pos, labels=labels, font_size=8, font_weight="bold")

    line_code = source.split("_")[1] if "_" in source else source
    title_bits = [f"路径对比 - {source}", f"线路 {line_code}"]
    if total_people is not None:
        title_bits.append(f"{total_people}人总规模")
    if obs_window is not None:
        title_bits.append(f"观测窗 0-{obs_window}s")

    plt.title(" | ".join(title_bits), fontsize=15, fontweight="bold")
    plt.legend(
        handles=[
            mpatches.Patch(color="red", label="Baseline: red dashed"),
            mpatches.Patch(color="blue", label="AdaptiveQueueAwareAStar: blue solid")
        ],
        loc="upper right"
    )
    plt.gca().set_aspect('equal', adjustable='datalim')
    plt.axis("off")
    plt.savefig(_output_path(filename), dpi=300, bbox_inches="tight")
    plt.close()


def execute_moves(G, moves, evacuated_by_line=None, exit_usage_dict=None):
    """把本步流量放入在途队列，真正的到达在后续按 travel_time 处理。"""
    _schedule_moves_as_transit(G, moves)
    return 0.0


def generate_snapshots_for_method(G_base, pop_dict, method, time_points):
    G = G_base.copy()
    init_people(G, pop_dict, apply_noise=False)
    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(G, weight="length"))

    time = 0
    max_time = max(time_points)
    snapshots = {}

    while time <= max_time:
        for tp in time_points:
            if abs(time - tp) < DELTA_T / 2:
                snapshots[tp] = {n: G.nodes[n].get("people", 0) for n in G.nodes()}

        advance_simulation_step(G, method, shortest_dists)
        time += DELTA_T

    return snapshots


def run_robustness_experiment(G_base, pop_dict, method=OUR_SINGLE_PATH_METHOD, runs=10, seed=42):
    active_lines = get_real_active_lines(G_base)
    if isinstance(pop_dict, dict):
        total_people = sum(sum(line_data.values()) for line_data in pop_dict.values())
    else:
        total_people = pop_dict * active_lines
    print(f"\n🔬 启动 {method} 算法鲁棒性测试 (全站总计:{total_people}人, 迭代:{runs}次)...")

    results_time, results_queue, results_exposure, results_speed = [], [], [], []

    for i in range(runs):
        metrics = run_simulation_for_metrics(
            G_base,
            pop_dict,
            method=method,
            apply_noise=True,
            rng=random.Random(None if seed is None else seed + i),
        )


        results_time.append(metrics["time"])
        results_queue.append(metrics["queueing_time"])
        results_exposure.append(metrics["high_density_exposure_person_seconds"] / 1000)
        results_speed.append(metrics["avg_speed"])

    mean_t, std_t = statistics.mean(results_time), statistics.stdev(results_time) if runs > 1 else 0.0
    mean_q, std_q = statistics.mean(results_queue), statistics.stdev(results_queue) if runs > 1 else 0.0
    mean_e, std_e = statistics.mean(results_exposure), statistics.stdev(results_exposure) if runs > 1 else 0.0
    mean_s, std_s = statistics.mean(results_speed), statistics.stdev(results_speed) if runs > 1 else 0.0

    return mean_t, std_t, mean_q, std_q, mean_e, std_e, mean_s, std_s


# ==============================================================================
# 5. 绘图与主流程
# ==============================================================================
def plot_initial_topology(G):
    # 只调整视觉呈现，不修改任何节点坐标。
    fig, ax = plt.subplots(figsize=(30, 42))
    visible_nodes = [
        n for n, data in G.nodes(data=True)
        if not _is_hidden_visual_node(data)
    ]
    H = G.subgraph(visible_nodes).copy()
    pos = nx.get_node_attributes(H, 'pos')
    display_pos = {n: (float(p[0]), float(p[1])) for n, p in pos.items()}

    # 真实坐标下很多设施点间距极小，论文图会糊成一团。
    # 这里仅生成绘图用坐标副本，把近距离节点轻微错开；G.nodes[n]["pos"] 不会被修改。
    min_gap = 260.0
    anchor_strength = 0.08
    nodes_for_layout = list(display_pos.keys())
    original_pos = {n: display_pos[n] for n in nodes_for_layout}
    for _ in range(40):
        shifts = {n: [0.0, 0.0] for n in nodes_for_layout}
        for i, u in enumerate(nodes_for_layout):
            x1, y1 = display_pos[u]
            for v in nodes_for_layout[i + 1:]:
                x2, y2 = display_pos[v]
                dx, dy = x2 - x1, y2 - y1
                dist = math.hypot(dx, dy)
                if dist >= min_gap:
                    continue
                if dist < 1e-6:
                    dx = ((i % 7) - 3) or 1
                    dy = (((i // 7) % 7) - 3) or 1
                    dist = math.hypot(dx, dy)
                push = (min_gap - dist) * 0.5
                ux, uy = dx / dist, dy / dist
                shifts[u][0] -= ux * push
                shifts[u][1] -= uy * push
                shifts[v][0] += ux * push
                shifts[v][1] += uy * push

        for n in nodes_for_layout:
            x, y = display_pos[n]
            ox, oy = original_pos[n]
            display_pos[n] = (
                x + shifts[n][0] + anchor_strength * (ox - x),
                y + shifts[n][1] + anchor_strength * (oy - y),
            )

    color_map = []
    node_sizes = []
    for n in H.nodes():
        t = H.nodes[n].get('type', '')
        if 'platform' in t:
            color_map.append('#E53935')
            node_sizes.append(520)
        elif 'exit' in t:
            color_map.append('#34C759')
            node_sizes.append(430)
        elif 'gate' in t:
            color_map.append('#FFC107')
            node_sizes.append(250)
        elif 'stair' in t or 'escalator' in t:
            color_map.append('#1E88E5')
            node_sizes.append(220)
        elif 'virtual' in t:
            color_map.append('#8E63CE')
            node_sizes.append(210)
        else:
            color_map.append('#8E63CE')
            node_sizes.append(170)

    for n, (ox, oy) in original_pos.items():
        x, y = display_pos[n]
        if math.hypot(x - ox, y - oy) > 60:
            ax.plot([ox, x], [oy, y], color='#D0D0D0', linewidth=0.45, alpha=0.35, zorder=0)

    nx.draw_networkx_edges(
        H,
        display_pos,
        ax=ax,
        edge_color='#9A9A9A',
        arrows=True,
        width=0.7,
        arrowsize=5,
        alpha=0.18,
        connectionstyle='arc3,rad=0.08',
        min_source_margin=2,
        min_target_margin=2,
    )
    nx.draw_networkx_nodes(
        H,
        display_pos,
        ax=ax,
        node_color=color_map,
        node_size=node_sizes,
        edgecolors='black',
        linewidths=0.75,
        alpha=0.96,
    )

    labels = {
        n: n.split('_')[-1]
        for n in H.nodes()
        if H.nodes[n].get('type') in ['platform', 'exit']
    }
    nx.draw_networkx_labels(
        G,
        display_pos,
        labels=labels,
        ax=ax,
        font_size=7,
        font_weight='bold',
        bbox=dict(boxstyle='round,pad=0.10', facecolor='white', edgecolor='none', alpha=0.78),
    )

    legend_handles = [
        plt.Line2D([0], [0], marker='o', color='w', label='站台', markerfacecolor='#E53935', markeredgecolor='black', markersize=11),
        plt.Line2D([0], [0], marker='o', color='w', label='楼梯/扶梯', markerfacecolor='#1E88E5', markeredgecolor='black', markersize=9),
        plt.Line2D([0], [0], marker='o', color='w', label='闸机', markerfacecolor='#FFC107', markeredgecolor='black', markersize=9),
        plt.Line2D([0], [0], marker='o', color='w', label='通道/虚拟节点', markerfacecolor='#8E63CE', markeredgecolor='black', markersize=9),
        plt.Line2D([0], [0], marker='o', color='w', label='出口', markerfacecolor='#34C759', markeredgecolor='black', markersize=10),
    ]
    ax.legend(handles=legend_handles, loc='upper left', frameon=True, framealpha=0.9, fontsize=12)

    ax.set_title('龙阳路枢纽初始物理拓扑（视觉展开版，原始坐标未修改）', fontsize=24, fontweight='bold', pad=18)
    ax.set_aspect('equal', adjustable='datalim')
    ax.margins(x=0.08, y=0.08)
    ax.axis('off')

    fig.savefig(_output_path("01_initial_topology.png"), dpi=400, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def plot_charts(method_metrics, total_p):
    """【专业高颜值版】核心指标对比"""
    labels = [label for label, _ in method_metrics]
    metrics_map = dict(method_metrics)
    colors = ['#E63946', '#F4A261', '#457B9D', '#59A14F']

    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    fig.suptitle(f'枢纽疏散指标评估 (测试客流: {total_p}人)', fontsize=20, fontweight='bold', y=0.96)

    metrics_list = [
        ('time', '疏散完成时间 ', axes[0, 0], 1),
        ('queueing_time', '总滞留排队时间 ', axes[0, 1], 1),
        ('effective_evacuation_speed', '含等待有效疏散速度', axes[1, 0], 1),
        ('moving_average_speed', '移动中平均速度', axes[1, 1], 1)
    ]

    for key, title, ax, div in metrics_list:
        vals = [metrics_map[label][key] / div for label in labels]
        bars = ax.bar(labels, vals, color=colors[:len(labels)], width=0.55, edgecolor='black', linewidth=1.2)
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.grid(axis='y', linestyle='--', alpha=0.6)
        ax.set_axisbelow(True)

        for bar in bars:
            yval = bar.get_height()
            label_text = f'{yval:.3f}' if 'speed' in key else f'{int(yval)}'
            ax.text(bar.get_x() + bar.get_width() / 2, yval + max(abs(yval) * 0.01, 0.5), label_text, ha='center', va='bottom',
                    fontsize=11, fontweight='bold')

    plt.savefig(_output_path("02_System_Macro_Metrics_Comparison.png"), dpi=300, bbox_inches="tight")
    plt.close()

    if len(labels) >= 2:
        baseline_label = labels[0]
        baseline = metrics_map[baseline_label]
        comparison_labels = [label for label in labels if label != baseline_label]
        metric_keys = [
            ("time", "时间改善率"),
            ("queueing_time", "排队改善率"),
            ("effective_evacuation_speed", "有效疏散速度改善率"),
        ]
        x = np.arange(len(metric_keys))
        width = min(0.8 / max(len(comparison_labels), 1), 0.28)

        plt.figure(figsize=(10, 6))
        for idx, label in enumerate(comparison_labels):
            vals = []
            for key, _ in metric_keys:
                base_val = baseline[key]
                cur_val = metrics_map[label][key]
                if key == "effective_evacuation_speed":
                    improve = ((cur_val - base_val) / base_val * 100) if base_val > 0 else 0.0
                else:
                    improve = ((base_val - cur_val) / base_val * 100) if base_val > 0 else 0.0
                vals.append(improve)
            offset = (idx - (len(comparison_labels) - 1) / 2.0) * width
            bars = plt.bar(x + offset, vals, width=width, color=colors[(idx + 1) % len(colors)], edgecolor='black', label=label)
            for bar in bars:
                yval = bar.get_height()
                plt.text(bar.get_x() + bar.get_width() / 2, yval + 1, f"{yval:.1f}%", ha='center', fontweight='bold',
                         fontsize=10, color='black')
        plt.xticks(x, [title for _, title in metric_keys])
        plt.ylabel("改善提升幅度 (%)", fontsize=12)
        plt.title(f"相对 {baseline_label} 的提升率 ({total_p}人)", fontweight="bold", fontsize=16)
        plt.legend()
        plt.grid(axis='y', linestyle='--', alpha=0.6)
        plt.gca().set_axisbelow(True)
        plt.savefig(_output_path("03_System_Improvement_Rates.png"), dpi=300, bbox_inches="tight")
        plt.close()


def plot_line_specific_analysis(metrics_baseline, metrics_guided, pop_dict):
    """绘制各线路清空时间和累计排队时间。"""
    lines = [l for l, d in pop_dict.items() if sum(d.values()) > 0]

    # 画 1行2列 的图，左边时间，右边拥挤暴露
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle('各线路疏散指标评估', fontsize=18, fontweight='bold', y=1.02)

    x = np.arange(len(lines))
    width = 0.35
    colors = ['#E63946', '#457B9D']

    # === 子图 1：各线路疏散完成时间 ===
    ax1 = axes[0]
    t_baseline = [
        metrics_baseline["clearance_times_by_line"].get(l)
        if metrics_baseline["clearance_times_by_line"].get(l) is not None
        else np.nan
        for l in lines
    ]
    t_guided = [
        metrics_guided["clearance_times_by_line"].get(l)
        if metrics_guided["clearance_times_by_line"].get(l) is not None
        else np.nan
        for l in lines
    ]

    bars1_baseline = ax1.bar(x - width / 2, t_baseline, width, label='ImprovedAStar', color=colors[0], edgecolor='black',
                             linewidth=1)
    bars1_guided = ax1.bar(x + width / 2, t_guided, width, label='AdaptiveQueueAwareAStar', color=colors[1], edgecolor='black',
                         linewidth=1)

    ax1.set_xticks(x);
    ax1.set_xticklabels(lines, fontsize=12)
    ax1.set_ylabel('疏散完成时间 / Evacuation Time (s)', fontsize=12)
    ax1.set_title('各单线路疏散完成时间对比', fontweight='bold', fontsize=14)
    ax1.legend();
    ax1.grid(axis='y', linestyle='--', alpha=0.6);
    ax1.set_axisbelow(True)

    for bars in [bars1_baseline, bars1_guided]:
        for bar in bars:
            yval = bar.get_height()
            if not np.isfinite(yval):
                continue
            ax1.text(bar.get_x() + bar.get_width() / 2, yval + 2, f'{int(yval)}', ha='center', va='bottom', fontsize=11,
                     fontweight='bold')

    # === 子图 2：各线路累计排队时间 ===
    ax2 = axes[1]
    e_baseline = [metrics_baseline["queueing_time_by_line"].get(l, 0) / 1000.0 for l in lines]
    e_guided = [metrics_guided["queueing_time_by_line"].get(l, 0) / 1000.0 for l in lines]

    bars2_baseline = ax2.bar(x - width / 2, e_baseline, width, label='ImprovedAStar', color=colors[0], edgecolor='black',
                             linewidth=1)
    bars2_guided = ax2.bar(x + width / 2, e_guided, width, label='AdaptiveQueueAwareAStar', color=colors[1], edgecolor='black',
                         linewidth=1)

    ax2.set_xticks(x);
    ax2.set_xticklabels(lines, fontsize=12)
    ax2.set_ylabel('累计排队时间 / Queueing (10$^3$ person·s)', fontsize=12)
    ax2.set_title('各线路累计排队时间对比', fontweight='bold', fontsize=14)
    ax2.legend();
    ax2.grid(axis='y', linestyle='--', alpha=0.6);
    ax2.set_axisbelow(True)

    for bars in [bars2_baseline, bars2_guided]:
        for bar in bars:
            yval = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2, yval + (max(e_baseline) * 0.02), f'{yval:.1f}', ha='center',
                     va='bottom', fontsize=11, fontweight='bold')

    plt.savefig(_output_path("05_System_Line_Core_Metrics.png"), dpi=300, bbox_inches='tight')
    plt.close()

    # ==== 保留：各线路逃生出口去向 (堆叠柱状图) ====
    exit_plot_methods = [("ImprovedAStar", metrics_baseline), ("AdaptiveQueueAwareAStar", metrics_guided)]
    shared_active_exits = sorted({
        ext
        for _, met in exit_plot_methods
        for ext, lines_ppl in met["exit_usage_by_line"].items()
        if sum(lines_ppl.values()) > 1.0
    })
    shared_exit_ymax = 0.0
    for _, met in exit_plot_methods:
        exits_dict = met["exit_usage_by_line"]
        for ext in shared_active_exits:
            shared_exit_ymax = max(shared_exit_ymax, sum(exits_dict.get(ext, {}).get(line, 0.0) for line in lines))

    if shared_active_exits:
        shared_exit_ymax = max(shared_exit_ymax * 1.08, 1.0)

    for title, met in exit_plot_methods:
        exits_dict = met["exit_usage_by_line"]
        active_exits = shared_active_exits
        if not active_exits:
            continue

        fig, ax = plt.subplots(figsize=(14, 6))
        bottoms = np.zeros(len(active_exits))
        c_map = plt.cm.Set3(np.linspace(0, 1, len(lines)))
        x_positions = np.arange(len(active_exits))

        for i, line in enumerate(lines):
            counts = [exits_dict[ext].get(line, 0.0) for ext in active_exits]
            ax.bar(x_positions, counts, label=line, bottom=bottoms, color=c_map[i], edgecolor='black', linewidth=0.5)
            bottoms += counts

        ax.set_xticks(x_positions);
        ax.set_xticklabels([e.replace("Exit_", "") for e in active_exits], rotation=45, ha='right')
        ax.set_ylabel('逃生人数 (人)');
        ax.set_ylim(0, shared_exit_ymax)
        ax.set_title(f'人群逃生出口分布溯源 ({_method_display_name(title)})', fontweight='bold', fontsize=14)
        ax.legend(title="人群来源");
        ax.grid(axis='y', linestyle='--', alpha=0.5);
        ax.set_axisbelow(True)
        plt.savefig(_output_path(f"06_Exit_Destinations_{_method_output_tag(title)}.png"), dpi=300, bbox_inches='tight')
        plt.close()


def plot_charts_multi(G_base, method_metrics, total_p):
    labels = [label for label, _ in method_metrics]
    metrics_map = dict(method_metrics)
    colors = ['#E63946', '#F4A261', '#457B9D', '#59A14F']
    baseline_label = labels[0] if labels else "Baseline"
    key_nodes = _select_key_facility_nodes(G_base, method_metrics, top_k=8)
    key_node_rows = []
    for label, metrics in method_metrics:
        sim_time = max(float(metrics.get("time", 0.0)), DELTA_T)
        node_stats = metrics.get("node_stats", {})
        occupancy_vals = []
        for node in key_nodes:
            stat = node_stats.get(node, {})
            avg_occupancy = float(stat.get("congestion_index_seconds", stat.get("density_seconds", 0.0))) / sim_time
            occupancy_vals.append(avg_occupancy)
            key_node_rows.append({
                "method": label,
                "node": node,
                "avg_occupancy": avg_occupancy,
                "peak_density": float(stat.get("peak_density", 0.0)),
                "peak_load_ratio": float(stat.get("peak_load_ratio", 0.0)),
                "peak_congestion_index": float(stat.get("peak_congestion_index", stat.get("peak_density", 0.0))),
                "congestion_measure_type": stat.get("congestion_measure_type", ""),
                "queue_seconds": float(stat.get("queue_seconds", 0.0)),
            })
        metrics["key_node_avg_occupancy"] = sum(occupancy_vals) / len(occupancy_vals) if occupancy_vals else 0.0

    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    fig.suptitle(f'枢纽疏散安全性评估 (测试客流: {total_p}人)', fontsize=20, fontweight='bold', y=0.96)
    metrics_list = [
        ('queueing_time', '总滞留排队时间 (人·秒)', axes[0, 0], 1),
        ('effective_evacuation_speed', '含等待有效疏散速度', axes[0, 1], 1),
        ('time', '疏散完成时间 (s)', axes[1, 0], 1),
        ('exit_load_jain_index', '出口负荷 Jain 指数', axes[1, 1], 1)
    ]

    for key, title, ax, div in metrics_list:
        vals = [metrics_map[label][key] / div for label in labels]
        bars = ax.bar(labels, vals, color=colors[:len(labels)], width=0.55, edgecolor='black', linewidth=1.2)
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.grid(axis='y', linestyle='--', alpha=0.6)
        ax.set_axisbelow(True)
        ymax = max(vals) if vals else 0.0
        if key in {'exit_load_jain_index', 'effective_evacuation_speed'}:
            offset = max(ymax * 0.04, 0.015)
            ax.set_ylim(0, max(ymax * 1.18, ymax + 0.08, 0.1))
        elif div == 1000:
            offset = max(ymax * 0.03, 0.12)
            ax.set_ylim(0, max(ymax * 1.14, 1.0))
        else:
            offset = max(ymax * 0.015, 0.5)
            ax.set_ylim(0, max(ymax * 1.10, 1.0))
        for bar in bars:
            yval = bar.get_height()
            label_text = f'{yval:.3f}' if key in {'exit_load_jain_index', 'effective_evacuation_speed'} else f'{int(yval)}'
            ax.text(bar.get_x() + bar.get_width() / 2, yval + offset, label_text,
                    ha='center', va='bottom', fontsize=11, fontweight='bold')

    plt.savefig(_output_path("02_System_Macro_Metrics_Comparison.png"), dpi=300, bbox_inches="tight")
    plt.close()
    if key_node_rows:
        pd.DataFrame(key_node_rows).to_csv(_output_path("02c_system_key_node_occupancy.csv"), index=False, encoding="utf-8-sig")

    plt.figure(figsize=(8.5, 6))
    speed_vals = [metrics_map[label]["moving_average_speed"] for label in labels]
    bars = plt.bar(labels, speed_vals, color=colors[:len(labels)], edgecolor='black', linewidth=1.2, width=0.55)
    ymax = max(speed_vals) if speed_vals else 0.0
    offset = max(ymax * 0.03, 0.12)
    plt.ylim(0, max(ymax * 1.14, 1.0))
    plt.ylabel("移动中平均速度 (m/s)", fontsize=12)
    plt.title("系统移动状态速度对比", fontweight="bold", fontsize=16)
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.gca().set_axisbelow(True)
    for bar in bars:
        yval = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            yval + offset,
            f"{yval:.2f}",
            ha='center',
            va='bottom',
            fontsize=11,
            fontweight='bold'
        )
    plt.savefig(_output_path("02d_System_Moving_Speed_Comparison.png"), dpi=300, bbox_inches="tight")
    plt.close()

    baseline = metrics_map[baseline_label]
    comparison_labels = [label for label in labels if label != baseline_label]
    metric_keys = [
        ("queueing_time", "排队改善率"),
        ("time", "时间改善率"),
        ("effective_evacuation_speed", "有效疏散速度改善率"),
    ]
    x = np.arange(len(metric_keys))
    width = min(0.8 / max(len(comparison_labels), 1), 0.28)

    plt.figure(figsize=(10, 6))
    for idx, label in enumerate(comparison_labels):
        vals = []
        for key, _ in metric_keys:
            base_val = baseline[key]
            cur_val = metrics_map[label][key]
            if key == "effective_evacuation_speed":
                improve = ((cur_val - base_val) / base_val * 100) if base_val > 0 else 0.0
            else:
                improve = ((base_val - cur_val) / base_val * 100) if base_val > 0 else 0.0
            vals.append(improve)
        offset = (idx - (len(comparison_labels) - 1) / 2.0) * width
        bars = plt.bar(x + offset, vals, width=width, color=colors[idx + 1], edgecolor='black', label=label)
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width() / 2, yval + 1, f"{yval:.1f}%", ha='center',
                     fontweight='bold', fontsize=10, color='black')
    plt.xticks(x, [title for _, title in metric_keys])
    plt.ylabel("改善提升幅度 (%)", fontsize=12)
    plt.title(f"相对 {baseline_label} 的安全性优先改善率 ({total_p}人)", fontweight="bold", fontsize=16)
    plt.legend()
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.gca().set_axisbelow(True)
    plt.savefig(_output_path("03_System_Improvement_Rates.png"), dpi=300, bbox_inches="tight")
    plt.close()

    if all("wall_clock_runtime_s" in metrics_map[label] for label in labels):
        plt.figure(figsize=(8.5, 6))
        runtime_vals = [metrics_map[label]["wall_clock_runtime_s"] for label in labels]
        bars = plt.bar(labels, runtime_vals, color=colors[:len(labels)], edgecolor='black', linewidth=1.2, width=0.55)
        plt.ylabel("实际运行时间 (s)", fontsize=12)
        plt.title("系统层三算法实际运行时间对比", fontweight="bold", fontsize=16)
        plt.grid(axis='y', linestyle='--', alpha=0.6)
        plt.gca().set_axisbelow(True)
        for bar in bars:
            yval = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                yval + max(yval * 0.02, 0.02),
                f"{yval:.2f}",
                ha='center',
                va='bottom',
                fontsize=11,
                fontweight='bold'
            )
        plt.savefig(_output_path("02b_System_Runtime_Comparison.png"), dpi=300, bbox_inches="tight")
        plt.close()


def plot_system_evacuation_curve(method_metrics, total_p, filename="01_system_evacuation_curve.png", csv_filename="01_system_evacuation_curve.csv"):
    colors = ['#E63946', '#F4A261', '#457B9D', '#59A14F']
    plt.figure(figsize=(10.5, 6.5))
    csv_rows = []

    for idx, (label, metrics) in enumerate(method_metrics):
        curve = metrics.get("evacuation_curve", {})
        times = curve.get("times", [])
        remaining = curve.get("remaining", [])
        if not times or not remaining:
            continue
        plt.plot(times, remaining, linewidth=2.8, color=colors[idx % len(colors)], label=label)
        for t, r in zip(times, remaining):
            csv_rows.append({
                "method": label,
                "time_s": float(t),
                "remaining_people": float(r),
            })

    plt.title(f"整体疏散完成曲线（站内剩余人数随时间变化，{total_p}人）", fontsize=18, fontweight='bold')
    plt.xlabel("时间 (s)", fontsize=13)
    plt.ylabel("站内剩余人数 (人)", fontsize=13)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend()
    plt.gca().set_axisbelow(True)
    plt.savefig(_output_path(filename), dpi=300, bbox_inches="tight")
    plt.close()

    if csv_rows:
        pd.DataFrame(csv_rows).to_csv(_output_path(csv_filename), index=False, encoding="utf-8-sig")


def plot_line_specific_analysis_multi(method_metrics, pop_dict):
    lines = [l for l, d in pop_dict.items() if sum(d.values()) > 0]
    labels = [label for label, _ in method_metrics]
    metrics_map = dict(method_metrics)
    colors = ['#E63946', '#F4A261', '#457B9D', '#59A14F']

    fig, axes = plt.subplots(1, 2, figsize=(17, 6))
    fig.suptitle('各线路疏散指标评估', fontsize=18, fontweight='bold', y=1.02)

    x = np.arange(len(lines))
    width = min(0.8 / max(len(labels), 1), 0.25)

    ax1 = axes[0]
    time_groups = []
    for idx, label in enumerate(labels):
        vals = [
            metrics_map[label]["clearance_times_by_line"].get(l)
            if metrics_map[label]["clearance_times_by_line"].get(l) is not None
            else np.nan
            for l in lines
        ]
        offset = (idx - (len(labels) - 1) / 2.0) * width
        bars = ax1.bar(x + offset, vals, width, label=label, color=colors[idx], edgecolor='black', linewidth=1)
        time_groups.append(bars)

    ax1.set_xticks(x)
    ax1.set_xticklabels(lines, fontsize=12)
    ax1.set_ylabel('疏散完成时间 / Evacuation Time (s)', fontsize=12)
    ax1.set_title('各单线路疏散完成时间对比', fontweight='bold', fontsize=14)
    ax1.legend()
    ax1.grid(axis='y', linestyle='--', alpha=0.6)
    ax1.set_axisbelow(True)
    for bars in time_groups:
        for bar in bars:
            yval = bar.get_height()
            if not np.isfinite(yval):
                continue
            ax1.text(bar.get_x() + bar.get_width() / 2, yval + 2, f'{int(yval)}', ha='center', va='bottom', fontsize=10,
                     fontweight='bold')

    ax2 = axes[1]
    queueing_groups = []
    queueing_max = 0.0
    for idx, label in enumerate(labels):
        vals = [metrics_map[label]["queueing_time_by_line"].get(l, 0) / 1000.0 for l in lines]
        queueing_max = max(queueing_max, max(vals) if vals else 0.0)
        offset = (idx - (len(labels) - 1) / 2.0) * width
        bars = ax2.bar(x + offset, vals, width, label=label, color=colors[idx], edgecolor='black', linewidth=1)
        queueing_groups.append(bars)

    ax2.set_xticks(x)
    ax2.set_xticklabels(lines, fontsize=12)
    ax2.set_ylabel('累计排队时间 / Queueing (10$^3$ person·s)', fontsize=12)
    ax2.set_title('各线路累计排队时间对比', fontweight='bold', fontsize=14)
    ax2.legend()
    ax2.grid(axis='y', linestyle='--', alpha=0.6)
    ax2.set_axisbelow(True)
    for bars in queueing_groups:
        for bar in bars:
            yval = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2, yval + max(queueing_max, 1.0) * 0.02, f'{yval:.1f}', ha='center',
                     va='bottom', fontsize=10, fontweight='bold')

    plt.savefig(_output_path("05_System_Line_Core_Metrics.png"), dpi=300, bbox_inches='tight')
    plt.close()

    shared_active_exits = sorted({
        ext
        for _, met in method_metrics
        for ext, lines_ppl in met["exit_usage_by_line"].items()
        if sum(lines_ppl.values()) > 1.0
    })
    shared_exit_ymax = 0.0
    for _, met in method_metrics:
        exits_dict = met["exit_usage_by_line"]
        for ext in shared_active_exits:
            shared_exit_ymax = max(shared_exit_ymax, sum(exits_dict.get(ext, {}).get(line, 0.0) for line in lines))

    if shared_active_exits:
        shared_exit_ymax = max(shared_exit_ymax * 1.08, 1.0)

    for title, met in method_metrics:
        exits_dict = met["exit_usage_by_line"]
        active_exits = shared_active_exits
        if not active_exits:
            continue

        fig, ax = plt.subplots(figsize=(14, 6))
        bottoms = np.zeros(len(active_exits))
        c_map = plt.cm.Set3(np.linspace(0, 1, len(lines)))
        x_positions = np.arange(len(active_exits))

        for i, line in enumerate(lines):
            counts = [exits_dict[ext].get(line, 0.0) for ext in active_exits]
            ax.bar(x_positions, counts, label=line, bottom=bottoms, color=c_map[i], edgecolor='black', linewidth=0.5)
            bottoms += counts

        ax.set_xticks(x_positions)
        ax.set_xticklabels([e.replace("Exit_", "") for e in active_exits], rotation=45, ha='right')
        ax.set_ylabel('逃生人数 (人)')
        ax.set_ylim(0, shared_exit_ymax)
        ax.set_title(f'人群逃生出口分布溯源 ({_method_display_name(title)})', fontweight='bold', fontsize=14)
        ax.legend(title="人群来源")
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        ax.set_axisbelow(True)
        plt.savefig(_output_path(f"06_Exit_Destinations_{_method_output_tag(title)}.png"), dpi=300, bbox_inches='tight')
        plt.close()

def _infer_target_by_line_from_graph_state(G):
    totals = {line: 0.0 for line in ALL_LINE_IDS}
    for _, data in G.nodes(data=True):
        people_dict = data.get("people_dict", {})
        for line in ALL_LINE_IDS:
            totals[line] += float(people_dict.get(line, 0.0))
    return {line: total for line, total in totals.items() if total > 0.0}


def _run_simulation_for_metrics_core(
    G,
    method,
    target_by_line,
    stop_at_time=6000.0,
    collect_detailed_series=COLLECT_DETAILED_SERIES_DEFAULT,
    metric_sample_interval_seconds=METRIC_SAMPLE_INTERVAL_SECONDS,
):
    G.graph["_active_simulation_method"] = _normalize_method(method)
    fast_exact_override = G.graph.get("_fast_exact_aa_override")
    G.graph["_fast_exact_aa"] = bool(
        FAST_EXACT_AA
        if fast_exact_override is None
        else fast_exact_override
    )
    if PROFILE_AA:
        _install_predicted_queue_performance_counter()
    else:
        _remove_predicted_queue_performance_counter()
    run_wall_start = perf_counter()
    run_log_path = G.graph.get("_run_log_path")

    def emit_progress(message):
        print(message, flush=True)
        if run_log_path:
            with open(run_log_path, "a", encoding="utf-8") as log_handle:
                log_handle.write(message + "\n")
    if hasattr(spr, "bind_physical_callbacks"):
        spr.bind_physical_callbacks(
            edge_travel_time_fn=physical_edge_travel_time,
            edge_flow_capacity_fn=_edge_effective_flow_capacity,
            edge_resource_id_fn=edge_resource_id,
            resource_capacity_fn=resource_capacity_per_second,
            predicted_spatial_wait_fn=predicted_spatial_receiving_wait,
            predicted_spatial_density_fn=predicted_spatial_density,
            gate_service_backlog_fn=gate_service_backlog_state,
        )

    time, evacuated_count = 0.0, 0.0
    total_flow_moves, sum_speed_weighted = 0.0, 0.0
    travel_person_seconds = 0.0
    total_movement_distance = 0.0
    moving_person_seconds = 0.0
    zero_or_topological_move_count = 0.0
    edge_flow_totals = {}
    edge_flow_by_source_group = {}
    node_throughput_by_sg = {}
    shortest_dists = _shortest_distances_to_exits(G)
    source_group_targets = _source_group_totals_from_graph(G)
    core_target_by_line = {line: 0.0 for line in ALL_LINE_IDS}
    transfer_target_by_line = {line: 0.0 for line in ALL_LINE_IDS}
    for source_group_id, amount in source_group_targets.items():
        line_id, source_type, _ = _parse_source_group_id(source_group_id)
        if line_id not in core_target_by_line:
            continue
        if source_type == "transfer_people":
            transfer_target_by_line[line_id] += float(amount)
        else:
            core_target_by_line[line_id] += float(amount)

    evacuated_by_line = {line: 0.0 for line in ALL_LINE_IDS}
    evacuated_by_source_group = {source_group_id: 0.0 for source_group_id in source_group_targets}
    monitored_queue_nodes = [n for n in G.nodes() if _is_queue_node(G, n)]
    monitored_edges = [
        _edge_key(u, v)
        for u, v, data in G.edges(data=True)
        if _is_monitored_edge(data)
    ]
    G.graph["_receiving_block_diagnostics"] = {
        "edge_receiving_hard_limit": {},
        "destination_capacity_or_spillback": {},
    }
    edge_state_diagnostics = {}
    for u, v, data in G.edges(data=True):
        edge_key = _edge_key(u, v)
        edge_type = str(data.get("edge_type", "")).lower()
        length = max(float(data.get("length", 0.0)), 0.0)
        area_source = data.get("area_source")
        if not area_source:
            area_source = (
                "explicit_edge_area"
                if float(data.get("edge_area", 0.0) or 0.0) > 0.0
                else "derived_length_width:"
                + str(data.get("distance_source", "configured_length"))
            )
        edge_state_diagnostics[edge_key] = {
            "edge": edge_key,
            "source_node": u,
            "destination_node": v,
            "edge_type": edge_type,
            "length_m": length,
            "effective_area_m2": float(_edge_effective_area(G, u, v)),
            "area_source": str(area_source),
            "density_exempt": edge_type in EDGE_DENSITY_EXEMPT_TYPES,
            "is_physical_edge": (
                length > 0.0 and edge_type not in EDGE_DENSITY_EXEMPT_TYPES
            ),
            "maximum_density_p_per_m2": 0.0,
            "minimum_speed_m_per_s": None,
            "maximum_in_transit_people": 0.0,
            "cumulative_in_transit_person_seconds": 0.0,
            "speed_below_0_3_person_seconds": 0.0,
            "speed_below_0_1_person_seconds": 0.0,
            "speed_below_0_05_person_seconds": 0.0,
            "density_2_0_to_3_0_person_seconds": 0.0,
            "density_3_0_to_3_5_person_seconds": 0.0,
            "density_3_5_to_4_0_person_seconds": 0.0,
            "last_occupied_time_seconds": None,
            "last_observed_in_transit_people": 0.0,
        }

    monitor_node = "Gate_L2_N_West" if "Gate_L2_N_West" in G.nodes else next(
        (n for n in G.nodes if "gate" in n.lower()), None
    )

    metrics = {
        "time": 0,
        "queueing_time": 0.0,
        "resource_queueing_time": 0.0,
        "resource_queue_person_seconds": 0.0,
        "unassigned_wait_person_seconds": 0.0,
        # Diagnostic-only component already represented within total
        # waiting/queueing accounting; not an independent formal performance metric.
        "spatial_blocked_person_seconds": 0.0,
        # Backward-compatible internal alias; never written to formal outputs.
        "spatial_blocked_exposure_person_seconds": 0.0,
        "stationary_person_seconds": 0.0,
        "in_transit_person_seconds": 0.0,
        "total_system_person_seconds": 0.0,
        "resource_stats": {},
        "high_density_exposure_person_seconds": 0.0,
        "edge_high_density_exposure_person_seconds": 0.0,
        "node_high_density_exposure_person_seconds": 0.0,
        "initial_high_density_exposure_person_seconds": 0.0,
        "high_density_diagnostics": {},
        "high_density_diagnostic_sum_person_seconds": 0.0,
        "high_density_diagnostic_sum_error": 0.0,
        "edge_state_diagnostics": edge_state_diagnostics,
        "edge_low_speed_person_seconds_by_line": {
            line: {
                "cumulative_in_transit_person_seconds": 0.0,
                "speed_below_0_3_person_seconds": 0.0,
                "speed_below_0_1_person_seconds": 0.0,
                "speed_below_0_05_person_seconds": 0.0,
            }
            for line in ALL_LINE_IDS
        },
        "receiving_block_diagnostics": [],
        "receiving_block_summary": {},
        "edge_lowest_speed_top20": [],
        "edge_low_speed_person_seconds_top20": [],
        "final_in_transit_edges": [],
        "last_in_transit_snapshot_time_seconds": None,
        "avg_speed": 0.0,
        "moving_average_speed": 0.0,
        "edge_traversal_average_speed": 0.0,
        "effective_evacuation_speed": 0.0,
        "avg_travel_time": 0.0,
        "peak_density": 0.0,
        "peak_overflow_queue": 0.0,
        "peak_congestion_index": 0.0,
        "occupancy_partition_max_error": 0.0,
        "configuration_density_diagnostics": {
            "jam_density_p_per_m2": float(HIGH_LOAD_JAM_DENSITY_P_PER_M2),
            "high_density_threshold_p_per_m2": float(
                HIGH_LOAD_JAM_DENSITY_P_PER_M2
            ),
            "edge_receiving_density_parameter_name": (
                EDGE_RECEIVING_DENSITY_PARAMETER_NAME
            ),
            "edge_receiving_density_limit_p_per_m2": (
                edge_receiving_density_limit(G)
            ),
            "edge_receiving_density_formula": (
                EDGE_RECEIVING_DENSITY_FORMULA
            ),
            "edge_receiving_density_source": (
                EDGE_RECEIVING_DENSITY_SOURCE
            ),
            "edge_receiving_hard_limit_enabled": (
                edge_receiving_hard_limit_enabled(G)
            ),
            "default_area_node_count": sum(
                1
                for _, data in G.nodes(data=True)
                if str(data.get("area_source", "")) == "default_gate_rule"
            ),
            "default_area_spatial_node_count": sum(
                1
                for node, data in G.nodes(data=True)
                if str(data.get("area_source", "")) == "default_gate_rule"
                and uses_spatial_storage(G, node)
            ),
            "euclidean_fallback_edge_count": sum(
                1
                for _, _, data in G.edges(data=True)
                if str(data.get("distance_source", "")) == "euclidean_fallback"
            ),
            "euclidean_fallback_monitored_edge_count": sum(
                1
                for _, _, data in G.edges(data=True)
                if str(data.get("distance_source", "")) == "euclidean_fallback"
                and _is_monitored_edge(data)
            ),
        },
        "clearance_times_by_line": {line: None for line, pop in target_by_line.items() if pop > 0},
        "clearance_times_by_line_core": {line: None for line, pop in core_target_by_line.items() if pop > 0},
        "clearance_times_by_line_transfer": {line: None for line, pop in transfer_target_by_line.items() if pop > 0},
        "queueing_time_by_line": {line: 0.0 for line in ALL_LINE_IDS},
        "high_density_exposure_by_line": {line: 0.0 for line in ALL_LINE_IDS},
        "exit_usage_by_line": {
            ext: {line: 0.0 for line in ALL_LINE_IDS}
            for ext in NODES_DATA.get("ALL_EXITS", {}).keys()
        },
        "exit_usage_by_source_group": {
            ext: {}
            for ext in NODES_DATA.get("ALL_EXITS", {}).keys()
        },
        "exit_usage": {ext: 0 for ext in NODES_DATA.get("ALL_EXITS", {}).keys()},
        "time_series_queue": {monitor_node: []} if monitor_node else {},
        "evacuation_curve": {"times": [], "remaining": [], "evacuated": []},
        "node_stats": {
            n: {
                "peak_people": 0.0,
                "peak_physical_people": 0.0,
                "peak_overflow_queue": 0.0,
                "peak_density": 0.0,
                "peak_load_ratio": 0.0,
                "peak_congestion_index": 0.0,
                "density_seconds": 0.0,
                "congestion_index_seconds": 0.0,
                "congestion_measure_type": "",
                "queue_seconds": 0.0,
                "congestion_seconds": 0.0,
                "time_at_receiving_limit": 0.0,
                "blocked_or_rejected_inflow": 0.0,
            }
            for n in G.nodes()
        },
        "time_series_by_line": {
            line: {"times": [], "speeds": [], "queues": []}
            for line in ALL_LINE_IDS
        },
        "node_series": {
            n: {"times": [], "queue": [], "travel_time": []}
            for n in monitored_queue_nodes
        },
        "edge_series": {
            edge_key: {"times": [], "passengers": [], "speed": [], "density": []}
            for edge_key in monitored_edges
        },
        "edge_stats": {
            edge_key: {
                "flow_total": 0.0,
                "peak_passengers": 0.0,
                "peak_speed": 0.0,
                "peak_density": 0.0,
                "density_seconds": 0.0,
                "congestion_seconds": 0.0,
            }
            for edge_key in monitored_edges
        },
        "physical_area_stats_by_line": {
            line: {
                "physical_clearance_time": None,
                "peak_node_people": 0.0,
                "peak_edge_people": 0.0,
                "peak_total_people": 0.0,
                "last_occupied_nodes": "",
                "last_occupied_edges": "",
            }
            for line in ALL_LINE_IDS
        },
    }

    sample_interval = max(float(metric_sample_interval_seconds), DELTA_T)
    next_detail_sample_time = 0.0

    def record_high_density_diagnostic(
        location_type,
        location_id,
        node_or_edge_type,
        area,
        area_source,
        people,
        physical_people,
        overflow_queue,
        density,
        exposure,
        spatial_storage_enabled,
        sample_time,
    ):
        if exposure <= 0.0:
            return
        time_bin = int(float(sample_time) // 100.0) * 100
        key = (location_type, location_id, time_bin)
        row = metrics["high_density_diagnostics"].setdefault(
            key,
            {
                "location_type": location_type,
                "location_id": location_id,
                "node_or_edge_type": node_or_edge_type,
                "area": float(area),
                "area_source": area_source,
                "people": 0.0,
                "physical_people": 0.0,
                "overflow_queue": 0.0,
                "density": 0.0,
                "exposure_person_seconds": 0.0,
                "initial_exposure_person_seconds": 0.0,
                "first_time": float(sample_time),
                "last_time": float(sample_time),
                "time_bin_100s": time_bin,
                "is_at_density_cap": False,
                "spatial_storage_enabled": bool(spatial_storage_enabled),
            },
        )
        row["people"] = max(row["people"], float(people))
        row["physical_people"] = max(row["physical_people"], float(physical_people))
        row["overflow_queue"] = max(row["overflow_queue"], float(overflow_queue))
        row["density"] = max(row["density"], float(density))
        row["exposure_person_seconds"] += float(exposure)
        if abs(float(sample_time)) <= 1e-9:
            row["initial_exposure_person_seconds"] += float(exposure)
        row["first_time"] = min(row["first_time"], float(sample_time))
        row["last_time"] = max(row["last_time"], float(sample_time))
        row["is_at_density_cap"] = bool(
            row["is_at_density_cap"]
            or (
                location_type == "node"
                and abs(
                    float(density) - HIGH_LOAD_JAM_DENSITY_P_PER_M2
                ) <= 1e-9
            )
        )

    while time < stop_at_time:
        current_time, _ = _ensure_transit_state(G)
        time = current_time
        diagnostics = G.graph.setdefault("_aa_diagnostics", {})
        diagnostics["simulation_step_count"] = (
            int(diagnostics.get("simulation_step_count", 0)) + 1
        )
        progress_mark = int(current_time)
        if (
            progress_mark % 100 == 0
            and G.graph.get("_last_progress_log_time") != progress_mark
        ):
            G.graph["_last_progress_log_time"] = progress_mark
            total_target_people = sum(
                float(target) for target in target_by_line.values() if target > 0
            )
            evacuated_so_far = sum(float(value) for value in evacuated_by_line.values())
            remaining_people = max(total_target_people - evacuated_so_far, 0.0)
            active_node_count = sum(
                1
                for _, data in G.nodes(data=True)
                if data.get("type") != "exit" and float(data.get("people", 0.0)) > 0.1
            )
            message = (
                f"progress sim_time={current_time:.1f}s "
                f"wall_clock={perf_counter() - run_wall_start:.2f}s "
                f"evacuated={evacuated_so_far:.0f} "
                f"remaining={remaining_people:.0f} "
                f"active_nodes={active_node_count}"
            )
            if G.graph.get("_active_simulation_method") == OUR_SINGLE_PATH_METHOD:
                active_aa_batches = sum(
                    1
                    for _, data in G.nodes(data=True)
                    for batch in data.get("_aa_batches", [])
                    if int(batch.get("amount", 0)) > 0
                )
                message += (
                    f" active_batches={active_aa_batches}"
                    f" astar_calls={int(diagnostics.get('astar_call_count', 0))}"
                    f" old_path_evaluations={int(diagnostics.get('old_path_evaluation_count', 0))}"
                    f" same_path_reuse={int(diagnostics.get('same_path_reuse_count', 0))}"
                    f" cutoff_no_improvement={int(diagnostics.get('astar_cutoff_no_improvement_count', 0))}"
                    f" committed_replan_skips={int(diagnostics.get('committed_replan_skip_count', 0))}"
                    f" committed_path_refreshes={int(diagnostics.get('committed_path_refresh_count', 0))}"
                    f" infeasible_old_paths={int(diagnostics.get('infeasible_old_path_count', 0))}"
                    f" infeasible_astar={int(diagnostics.get('infeasible_path_astar_count', 0))}"
                    f" infeasible_recoveries={int(diagnostics.get('infeasible_path_recovery_count', 0))}"
                    f" infeasible_no_alternative={int(diagnostics.get('infeasible_path_no_alternative_count', 0))}"
                    f" recovered_people={int(diagnostics.get('recovered_people_count', 0))}"
                )
            emit_progress(message)
        record_detailed_series = bool(
            collect_detailed_series
            and current_time + 1e-9 >= next_detail_sample_time
        )
        if record_detailed_series:
            next_detail_sample_time = current_time + sample_interval

        arrived_this_step = _process_transit_arrivals(
            G,
            current_time,
            evacuated_by_line=evacuated_by_line,
            evacuated_by_source_group=evacuated_by_source_group,
            exit_usage_dict=metrics["exit_usage_by_line"],
            exit_usage_by_source_group=metrics["exit_usage_by_source_group"],
            node_throughput_by_sg=node_throughput_by_sg,
        )
        evacuated_count += arrived_this_step
        _refresh_edge_runtime_densities(G, current_time)
        total_evacuated = sum(float(val) for val in evacuated_by_line.values())
        total_remaining = max(sum(float(target) for target in target_by_line.values() if target > 0) - total_evacuated, 0.0)
        metrics["evacuation_curve"]["times"].append(current_time)
        metrics["evacuation_curve"]["remaining"].append(total_remaining)
        metrics["evacuation_curve"]["evacuated"].append(total_evacuated)
        represented_at_nodes = sum(
            max(float(data.get("people", 0.0)), 0.0)
            for _, data in G.nodes(data=True)
            if data.get("type") != "exit"
        )
        represented_in_transit = sum(
            max(float(item.get("amount", 0.0)), 0.0)
            for item in G.graph.get("_transit_queue", [])
            if float(item.get("arrive_time", 0.0)) > current_time + 1e-9
        )
        metrics["occupancy_partition_max_error"] = max(
            metrics["occupancy_partition_max_error"],
            abs(
                represented_at_nodes
                + represented_in_transit
                - total_remaining
            ),
        )

        all_lines_cleared = True
        for line_id, target in target_by_line.items():
            if target > 0:
                # 1. 独立发奖牌：只要这条线跑完了，立刻记录当前时间，不管别人跑没跑完
                if metrics["clearance_times_by_line"].get(line_id) is None:
                    if evacuated_by_line[line_id] >= target  - 1e-9:
                        metrics["clearance_times_by_line"][line_id] = current_time

                # 2. 独立查缺勤：只要还有任何一条线没跑完，总清空标志就为 False
                if evacuated_by_line[line_id] < target - 1e-9:
                    all_lines_cleared = False

        # 注意：这里千万不要放在 for 循环里面！
        # 等 for 循环把所有线路都老老实实检查完之后，再判断要不要结束整个大仿真
        core_evacuated_by_line = {line: 0.0 for line in ALL_LINE_IDS}
        transfer_evacuated_by_line = {line: 0.0 for line in ALL_LINE_IDS}
        for source_group_id, amount in evacuated_by_source_group.items():
            line_id, source_type, _ = _parse_source_group_id(source_group_id)
            if line_id not in core_evacuated_by_line:
                continue
            if source_type == "transfer_people":
                transfer_evacuated_by_line[line_id] += float(amount)
            else:
                core_evacuated_by_line[line_id] += float(amount)

        for line_id, target in core_target_by_line.items():
            if target <= 0:
                continue
            if metrics["clearance_times_by_line_core"].get(line_id) is None:
                if core_evacuated_by_line[line_id] >= target - 1e-9:
                    metrics["clearance_times_by_line_core"][line_id] = current_time

        for line_id, target in transfer_target_by_line.items():
            if target <= 0:
                continue
            if metrics["clearance_times_by_line_transfer"].get(line_id) is None:
                if transfer_evacuated_by_line[line_id] >= target - 1e-9:
                    metrics["clearance_times_by_line_transfer"][line_id] = current_time

        if all_lines_cleared:
            break

        active_nodes = [
            n for n in G.nodes()
            if G.nodes[n].get("people", 0) > 0.1 and G.nodes[n].get("type") != "exit"
        ]

        current_high_density_exposure = 0.0
        current_queues_by_line = {line: 0.0 for line in ALL_LINE_IDS}
        current_moving_ppl_by_line = {line: 0.0 for line in ALL_LINE_IDS}
        current_speed_sum_by_line = {line: 0.0 for line in ALL_LINE_IDS}
        resource_queues = G.graph.get("_resource_queues", {})
        resource_queue_sources = G.graph.get("_resource_queue_sources", {})
        current_queue_by_node = {
            n: float(resource_queues.get(("facility", n), 0.0))
            for n in monitored_queue_nodes
        }

        total_resource_waiting = sum(max(float(value), 0.0) for value in resource_queues.values())
        metrics["queueing_time"] += total_resource_waiting * DELTA_T
        metrics["resource_queueing_time"] += total_resource_waiting * DELTA_T
        queue_by_source = {}
        for source_map in resource_queue_sources.values():
            for source_node, amount in source_map.items():
                queue_by_source[source_node] = queue_by_source.get(source_node, 0.0) + max(float(amount), 0.0)
        spatial_by_source = G.graph.get("_current_spatial_blocked_sources", {})
        step_resource_wait = 0.0
        step_spatial_wait = 0.0
        step_unassigned_wait = 0.0
        for source_node, node_data in G.nodes(data=True):
            if node_data.get("type") == "exit":
                continue
            stationary = max(float(node_data.get("people", 0.0)), 0.0)
            spatial = min(max(float(spatial_by_source.get(source_node, 0.0)), 0.0), stationary)
            resource = min(
                max(float(queue_by_source.get(source_node, 0.0)), 0.0),
                max(stationary - spatial, 0.0),
            )
            unassigned = max(stationary - spatial - resource, 0.0)
            step_spatial_wait += spatial
            step_resource_wait += resource
            step_unassigned_wait += unassigned
        metrics["resource_queue_person_seconds"] += step_resource_wait * DELTA_T
        metrics["spatial_blocked_person_seconds"] += step_spatial_wait * DELTA_T
        metrics["spatial_blocked_exposure_person_seconds"] += step_spatial_wait * DELTA_T
        metrics["unassigned_wait_person_seconds"] += step_unassigned_wait * DELTA_T
        metrics["stationary_person_seconds"] += (
            step_resource_wait + step_spatial_wait + step_unassigned_wait
        ) * DELTA_T
        for resource_id, queue_value in resource_queues.items():
            queue_value = max(float(queue_value), 0.0)
            resource_stat = metrics["resource_stats"].setdefault(
                resource_id,
                {
                    "total_throughput": 0.0,
                    "peak_queue": 0.0,
                    "queueing_person_seconds": 0.0,
                    "first_queue_time": None,
                    "last_queue_time": None,
                },
            )
            resource_stat["peak_queue"] = max(resource_stat["peak_queue"], queue_value)
            resource_stat["queueing_person_seconds"] += queue_value * DELTA_T
            if queue_value > 0.0:
                if resource_stat["first_queue_time"] is None:
                    resource_stat["first_queue_time"] = current_time
                resource_stat["last_queue_time"] = current_time
        for resource_id, source_map in resource_queue_sources.items():
            if resource_id[0] == "facility" and resource_id[1] in metrics["node_stats"]:
                metrics["node_stats"][resource_id[1]]["queue_seconds"] += (
                    sum(source_map.values()) * DELTA_T
                )
            for source_node, waiting in source_map.items():
                source_total = max(float(G.nodes[source_node].get("people", 0.0)), 0.0)
                if source_total <= 0:
                    continue
                for line_id, count in G.nodes[source_node].get("people_dict", {}).items():
                    share = max(float(count), 0.0) / source_total
                    attributed = float(waiting) * share * DELTA_T
                    metrics["queueing_time_by_line"][line_id] += attributed
                    current_queues_by_line[line_id] += float(waiting) * share

        # 先统计这一时刻节点状态
        for n in active_nodes:
            ppl = G.nodes[n]["people"]
            density, physical_ppl, overflow_queue = _evaluation_node_physical_state(G, n)

            metrics["node_stats"][n]["peak_people"] = max(metrics["node_stats"][n]["peak_people"], ppl)
            metrics["node_stats"][n]["peak_physical_people"] = max(
                metrics["node_stats"][n]["peak_physical_people"], physical_ppl
            )
            metrics["node_stats"][n]["peak_overflow_queue"] = max(
                metrics["node_stats"][n]["peak_overflow_queue"], overflow_queue
            )
            metrics["peak_overflow_queue"] = max(metrics["peak_overflow_queue"], overflow_queue)
            # Evaluation is method-independent: these fields describe only
            # observed physical density, never queue reservations or horizons.
            metrics["node_stats"][n]["congestion_measure_type"] = "density"
            metrics["node_stats"][n]["peak_congestion_index"] = max(
                metrics["node_stats"][n]["peak_congestion_index"],
                density,
            )
            metrics["node_stats"][n]["congestion_index_seconds"] += density * DELTA_T
            metrics["node_stats"][n]["peak_density"] = max(metrics["node_stats"][n]["peak_density"], density)
            metrics["node_stats"][n]["density_seconds"] += density * DELTA_T
            metrics["peak_density"] = max(metrics["peak_density"], density)
            metrics["peak_congestion_index"] = max(metrics["peak_congestion_index"], density)

            if uses_spatial_storage(G, n):
                storage_capacity = _node_storage_capacity(G, n)
                reserved = _reserved_transit_to_node(G, n)
                if (
                    math.isfinite(storage_capacity)
                    and ppl + reserved >= storage_capacity - 1e-9
                ):
                    metrics["node_stats"][n]["time_at_receiving_limit"] += DELTA_T

            if density >= HIGH_LOAD_JAM_DENSITY_P_PER_M2:
                exposure = physical_ppl * DELTA_T
                current_high_density_exposure += exposure
                metrics["node_high_density_exposure_person_seconds"] += exposure
                if abs(current_time) <= 1e-9:
                    metrics["initial_high_density_exposure_person_seconds"] += exposure
                metrics["node_stats"][n]["congestion_seconds"] += exposure
                node_data = G.nodes[n]
                record_high_density_diagnostic(
                    "node",
                    n,
                    str(node_data.get("type", "")),
                    effective_node_area(G, n),
                    str(node_data.get("area_source", "configured_node_area")),
                    ppl,
                    physical_ppl,
                    overflow_queue,
                    density,
                    exposure,
                    uses_spatial_storage(G, n),
                    current_time,
                )
                physical_share = physical_ppl / max(ppl, 0.001)
                for line_id, count in G.nodes[n].get("people_dict", {}).items():
                    if count <= 0:
                        continue
                    physical_count = count * physical_share
                    metrics["high_density_exposure_by_line"][line_id] += physical_count * DELTA_T

        # 关键改动：这里不再只走单一 next node，而是允许并行分流
        edge_snapshot_for_exposure = _capture_edge_snapshot(G, current_time, monitored_edges)
        current_edge_high_density_exposure = 0.0
        for edge_key, snapshot in edge_snapshot_for_exposure.items():
            passengers = float(snapshot.get("passengers", 0.0))
            if passengers <= 0:
                continue
            try:
                u, v = [part.strip() for part in edge_key.split("->", 1)]
            except ValueError:
                continue
            if u not in G.nodes or v not in G.nodes or not G.has_edge(u, v):
                continue
            density = passengers / _edge_effective_area(G, u, v)
            metrics["edge_stats"][edge_key]["peak_passengers"] = max(
                metrics["edge_stats"][edge_key]["peak_passengers"],
                passengers,
            )
            metrics["edge_stats"][edge_key]["peak_density"] = max(
                metrics["edge_stats"][edge_key]["peak_density"],
                density,
            )
            metrics["edge_stats"][edge_key]["density_seconds"] += density * DELTA_T
            if density >= HIGH_LOAD_JAM_DENSITY_P_PER_M2:
                exposure = passengers * DELTA_T
                current_edge_high_density_exposure += exposure
                if abs(current_time) <= 1e-9:
                    metrics["initial_high_density_exposure_person_seconds"] += exposure
                metrics["edge_stats"][edge_key]["congestion_seconds"] += exposure
                edge_data = G[u][v]
                edge_area_source = edge_data.get("area_source")
                if not edge_area_source:
                    edge_area_source = (
                        "explicit_edge_area"
                        if float(edge_data.get("edge_area", 0.0) or 0.0) > 0.0
                        else "derived_length_width:"
                        + str(edge_data.get("distance_source", "configured_length"))
                    )
                record_high_density_diagnostic(
                    "edge",
                    edge_key,
                    str(edge_data.get("edge_type", "")),
                    _edge_effective_area(G, u, v),
                    str(edge_area_source),
                    passengers,
                    passengers,
                    0.0,
                    density,
                    exposure,
                    True,
                    current_time,
                )
                for line_id, count in snapshot.get("line_shares", {}).items():
                    if count > 0:
                        metrics["high_density_exposure_by_line"][line_id] += count * DELTA_T

        current_high_density_exposure += current_edge_high_density_exposure
        metrics["edge_high_density_exposure_person_seconds"] += current_edge_high_density_exposure

        moves = get_step_moves(G, method, shortest_dists)
        G.graph["_gate_selected_people_this_step"] = {
            gate: sum(float(flow) for _, v, flow in moves if v == gate)
            for gate in G.nodes
            if is_point_service_resource(G, gate)
        }

        for (u, v, flow) in moves:
            if flow > 0:
                ek = _edge_key(u, v)
                edge_flow_totals[ek] = edge_flow_totals.get(ek, 0.0) + flow

        metrics["high_density_exposure_person_seconds"] += current_high_density_exposure
        if record_detailed_series and monitor_node and monitor_node in G.nodes:
            metrics["time_series_queue"][monitor_node].append(G.nodes[monitor_node].get("people", 0))

        scheduled_moves = _schedule_moves_as_transit(G, moves)
        _update_gate_service_diagnostics(
            G,
            current_time,
            scheduled_moves,
        )
        _update_edge_state_diagnostics(
            G,
            metrics,
            current_time,
            scheduled_moves,
        )
        _update_physical_line_occupancy_metrics(G, metrics, current_time)
        for item in scheduled_moves:
            amount = float(item["amount"])
            tt = max(float(item["travel_time"]), 0.001)
            u_node, v_node = item["u"], item["v"]
            length = max(float(G[u_node][v_node].get("length", 0.0)), 0.0)
            actual_spd = length / tt if length > 0 else 0.0
            edge_type = str(G[u_node][v_node].get("edge_type", "")).lower()
            is_physical_movement = (
                length > 0.0 and edge_type not in EDGE_DENSITY_EXEMPT_TYPES
            )
            if is_physical_movement:
                total_flow_moves += amount
                sum_speed_weighted += amount * actual_spd
                total_movement_distance += amount * length
                moving_person_seconds += amount * tt
            else:
                zero_or_topological_move_count += amount

            for line_id, line_flow in item.get("line_shares", {}).items():
                if line_flow <= 0:
                    continue
                current_moving_ppl_by_line[line_id] += line_flow
                current_speed_sum_by_line[line_id] += line_flow * actual_spd

            edge_key = _edge_key(u_node, v_node)
            resource_id = edge_resource_id(G, u_node, v_node)
            resource_stat = metrics["resource_stats"].setdefault(
                resource_id,
                {
                    "total_throughput": 0.0,
                    "peak_queue": 0.0,
                    "queueing_person_seconds": 0.0,
                    "first_queue_time": None,
                    "last_queue_time": None,
                },
            )
            resource_stat["total_throughput"] += amount
            source_group_edge = edge_flow_by_source_group.setdefault((u_node, v_node), {})
            for source_group_id, source_group_flow in item.get("source_group_shares", {}).items():
                if source_group_flow <= 0:
                    continue
                source_group_edge[source_group_id] = (
                    source_group_edge.get(source_group_id, 0.0) + float(source_group_flow)
                )
            if edge_key in metrics["edge_stats"]:
                metrics["edge_stats"][edge_key]["flow_total"] += amount
                metrics["edge_stats"][edge_key]["peak_passengers"] = max(
                    metrics["edge_stats"][edge_key]["peak_passengers"], amount
                )
                metrics["edge_stats"][edge_key]["peak_speed"] = max(
                    metrics["edge_stats"][edge_key]["peak_speed"], actual_spd
                )

        travel_person_seconds += sum(item["amount"] * item["travel_time"] for item in scheduled_moves)
        G.graph["_sim_time"] = current_time + DELTA_T
        equivalence_observer = G.graph.get("_aa_equivalence_observer")
        if callable(equivalence_observer):
            equivalence_observer(
                G,
                current_time,
                scheduled_moves,
                total_evacuated,
            )

        node_travel_sum = {n: 0.0 for n in monitored_queue_nodes}
        node_travel_flow = {n: 0.0 for n in monitored_queue_nodes}
        for item in scheduled_moves:
            u = item["u"]
            if u not in node_travel_sum:
                continue
            node_travel_sum[u] += item["amount"] * item["travel_time"]
            node_travel_flow[u] += item["amount"]

        # 记录每条线的瞬时折线数据
        for line_id, target in target_by_line.items():
            if record_detailed_series and target > 0:
                metrics["time_series_by_line"][line_id]["times"].append(time)
                metrics["time_series_by_line"][line_id]["queues"].append(current_queues_by_line[line_id])
                if current_moving_ppl_by_line[line_id] > 0:
                    metrics["time_series_by_line"][line_id]["speeds"].append(
                        current_speed_sum_by_line[line_id] / current_moving_ppl_by_line[line_id]
                    )
                else:
                    metrics["time_series_by_line"][line_id]["speeds"].append(0.0)

        for n in monitored_queue_nodes if record_detailed_series else ():
            metrics["node_series"][n]["times"].append(current_time)
            metrics["node_series"][n]["queue"].append(current_queue_by_node.get(n, 0.0))
            if node_travel_flow[n] > 0:
                metrics["node_series"][n]["travel_time"].append(node_travel_sum[n] / node_travel_flow[n])
            else:
                metrics["node_series"][n]["travel_time"].append(np.nan)

        edge_snapshot = (
            _capture_edge_snapshot(G, current_time, monitored_edges)
            if record_detailed_series else {}
        )
        for edge_key, series in (
            metrics["edge_series"].items() if record_detailed_series else ()
        ):
            series["times"].append(current_time)
            passengers = edge_snapshot[edge_key]["passengers"] if edge_key in edge_snapshot else 0.0
            series["passengers"].append(passengers)
            try:
                u, v = [part.strip() for part in edge_key.split("->", 1)]
                density = passengers / _edge_effective_area(G, u, v) if G.has_edge(u, v) else 0.0
            except ValueError:
                density = 0.0
            series["density"].append(density)
            if passengers > 0:
                series["speed"].append(edge_snapshot[edge_key]["speed_sum"] / passengers)
            else:
                series["speed"].append(np.nan)

        time = current_time + DELTA_T

    metrics["time"] = time
    # Comparable to Pathfinder's time-sampled moving speed: integral distance
    # divided by moving person-time. Queueing/stationary time is excluded here.
    metrics["avg_speed"] = (
        total_movement_distance / moving_person_seconds
        if moving_person_seconds > 0 else 0.0
    )
    metrics["moving_average_speed"] = metrics["avg_speed"]
    metrics["edge_traversal_avg_speed"] = (
        sum_speed_weighted / total_flow_moves if total_flow_moves > 0 else 0.0
    )
    metrics["edge_traversal_average_speed"] = metrics["edge_traversal_avg_speed"]
    metrics["total_movement_distance"] = total_movement_distance
    metrics["moving_person_seconds"] = moving_person_seconds
    total_target = sum(float(target) for target in target_by_line.values() if target > 0)
    metrics["avg_travel_time"] = travel_person_seconds / total_target if total_target > 0 else 0.0
    final_evacuated = sum(float(value) for value in evacuated_by_line.values())
    remaining_people = max(total_target - final_evacuated, 0.0)
    completed = remaining_people <= 1e-9
    metrics["completed"] = completed
    metrics["remaining_people"] = remaining_people
    metrics["termination_reason"] = "completed" if completed else "time_limit"
    metrics["mean_queueing_time"] = (
        metrics["resource_queueing_time"] / total_target if total_target > 0 else 0.0
    )
    metrics["mean_stationary_time"] = (
        metrics["stationary_person_seconds"] / total_target if total_target > 0 else 0.0
    )
    metrics["mean_moving_time"] = (
        moving_person_seconds / total_target if total_target > 0 else 0.0
    )
    metrics["in_transit_person_seconds"] = moving_person_seconds
    active_person_seconds = sum(
        max(float(value), 0.0) * DELTA_T
        for value in metrics["evacuation_curve"].get("remaining", [])
    )
    metrics["mean_total_evacuation_time"] = (
        active_person_seconds / total_target if total_target > 0 else 0.0
    )
    metrics["total_system_person_seconds"] = active_person_seconds
    metrics["effective_evacuation_speed"] = (
        total_movement_distance / active_person_seconds
        if active_person_seconds > 0.0 else 0.0
    )
    metrics["zero_or_topological_movement_people"] = zero_or_topological_move_count
    diagnostic_sum = sum(
        float(row["exposure_person_seconds"])
        for row in metrics["high_density_diagnostics"].values()
    )
    metrics["high_density_diagnostic_sum_person_seconds"] = diagnostic_sum
    metrics["high_density_diagnostic_sum_error"] = (
        diagnostic_sum - metrics["high_density_exposure_person_seconds"]
    )
    metrics["high_density_diagnostics"] = list(
        metrics["high_density_diagnostics"].values()
    )
    edge_state_rows = list(metrics["edge_state_diagnostics"].values())
    physical_occupied_rows = [
        row
        for row in edge_state_rows
        if row["is_physical_edge"]
        and row["minimum_speed_m_per_s"] is not None
        and row["maximum_in_transit_people"] > 0.0
    ]
    metrics["edge_lowest_speed_top20"] = sorted(
        physical_occupied_rows,
        key=lambda row: (
            float(row["minimum_speed_m_per_s"]),
            -float(row["cumulative_in_transit_person_seconds"]),
            str(row["edge"]),
        ),
    )[:20]
    metrics["edge_low_speed_person_seconds_top20"] = sorted(
        physical_occupied_rows,
        key=lambda row: (
            -float(row["speed_below_0_3_person_seconds"]),
            float(row["minimum_speed_m_per_s"]),
            str(row["edge"]),
        ),
    )[:20]
    last_snapshot_time = metrics["last_in_transit_snapshot_time_seconds"]
    metrics["final_in_transit_edges"] = (
        sorted(
            [
                row
                for row in edge_state_rows
                if row["last_occupied_time_seconds"] is not None
                and abs(
                    float(row["last_occupied_time_seconds"])
                    - float(last_snapshot_time)
                ) <= 1e-9
            ],
            key=lambda row: (
                -float(row["last_observed_in_transit_people"]),
                str(row["edge"]),
            ),
        )
        if last_snapshot_time is not None
        else []
    )
    metrics["edge_state_diagnostics"] = sorted(
        edge_state_rows,
        key=lambda row: str(row["edge"]),
    )

    block_rows = []
    block_graph_diagnostics = G.graph.get(
        "_receiving_block_diagnostics",
        {},
    )
    for block_type in (
        "edge_receiving_hard_limit",
        "destination_capacity_or_spillback",
    ):
        per_edge = block_graph_diagnostics.get(block_type, {})
        for u, v in G.edges():
            stat = per_edge.get((u, v), {})
            block_rows.append({
                "block_type": block_type,
                "edge": _edge_key(u, v),
                "source_node": u,
                "destination_node": v,
                "rejection_event_count": int(
                    stat.get("rejection_event_count", 0)
                ),
                "rejected_people": float(
                    stat.get("rejected_people", 0.0)
                ),
                "blocked_person_seconds": float(
                    stat.get("blocked_person_seconds", 0.0)
                ),
            })
    metrics["receiving_block_diagnostics"] = block_rows
    metrics["receiving_block_summary"] = {
        "edge_receiving_hard_limit_enabled": (
            edge_receiving_hard_limit_enabled(G)
        ),
        "edge_receiving_density_limit_p_per_m2": (
            edge_receiving_density_limit(G)
        ),
        "edge_receiving_hard_limit_rejection_event_count": sum(
            int(row["rejection_event_count"])
            for row in block_rows
            if row["block_type"] == "edge_receiving_hard_limit"
        ),
        "edge_receiving_hard_limit_rejected_people": sum(
            float(row["rejected_people"])
            for row in block_rows
            if row["block_type"] == "edge_receiving_hard_limit"
        ),
        "edge_receiving_hard_limit_blocked_person_seconds": sum(
            float(row["blocked_person_seconds"])
            for row in block_rows
            if row["block_type"] == "edge_receiving_hard_limit"
        ),
        "destination_capacity_or_spillback_rejection_event_count": sum(
            int(row["rejection_event_count"])
            for row in block_rows
            if row["block_type"] == "destination_capacity_or_spillback"
        ),
        "destination_capacity_or_spillback_rejected_people": sum(
            float(row["rejected_people"])
            for row in block_rows
            if row["block_type"] == "destination_capacity_or_spillback"
        ),
        "destination_capacity_or_spillback_blocked_person_seconds": sum(
            float(row["blocked_person_seconds"])
            for row in block_rows
            if row["block_type"] == "destination_capacity_or_spillback"
        ),
    }
    metrics["edge_low_speed_person_seconds_by_line"] = [
        {
            "line": line,
            **metrics["edge_low_speed_person_seconds_by_line"][line],
        }
        for line in ALL_LINE_IDS
    ]
    for node, rejected in G.graph.get("_spatial_rejected_inflow", {}).items():
        if node in metrics["node_stats"]:
            metrics["node_stats"][node]["blocked_or_rejected_inflow"] = float(rejected)

    max_predicted_waits = G.graph.get("_resource_max_predicted_wait", {})
    mesoscopic_execution = G.graph.get("_mesoscopic_resource_execution", {})
    for resource_id in mesoscopic_execution:
        metrics["resource_stats"].setdefault(resource_id, {
            "total_throughput": 0.0,
            "peak_queue": 0.0,
            "queueing_person_seconds": 0.0,
            "first_queue_time": None,
            "last_queue_time": None,
        })
    for resource_id, stat in metrics["resource_stats"].items():
        capacity = resource_capacity_per_second(G, resource_id)
        stat["resource_id"] = resource_id_text(resource_id)
        stat["resource_type"] = resource_type(G, resource_id)
        stat["capacity_per_second"] = capacity
        stat["mean_queue"] = (
            stat["queueing_person_seconds"] / time if time > 0 else 0.0
        )
        stat["maximum_predicted_wait"] = float(max_predicted_waits.get(resource_id, 0.0))
        stat["utilization"] = (
            stat["total_throughput"] / (capacity * time)
            if time > 0 and capacity > 0 and math.isfinite(capacity)
            else 0.0
        )
        stat["associated_edges"] = "; ".join(
            f"{u} -> {v}" for u, v in resource_control_edges(G, resource_id)
        )
        stat.update(mesoscopic_execution.get(resource_id, {}))
    metrics["exit_usage"] = {
        exit_name: sum(float(flow) for flow in line_map.values())
        for exit_name, line_map in metrics["exit_usage_by_line"].items()
    }
    def _jain_fairness(values):
        values = [max(float(value), 0.0) for value in values]
        squared_sum = sum(value * value for value in values)
        if not values or squared_sum <= 0.0:
            return 0.0
        return sum(values) ** 2 / (len(values) * squared_sum)

    metrics["exit_load_jain_index"] = _jain_fairness(
        metrics["exit_usage"].values()
    )
    key_facility_types = {"gate", "stair", "escalator"}
    key_facility_throughput = {}
    for resource_id in iter_physical_resources(G):
        if resource_id[0] != "facility":
            continue
        node = resource_id[1]
        if str(G.nodes[node].get("type", "")).lower() not in key_facility_types:
            continue
        key_facility_throughput[node] = float(
            metrics["resource_stats"].get(resource_id, {}).get("total_throughput", 0.0)
        )
    metrics["key_facility_throughput"] = key_facility_throughput
    metrics["key_facility_load_jain_index"] = _jain_fairness(
        key_facility_throughput.values()
    )
    metrics["edge_flow_totals"] = edge_flow_totals
    metrics["edge_flow_by_source_group"] = edge_flow_by_source_group
    metrics["node_throughput_by_sg"] = node_throughput_by_sg
    metrics["evacuation_arrival_events"] = list(
        G.graph.get("_evacuation_arrival_events", [])
    )
    metrics["completed_executed_routes"] = [
        {
            "source_group": source_group,
            "raw_full_path": list(path),
            "route_people": int(amount),
        }
        for (source_group, path), amount in sorted(
            G.graph.get("_completed_executed_routes", {}).items(),
            key=lambda item: (str(item[0][0]), tuple(map(str, item[0][1]))),
        )
        if int(amount) > 0
    ]
    metrics["route_tracking_errors"] = list(
        G.graph.get("_route_tracking_errors", [])
    )
    metrics["mesoscopic_diagnostics"] = dict(
        G.graph.get("_mesoscopic_diagnostics", {})
    )
    metrics["mesoscopic_diagnostics"].setdefault("nondecision_replan_count", 0)
    metrics["mesoscopic_diagnostics"].setdefault("decision_count", 0)
    metrics["mesoscopic_diagnostics"].setdefault("segment_commitment_count", 0)
    metrics["mesoscopic_diagnostics"].setdefault("reroute_after_rejection_count", 0)
    prediction_rows = list(G.graph.get("_aa_prediction_accuracy", []))
    metrics["aa_prediction_accuracy"] = prediction_rows
    metrics["prediction_mean_absolute_error"] = (
        sum(float(row["absolute_error"]) for row in prediction_rows) / len(prediction_rows)
        if prediction_rows else 0.0
    )
    metrics["prediction_bias"] = (
        sum(float(row["error"]) for row in prediction_rows) / len(prediction_rows)
        if prediction_rows else 0.0
    )
    metrics["aa_diagnostics"] = dict(G.graph.get("_aa_diagnostics", {}))
    metrics["gate_approach_replan_diagnostics"] = list(
        G.graph.get("_aa_gate_replan_diagnostics", [])
    )
    metrics["gate_approach_connectivity"] = list(
        G.graph.get("gate_approach_connectivity", [])
    )
    metrics["l7_hall_common_decision_diagnostics"] = list(
        G.graph.get("_l7_hall_decision_diagnostics", [])
    )
    hall_summary = dict(
        G.graph.get("_l7_hall_common_decision_summary", {})
    )
    aa_diagnostics = G.graph.get("_aa_diagnostics", {})
    for field in (
        "hall_gate_switch_decision_count",
        "hall_gate_switch_decision_people",
        "hall_gate_switch_executed_count",
        "hall_gate_switch_executed_people",
        "gate_queue_replan_attempt_count",
        "improved_density_triggered_switch_count",
        "aa_prediction_triggered_switch_count",
    ):
        hall_summary[field] = float(
            hall_summary.get(field, 0)
        ) + float(aa_diagnostics.get(field, 0))
    metrics["l7_hall_common_decision_summary"] = hall_summary
    metrics["l7_common_hall_topology_audit"] = list(
        G.graph.get("l7_common_hall_topology_audit", [])
    )
    metrics["l7_common_hall_vertical_integration_enabled"] = bool(
        G.graph.get("l7_common_hall_vertical_integration_enabled", False)
    )
    gate_rows = []
    for gate, stat in sorted(
        G.graph.get("_gate_service_diagnostics", {}).items()
    ):
        row = {"gate": gate}
        row.update(stat)
        for field in (
            "gate_arrival_people",
            "gate_service_people",
            "gate_queue_person_seconds",
            "gate_max_queue_people",
            "gate_upstream_spillback_person_seconds",
            "gate_double_service_violation_count",
            "gate_capacity_violation_count",
            "gate_storage_capacity_people",
            "gate_peak_storage_utilization",
            "gate_storage_overflow_people",
        ):
            row.setdefault(field, 0)
        gate_rows.append(row)
    metrics["gate_service_diagnostics"] = gate_rows
    metrics["gate_service_diagnostics_summary"] = {
        field: sum(float(row.get(field, 0.0)) for row in gate_rows)
        for field in (
            "gate_arrival_people",
            "gate_service_people",
            "gate_queue_person_seconds",
            "gate_upstream_spillback_person_seconds",
            "gate_double_service_violation_count",
            "gate_capacity_violation_count",
            "gate_storage_capacity_people",
            "gate_storage_overflow_people",
        )
    }
    metrics["gate_service_diagnostics_summary"][
        "gate_peak_storage_utilization"
    ] = max(
        (float(row.get("gate_peak_storage_utilization", 0.0)) for row in gate_rows),
        default=0.0,
    )
    metrics["gate_service_diagnostics_summary"]["gate_max_queue_people"] = max(
        (float(row.get("gate_max_queue_people", 0.0)) for row in gate_rows),
        default=0.0,
    )
    gate_backlog_rows = []
    for gate, stat in sorted(
        G.graph.get("_gate_backlog_diagnostics", {}).items()
    ):
        row = {"gate": gate}
        row.update(stat)
        for field in (
            "gate_node_waiting_people",
            "gate_node_occupancy_people",
            "gate_upstream_blocked_people",
            "gate_spillback_queue_people",
            "gate_service_backlog_people",
            "gate_routing_queue_people",
            "improved_queue_q_used",
            "aa_queue_q_used",
            "gate_backlog_overlap_people",
            "gate_backlog_mismatch_count",
        ):
            row.setdefault(field, 0)
        gate_backlog_rows.append(row)
    metrics["gate_backlog_diagnostics"] = gate_backlog_rows
    metrics["gate_backlog_step_trace"] = list(
        G.graph.get("_gate_backlog_step_trace", [])
    )
    improved_density_rows = []
    for gate, stat in sorted(
        G.graph.get("_improved_gate_density_diagnostics", {}).items()
    ):
        row = {"gate": gate}
        row.update(stat)
        improved_density_rows.append(row)
    metrics["improved_gate_density_diagnostics"] = improved_density_rows
    metrics["improved_gate_density_diagnostics_summary"] = {
        field: sum(float(row.get(field, 0.0)) for row in improved_density_rows)
        for field in (
            "improved_gate_density_actual_people",
            "improved_gate_density_upstream_excluded_people",
            "improved_gate_density_duplicate_count",
        )
    }
    improved_high_cost_diagnostics = dict(
        G.graph.get(
            "_improved_temporary_high_cost_diagnostics",
            {},
        )
    )
    for field in (
        "temporary_high_cost_events",
        "recovered_next_step_events",
        "high_cost_active_edges",
        "maximum_high_cost_active_edges",
        "stale_high_cost_state_count",
        "crossline_committed_continuation_events",
        "crossline_committed_continuation_people",
    ):
        improved_high_cost_diagnostics.setdefault(field, 0)
    metrics["improved_temporary_high_cost_diagnostics"] = (
        improved_high_cost_diagnostics
    )
    metrics["improved_temporary_high_cost_trace"] = list(
        G.graph.get("_improved_temporary_high_cost_trace", [])
    )
    metrics["improved_temporary_high_cost_step_diagnostics"] = list(
        G.graph.get(
            "_improved_temporary_high_cost_step_diagnostics", []
        )
    )
    metrics["improved_ordinary_crossline_controls"] = list(
        G.graph.get("_improved_ordinary_crossline_controls", [])
    )
    metrics["step0_aa_candidate_diagnostics"] = list(
        G.graph.get("_step0_aa_candidate_diagnostics", [])
    )
    metrics["aa_astar_call_count"] = int(
        metrics["aa_diagnostics"].get("astar_call_count", 0)
    )
    metrics["aa_old_path_evaluation_count"] = int(
        metrics["aa_diagnostics"].get("old_path_evaluation_count", 0)
    )
    metrics["aa_same_path_reuse_count"] = int(
        metrics["aa_diagnostics"].get("same_path_reuse_count", 0)
    )
    metrics["aa_astar_cutoff_no_improvement_count"] = int(
        metrics["aa_diagnostics"].get("astar_cutoff_no_improvement_count", 0)
    )
    risk_summary = (
        spr.aa_density_risk_summary(G)
        if hasattr(spr, "aa_density_risk_summary")
        else {}
    )
    metrics["aa_safety_weight"] = float(
        risk_summary.get("aa_safety_weight", 0.0)
    )
    metrics["aa_cumulative_predicted_risk_time"] = float(
        risk_summary.get("cumulative_predicted_risk_time", 0.0)
    )
    metrics["aa_average_predicted_density_risk"] = float(
        risk_summary.get("average_predicted_density_risk", 0.0)
    )
    metrics["aa_predicted_density_above_3_count"] = int(
        risk_summary.get("predicted_density_above_3_count", 0)
    )
    metrics["aa_predicted_density_above_3_5_count"] = int(
        risk_summary.get("predicted_density_above_3_5_count", 0)
    )
    metrics["aa_skipped_jam_density_edges"] = int(
        risk_summary.get("skipped_jam_density_edges", 0)
    )
    metrics["predicted_planning_node_moderate_risk_time"] = float(
        risk_summary.get("predicted_planning_node_moderate_risk_time", 0.0)
    )
    metrics["predicted_planning_edge_moderate_risk_time"] = float(
        risk_summary.get("predicted_planning_edge_moderate_risk_time", 0.0)
    )
    metrics["predicted_planning_node_severe_risk_time"] = float(
        risk_summary.get("predicted_planning_node_severe_risk_time", 0.0)
    )
    metrics["predicted_planning_edge_severe_risk_time"] = float(
        risk_summary.get("predicted_planning_edge_severe_risk_time", 0.0)
    )
    metrics["aa_density_risk_summary"] = risk_summary
    metrics["bottleneck_resources"] = build_resource_bottleneck_rows(metrics, top_k=20)
    metrics["spatial_bottlenecks"] = build_spatial_bottleneck_rows(G, metrics, top_k=20)
    metrics["wall_clock_runtime_seconds"] = perf_counter() - run_wall_start
    if G.graph.get("_active_simulation_method") == OUR_SINGLE_PATH_METHOD:
        diagnostics = metrics["aa_diagnostics"]
        if bool(G.graph.get("_fast_exact_aa", FAST_EXACT_AA)):
            if int(
                diagnostics.get(
                    "predicted_queue_fallback_linear_scan_count",
                    0,
                )
            ) != 0:
                raise AssertionError(
                    "FAST_EXACT_AA resource queue used a linear fallback"
                )
            if int(
                diagnostics.get(
                    "spatial_fallback_linear_scan_count",
                    0,
                )
            ) != 0:
                raise AssertionError(
                    "FAST_EXACT_AA spatial prediction used a linear fallback"
                )
        summary_fields = (
            (
                "wall_clock_runtime_seconds",
                metrics["wall_clock_runtime_seconds"],
            ),
            ("astar_call_count", diagnostics.get("astar_call_count", 0)),
            (
                "old_path_evaluation_count",
                diagnostics.get("old_path_evaluation_count", 0),
            ),
            (
                "old_path_evaluation_runtime_seconds",
                diagnostics.get("old_path_evaluation_runtime_seconds", 0.0),
            ),
            (
                "predicted_queue_query_count",
                diagnostics.get("predicted_queue_query_count", 0),
            ),
            (
                "predicted_queue_index_query_count",
                diagnostics.get("predicted_queue_index_query_count", 0),
            ),
            (
                "predicted_queue_fallback_linear_scan_count",
                diagnostics.get(
                    "predicted_queue_fallback_linear_scan_count",
                    0,
                ),
            ),
            (
                "spatial_index_query_count",
                diagnostics.get("spatial_index_query_count", 0),
            ),
            (
                "spatial_fallback_linear_scan_count",
                diagnostics.get(
                    "spatial_fallback_linear_scan_count",
                    0,
                ),
            ),
            (
                "max_active_batch_count",
                diagnostics.get("max_active_batch_count", 0),
            ),
        )
        print("AA exact-performance summary")
        for field, value in summary_fields:
            print(f"{field}={value}")
    return metrics


def build_resource_bottleneck_rows(metrics, top_k=20):
    rows = [dict(stat) for stat in metrics.get("resource_stats", {}).values()]
    rows.sort(
        key=lambda row: (
            float(row.get("queueing_person_seconds", 0.0)),
            float(row.get("peak_queue", 0.0)),
            float(row.get("total_throughput", 0.0)),
        ),
        reverse=True,
    )
    return rows[:top_k]


def build_spatial_bottleneck_rows(G, metrics, top_k=20):
    rows = []
    for node, stat in metrics.get("node_stats", {}).items():
        if node not in G.nodes or not uses_spatial_storage(G, node):
            continue
        rows.append({
            "node": node,
            "node_type": str(G.nodes[node].get("type", "")),
            "effective_area": effective_node_area(G, node),
            "storage_capacity": _node_storage_capacity(G, node),
            "peak_people": float(stat.get("peak_people", 0.0)),
            "peak_density": float(stat.get("peak_density", 0.0)),
            "time_at_receiving_limit": float(stat.get("time_at_receiving_limit", 0.0)),
            "blocked_or_rejected_inflow": float(stat.get("blocked_or_rejected_inflow", 0.0)),
        })
    rows.sort(
        key=lambda row: (
            row["blocked_or_rejected_inflow"],
            row["time_at_receiving_limit"],
            row["peak_density"],
        ),
        reverse=True,
    )
    return rows[:top_k]


def _fast_exact_sorted_items(mapping):
    return tuple(
        sorted(
            mapping.items(),
            key=lambda item: repr(item[0]),
        )
    )


def _fast_exact_step_snapshot(
    G,
    current_time,
    scheduled_moves,
    total_evacuated,
):
    nodes = {}
    batches = {}
    prediction_costs = {}
    for node in sorted(G.nodes(), key=str):
        data = G.nodes[node]
        nodes[node] = {
            "people": data.get("people", 0),
            "people_dict": _fast_exact_sorted_items(
                data.get("people_dict", {})
            ),
            "source_group_dict": _fast_exact_sorted_items(
                data.get("source_group_dict", {})
            ),
        }
        for batch in data.get("_aa_batches", []):
            batch_id = batch.get("batch_id")
            batches[batch_id] = {
                "node": node,
                "batch_id": batch_id,
                "amount": batch.get("amount", 0),
                "current_path": tuple(batch.get("current_path") or ()),
                "waiting_resource": batch.get("waiting_resource"),
            }
            prediction_costs[batch_id] = tuple(
                float(item.get("objective_cost", 0.0))
                for item in batch.get("path_predictions", [])
            )

    accepted_moves = tuple(
        (
            item.get("u"),
            item.get("v"),
            item.get("amount"),
        )
        for item in scheduled_moves
    )
    transit = tuple(
        (
            item.get("u"),
            item.get("v"),
            item.get("amount"),
            item.get("depart_time"),
            item.get("arrive_time"),
            item.get("aa_batch_state", {}).get("batch_id"),
            tuple(
                item.get("aa_batch_state", {}).get("current_path")
                or ()
            ),
        )
        for item in G.graph.get("_transit_queue", [])
    )
    resource_queue_sources = {
        resource_id: dict(source_map)
        for resource_id, source_map in G.graph.get(
            "_resource_queue_sources",
            {},
        ).items()
    }
    completed_routes = tuple(
        sorted(
            (
                source_group,
                tuple(path),
                amount,
            )
            for (source_group, path), amount in G.graph.get(
                "_completed_executed_routes",
                {},
            ).items()
        )
    )
    return {
        "time": float(current_time),
        "accepted_moves": accepted_moves,
        "nodes": nodes,
        "resource_queues": dict(G.graph.get("_resource_queues", {})),
        "resource_queue_sources": resource_queue_sources,
        "transit_queue": transit,
        "batches": batches,
        "prediction_costs": prediction_costs,
        "total_evacuated": total_evacuated,
        "completed_routes": completed_routes,
    }


def _raise_fast_exact_difference(
    current_time,
    path,
    legacy_value,
    fast_value,
):
    raise AssertionError(
        "FAST_EXACT_AA mismatch at "
        f"time={current_time:.9f}, location={path}: "
        f"legacy={legacy_value!r}, fast={fast_value!r}"
    )


def _compare_fast_exact_value(
    current_time,
    path,
    legacy_value,
    fast_value,
):
    if isinstance(legacy_value, dict) and isinstance(fast_value, dict):
        legacy_keys = set(legacy_value)
        fast_keys = set(fast_value)
        if legacy_keys != fast_keys:
            _raise_fast_exact_difference(
                current_time,
                f"{path}.keys",
                sorted(legacy_keys, key=repr),
                sorted(fast_keys, key=repr),
            )
        for key in sorted(legacy_keys, key=repr):
            _compare_fast_exact_value(
                current_time,
                f"{path}[{key!r}]",
                legacy_value[key],
                fast_value[key],
            )
        return

    if (
        isinstance(legacy_value, (tuple, list))
        and isinstance(fast_value, (tuple, list))
    ):
        if len(legacy_value) != len(fast_value):
            _raise_fast_exact_difference(
                current_time,
                f"{path}.length",
                len(legacy_value),
                len(fast_value),
            )
        for index, (legacy_item, fast_item) in enumerate(
            zip(legacy_value, fast_value)
        ):
            _compare_fast_exact_value(
                current_time,
                f"{path}[{index}]",
                legacy_item,
                fast_item,
            )
        return

    if legacy_value != fast_value:
        _raise_fast_exact_difference(
            current_time,
            path,
            legacy_value,
            fast_value,
        )


def _compare_fast_exact_snapshots(legacy, fast):
    current_time = float(fast.get("time", legacy.get("time", 0.0)))
    for field in (
        "time",
        "accepted_moves",
        "nodes",
        "resource_queues",
        "resource_queue_sources",
        "transit_queue",
        "batches",
        "total_evacuated",
        "completed_routes",
    ):
        _compare_fast_exact_value(
            current_time,
            field,
            legacy[field],
            fast[field],
        )

    legacy_costs = legacy["prediction_costs"]
    fast_costs = fast["prediction_costs"]
    if set(legacy_costs) != set(fast_costs):
        _raise_fast_exact_difference(
            current_time,
            "prediction_costs.batch_ids",
            sorted(legacy_costs, key=repr),
            sorted(fast_costs, key=repr),
        )
    for batch_id in sorted(legacy_costs, key=repr):
        legacy_values = legacy_costs[batch_id]
        fast_values = fast_costs[batch_id]
        if len(legacy_values) != len(fast_values):
            _raise_fast_exact_difference(
                current_time,
                f"batch[{batch_id!r}].prediction_costs.length",
                len(legacy_values),
                len(fast_values),
            )
        for index, (legacy_value, fast_value) in enumerate(
            zip(legacy_values, fast_values)
        ):
            if abs(float(legacy_value) - float(fast_value)) > 1e-9:
                _raise_fast_exact_difference(
                    current_time,
                    (
                        f"batch[{batch_id!r}]"
                        f".prediction_costs[{index}]"
                    ),
                    legacy_value,
                    fast_value,
                )


def verify_fast_exact_aa():
    """Run one automatic 120-second Mode 4 legacy-vs-fast equivalence check."""
    import algorithm_comparison as comparison

    python_random_state = random.getstate()
    numpy_random_state = np.random.get_state()
    previous_mode = comparison.MODE
    legacy_snapshots = []

    try:
        comparison.MODE = 4
        random.seed(0)
        np.random.seed(0)
        base_graph = build_graph()
        base_graph.graph["density_dependent_flow"] = True
        base_graph.graph["spillback_enabled"] = True
        base_graph.graph["aa_reroute_gain_min"] = 0.20
        base_graph.graph["split_l2_train_source_groups_by_zone"] = True
        population, total_people = comparison.build_population()
        if total_people != 17905:
            raise AssertionError(
                "Mode 4 verification population mismatch: "
                f"expected 17905, got {total_people}"
            )

        def run_variant(fast_exact, observer):
            random.seed(0)
            np.random.seed(0)
            graph = copy.deepcopy(base_graph)
            graph.graph["_fast_exact_aa_override"] = bool(fast_exact)
            graph.graph["_track_executed_routes"] = True
            graph.graph["_aa_equivalence_observer"] = observer
            init_people(
                graph,
                population,
                apply_noise=False,
                rng=random.Random(0),
            )
            targets = _infer_target_by_line_from_graph_state(graph)
            return _run_simulation_for_metrics_core(
                graph,
                OUR_SINGLE_PATH_METHOD,
                targets,
                stop_at_time=120.0,
                collect_detailed_series=False,
            )

        def collect_legacy(
            graph,
            current_time,
            scheduled_moves,
            total_evacuated,
        ):
            legacy_snapshots.append(
                _fast_exact_step_snapshot(
                    graph,
                    current_time,
                    scheduled_moves,
                    total_evacuated,
                )
            )

        fast_step = 0

        def compare_fast(
            graph,
            current_time,
            scheduled_moves,
            total_evacuated,
        ):
            nonlocal fast_step
            if fast_step >= len(legacy_snapshots):
                _raise_fast_exact_difference(
                    current_time,
                    "step_count",
                    len(legacy_snapshots),
                    fast_step + 1,
                )
            fast_snapshot = _fast_exact_step_snapshot(
                graph,
                current_time,
                scheduled_moves,
                total_evacuated,
            )
            _compare_fast_exact_snapshots(
                legacy_snapshots[fast_step],
                fast_snapshot,
            )
            fast_step += 1

        legacy_metrics = run_variant(False, collect_legacy)
        fast_metrics = run_variant(True, compare_fast)
        if fast_step != len(legacy_snapshots):
            _raise_fast_exact_difference(
                float(fast_metrics.get("time", 120.0)),
                "step_count",
                len(legacy_snapshots),
                fast_step,
            )

        fast_diagnostics = fast_metrics.get("aa_diagnostics", {})
        if (
            int(
                fast_diagnostics.get(
                    "predicted_queue_fallback_linear_scan_count",
                    0,
                )
            )
            != 0
        ):
            raise AssertionError(
                "FAST_EXACT_AA used a resource-queue linear fallback"
            )
        if (
            int(
                fast_diagnostics.get(
                    "spatial_fallback_linear_scan_count",
                    0,
                )
            )
            != 0
        ):
            raise AssertionError(
                "FAST_EXACT_AA used a spatial linear fallback"
            )

        print(
            "verify_fast_exact_aa passed: "
            f"{fast_step} steps, Mode 4, 120.0 seconds"
        )
        return {
            "passed": True,
            "steps": fast_step,
            "legacy_metrics": legacy_metrics,
            "fast_metrics": fast_metrics,
        }
    finally:
        comparison.MODE = previous_mode
        random.setstate(python_random_state)
        np.random.set_state(numpy_random_state)


def run_simulation_for_metrics(
    G_base,
    pop_dict,
    method=OUR_SINGLE_PATH_METHOD,
    apply_noise=False,
    rng=None,
    collect_detailed_series=COLLECT_DETAILED_SERIES_DEFAULT,
    metric_sample_interval_seconds=METRIC_SAMPLE_INTERVAL_SECONDS,
):
    G = copy.deepcopy(G_base)
    init_people(G, pop_dict, apply_noise, rng)
    source_group_totals = _source_group_totals_from_graph(G)
    if apply_noise:
        noise_rng = rng if rng is not None else random.Random()
        apply_capacity_noise(G, noise_rng, 0.95, 1.05)
    target_by_line = {
        line: sum(d.values())
        for line, d in pop_dict.items()
        if sum(d.values()) > 0
    }
    metrics = _run_simulation_for_metrics_core(
        G,
        method,
        target_by_line,
        collect_detailed_series=collect_detailed_series,
        metric_sample_interval_seconds=metric_sample_interval_seconds,
    )
    metrics["source_group_totals"] = source_group_totals
    return metrics


def run_simulation_for_metrics_timed(
    G_base,
    pop_dict,
    method=OUR_SINGLE_PATH_METHOD,
    apply_noise=False,
    rng=None,
    collect_detailed_series=COLLECT_DETAILED_SERIES_DEFAULT,
    metric_sample_interval_seconds=METRIC_SAMPLE_INTERVAL_SECONDS,
):
    start_ts = time.perf_counter()
    metrics = run_simulation_for_metrics(
        G_base,
        pop_dict,
        method=method,
        apply_noise=apply_noise,
        rng=rng,
        collect_detailed_series=collect_detailed_series,
        metric_sample_interval_seconds=metric_sample_interval_seconds,
    )
    metrics["wall_clock_runtime_s"] = time.perf_counter() - start_ts
    return metrics


def build_exit_source_group_rows(metrics, method_label=None):
    source_group_totals = metrics.get("source_group_totals", {})
    exit_usage_by_source_group = metrics.get("exit_usage_by_source_group", {})
    rows = []

    for source_group_id, configured_people in source_group_totals.items():
        line_id, source_type, source_zone = _parse_source_group_id(source_group_id)
        evacuated_people = sum(
            float(group_map.get(source_group_id, 0.0))
            for group_map in exit_usage_by_source_group.values()
        )
        denom = evacuated_people if evacuated_people > 0 else float(configured_people)

        for exit_name, group_map in exit_usage_by_source_group.items():
            people = float(group_map.get(source_group_id, 0.0))
            if people <= 0:
                continue
            rows.append({
                "method_label": method_label or "",
                "source_group": source_group_id,
                "line": line_id,
                "source_type": source_type,
                "source_zone": source_zone,
                "configured_people": float(configured_people),
                "evacuated_people": float(evacuated_people),
                "exit_name": exit_name,
                "people": people,
                "share_within_group": people / max(denom, 1.0),
            })

    order = {"platform_waiting": 0, "hall_people": 1, "transfer_people": 2, "train_1": 3, "train_2": 4}
    rows.sort(
        key=lambda row: (
            row["method_label"],
            row["line"],
            order.get(row["source_type"], 99),
            row.get("source_zone", ""),
            row["exit_name"],
        )
    )
    return rows


def run_simulation_for_existing_state(G_state, method=OUR_SINGLE_PATH_METHOD, target_by_line=None):
    G = copy.deepcopy(G_state)
    targets = target_by_line if target_by_line is not None else _infer_target_by_line_from_graph_state(G)
    return _run_simulation_for_metrics_core(G, method, targets)


def _build_fixed_next_by_node(G, path=None, method=PAPER_SINGLE_PATH_METHOD):
    fixed_next = {}

    if isinstance(path, dict):
        for fixed_path in path.values():
            if not fixed_path:
                continue
            for u, v in zip(fixed_path, fixed_path[1:]):
                if G.has_edge(u, v):
                    fixed_next[u] = v
    elif path:
        for u, v in zip(path, path[1:]):
            if G.has_edge(u, v):
                fixed_next[u] = v

    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(G, weight="length"))
    active_sources = [
        n for n in G.nodes()
        if G.nodes[n].get("type") != "exit" and float(G.nodes[n].get("people", 0.0)) > 0.1
    ]
    for source in active_sources:
        if source in fixed_next:
            continue
        source_path = get_best_path_to_exit(G, source, method, shortest_dists)
        if not source_path:
            continue
        for u, v in zip(source_path, source_path[1:]):
            if G.has_edge(u, v):
                fixed_next[u] = v
    return fixed_next


def _recover_fixed_path(G, source, max_steps=None):
    fixed_next = G.graph.get("_fixed_next_by_node") or {}
    if source not in fixed_next:
        return None
    max_steps = max_steps or max(len(G.nodes), 1)
    path = [source]
    visited = {source}
    current = source
    for _ in range(max_steps):
        nxt = fixed_next.get(current)
        if not nxt or not G.has_edge(current, nxt):
            break
        path.append(nxt)
        if G.nodes[nxt].get("type") == "exit":
            return path
        if nxt in visited:
            break
        visited.add(nxt)
        current = nxt
    return path if len(path) > 1 else None


def run_simulation_for_fixed_path_state(G_state, path, method=PAPER_SINGLE_PATH_METHOD, target_by_line=None):
    """按一条预先规划好的固定路径推进，用于静态路径基准测试。"""
    G = copy.deepcopy(G_state)
    targets = target_by_line if target_by_line is not None else _infer_target_by_line_from_graph_state(G)
    G.graph["_fixed_next_by_node"] = _build_fixed_next_by_node(G, path=path, method=method)
    return _run_simulation_for_metrics_core(G, method, targets)


def _reset_graph_people_state(G):
    for node in G.nodes():
        G.nodes[node]["people"] = 0
        G.nodes[node]["people_dict"] = {line: 0 for line in ALL_LINE_IDS}
        G.nodes[node]["source_group_dict"] = {}
        G.nodes[node].pop("_service_arrival_rate_ema", None)
    G.graph["_sim_time"] = 0.0
    G.graph["_transit_queue"] = []
    G.graph.pop("_l7_hall_decision_diagnostics", None)
    G.graph.pop("_l7_hall_common_decision_summary", None)
    G.graph["_transit_queue_version"] = 0
    G.graph["_resource_flow_credit"] = {}
    G.graph["_edge_flow_credit"] = G.graph["_resource_flow_credit"]
    G.graph["_resource_queues"] = {}
    G.graph["_resource_queue_sources"] = {}
    G.graph.pop("_paper_high_cost_signature", None)
    G.graph.pop("_paper_high_cost_active_edges", None)
    G.graph.pop("_paper_high_cost_control_densities", None)
    G.graph.pop("_paper_high_cost_normal_costs", None)
    G.graph.pop("_paper_high_cost_recovery_times", None)
    G.graph.pop("_improved_temporary_high_cost_diagnostics", None)
    G.graph.pop("_improved_temporary_high_cost_trace", None)
    G.graph.pop(
        "_improved_temporary_high_cost_step_diagnostics", None
    )
    G.graph.pop("_dyn_weight_step", None)
    G.graph.pop("_paper_path_by_node", None)
    G.graph.pop("_paper_fixed_next_by_node", None)
    G.graph.pop("_paper_gate_density_log_state", None)
    G.graph.pop("_our_guidance_state", None)


def build_single_path_case_state(
    G_base,
    case_spec,
    evacuees=SINGLE_PATH_CASE_POPULATION,
    use_waiting_zones=None,
):
    G = copy.deepcopy(G_base)
    _reset_graph_people_state(G)

    origin = case_spec["origin"]
    line_id = case_spec["line"]
    G.graph["_single_path_case_line"] = line_id
    if origin not in G.nodes:
        raise ValueError(f"Single-path case origin {origin} not found in graph.")

    should_use_waiting_zones = use_waiting_zones
    if should_use_waiting_zones is None:
        should_use_waiting_zones = (
            origin == f"Platform_{line_id}"
            and bool(_platform_waiting_zone_defs(line_id))
            and bool(_platform_waiting_zone_nodes(G, line_id))
        )

    if should_use_waiting_zones:
        _add_people_to_nodes_by_weights(
            G,
            _platform_waiting_zone_nodes(G, line_id),
            line_id,
            int(round(float(evacuees))),
            _platform_waiting_zone_area_weights(_platform_waiting_zone_defs(line_id)),
        )
    else:
        assigned = int(round(float(evacuees)))
        G.nodes[origin]["people"] = assigned
        G.nodes[origin]["people_dict"][line_id] = assigned
    _apply_obstacle_areas(G)
    return G


def build_distributed_platform_case_state(G_base, line_id, evacuees, area_weights=None):
    G = copy.deepcopy(G_base)
    _reset_graph_people_state(G)
    G.graph["_single_path_case_line"] = line_id

    waiting_zone_defs = _platform_waiting_zone_defs(line_id)
    waiting_zone_nodes = _platform_waiting_zone_nodes(G, line_id)
    if not waiting_zone_defs or not waiting_zone_nodes:
        raise ValueError(f"Line {line_id} has no configured platform waiting zones.")

    if area_weights is None:
        area_weights = _platform_waiting_zone_area_weights(waiting_zone_defs)
    elif len(area_weights) != len(waiting_zone_nodes):
        raise ValueError(
            f"Expected {len(waiting_zone_nodes)} area weights for line {line_id}, got {len(area_weights)}."
        )

    _add_people_to_nodes_by_weights(
        G,
        waiting_zone_nodes,
        line_id,
        int(round(float(evacuees))),
        area_weights,
    )
    _apply_obstacle_areas(G)
    return G


def _apply_obstacle_areas(G):
    """把配置文件里的障碍物面积写入图属性。"""
    nodes_cfg = OBSTACLE_AREAS.get("nodes", {})
    for line_id, node_map in nodes_cfg.items():
        if not isinstance(node_map, dict):
            continue
        for node_name, obstacle_area in node_map.items():
            if node_name in G.nodes:
                G.nodes[node_name]["obstacle_area"] = float(obstacle_area)
                G.nodes[node_name]["obstacle_line"] = line_id

    edges_cfg = OBSTACLE_AREAS.get("edges", {})
    for line_id, edge_map in edges_cfg.items():
        if not isinstance(edge_map, dict):
            continue
        for edge_name, obstacle_area in edge_map.items():
            if "->" not in edge_name:
                continue
            u, v = [part.strip() for part in edge_name.split("->", 1)]
            if G.has_edge(u, v):
                G[u][v]["obstacle_area"] = float(obstacle_area)
                G[u][v]["obstacle_line"] = line_id


def _path_total_length(G, path):
    if not path or len(path) <= 1:
        return 0.0
    return sum(float(G[path[i]][path[i + 1]].get("length", 0.0)) for i in range(len(path) - 1))


def run_single_path_case_suite(
    G_base,
    case_specs=None,
    evacuees=SINGLE_PATH_CASE_POPULATION,
    methods=(PAPER_SINGLE_PATH_METHOD, OUR_SINGLE_PATH_METHOD),
    long_csv="15_single_path_case_results.csv",
    wide_csv="16_single_path_case_comparison.csv",
    summary_csv="17_single_path_case_summary.csv",
    plot_file="18_single_path_case_metrics.png",
):
    """Run the reusable two-method single-path benchmark suite."""
    case_specs = case_specs or SINGLE_PATH_CASE_SPECS
    long_rows = []

    for case_spec in case_specs:
        case_state = build_single_path_case_state(G_base, case_spec, evacuees=evacuees)
        shortest_dists = dict(nx.all_pairs_dijkstra_path_length(case_state, weight="length"))

        for method in methods:
            metrics = run_simulation_for_existing_state(
                case_state,
                method=method,
                target_by_line={case_spec["line"]: float(evacuees)},
            )
            path = get_best_path_to_exit(case_state, case_spec["origin"], method, shortest_dists)
            long_rows.append(
                {
                    "case_id": case_spec["case_id"],
                    "line": case_spec["line"],
                    "origin": case_spec["origin"],
                    "start_role": case_spec["start_role"],
                    "evacuees": float(evacuees),
                    "method": _normalize_method(method),
                    "method_label": _method_display_name(method),
                    "target_exit": path[-1] if path else None,
                    "path": format_path(path),
                    "path_length": _path_total_length(case_state, path),
                    "T100_seconds": metrics["time"],
                    "cumulative_stationary_person_seconds": metrics.get(
                        "stationary_person_seconds", metrics["queueing_time"]
                    ),
                    "effective_evacuation_speed_m_per_s": metrics["effective_evacuation_speed"],
                    "moving_average_speed_m_per_s": metrics["moving_average_speed"],
                }
            )

    long_df = pd.DataFrame(long_rows)
    long_df.to_csv(long_csv, index=False, encoding="utf-8-sig")
    wide_df = long_df.pivot_table(
        index=["case_id", "line", "origin", "start_role", "evacuees"],
        columns="method",
        values=[
            "target_exit",
            "path",
            "path_length",
            "T100_seconds",
            "cumulative_stationary_person_seconds",
            "effective_evacuation_speed_m_per_s",
            "moving_average_speed_m_per_s",
        ],
        aggfunc="first",
    ).sort_index()
    wide_df.columns = [f"{metric}_{method}" for metric, method in wide_df.columns]
    wide_df = wide_df.reset_index()
    wide_df.to_csv(wide_csv, index=False, encoding="utf-8-sig")

    summary_df = long_df.groupby(["line", "method", "method_label"]).agg(
        case_count=("case_id", "count"),
        mean_path_length=("path_length", "mean"),
        mean_T100_seconds=("T100_seconds", "mean"),
        mean_cumulative_stationary_person_seconds=("cumulative_stationary_person_seconds", "mean"),
        mean_effective_evacuation_speed_m_per_s=("effective_evacuation_speed_m_per_s", "mean"),
        mean_moving_average_speed_m_per_s=("moving_average_speed_m_per_s", "mean"),
    ).reset_index()
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    method_order = [_normalize_method(method) for method in methods]
    case_order = [spec["case_id"] for spec in case_specs]
    pivots = [
        (long_df.pivot(index="case_id", columns="method", values="T100_seconds").reindex(case_order), "T100 (s)"),
        (long_df.pivot(index="case_id", columns="method", values="cumulative_stationary_person_seconds").reindex(case_order), "Stationary time (person*s)"),
        (long_df.pivot(index="case_id", columns="method", values="effective_evacuation_speed_m_per_s").reindex(case_order), "Effective evacuation speed (m/s)"),
    ]
    fig, axes = plt.subplots(3, 1, figsize=(14, 13), sharex=True)
    x = np.arange(len(case_order))
    width = min(0.35, 0.8 / max(len(method_order), 1))
    colors = ["#4E79A7", "#E15759"]
    for plot_idx, ((pivot_df, ylabel), ax) in enumerate(zip(pivots, axes)):
        for method_idx, method in enumerate(method_order):
            offset = (method_idx - (len(method_order) - 1) / 2.0) * width
            ax.bar(
                x + offset,
                pivot_df[method].to_numpy(dtype=float),
                width=width,
                color=colors[method_idx % len(colors)],
                edgecolor="black",
                label=_method_display_name(method),
            )
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        if plot_idx == 0:
            ax.legend()
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(case_order, rotation=25, ha="right")
    fig.suptitle(
        f"Single-Path Benchmark ({int(evacuees)} evacuees per case)",
        fontsize=16,
        fontweight="bold",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(plot_file, dpi=300, bbox_inches="tight")
    plt.close()
    return long_df, wide_df, summary_df


def plot_detailed_dynamics_by_line(G_base, metrics_baseline, metrics_guided, pop_dict):
    """方案A：按文献口径画等待区队列与关键设施旅行时间。"""
    lines = [l for l, d in pop_dict.items() if sum(d.values()) > 0]
    if not lines: return

    # ==== 1. 各线路等待区队列长度 + 占用率 ====
    fig, axes = plt.subplots(math.ceil(len(lines) / 2), 2, figsize=(16, 5 * math.ceil(len(lines) / 2)))
    fig.suptitle('各线路等待区队列长度与占用率动态演化对比', fontsize=20, fontweight='bold', y=0.95)
    axes = np.atleast_1d(axes).flatten()

    for idx, line in enumerate(lines):
        ax = axes[idx]
        times_baseline, q_baseline, nodes_baseline = _aggregate_line_node_series(
            G_base, metrics_baseline, line, "queue", normalize_by_area=False
        )
        times_guided, q_guided, _ = _aggregate_line_node_series(
            G_base, metrics_guided, line, "queue", normalize_by_area=False
        )
        _, occ_baseline, _ = _aggregate_line_node_series(G_base, metrics_baseline, line, "queue", normalize_by_area=True)
        _, occ_guided, _ = _aggregate_line_node_series(G_base, metrics_guided, line, "queue", normalize_by_area=True)

        q_baseline = _smooth_display_series(q_baseline, window=5)
        q_guided = _smooth_display_series(q_guided, window=5)
        occ_baseline = _smooth_display_series(occ_baseline, window=5)
        occ_guided = _smooth_display_series(occ_guided, window=5)

        ax2 = ax.twinx()
        ax.plot(times_baseline, q_baseline, 'r-', linewidth=2.2, label="ImprovedAStar 队列长度", alpha=0.85)
        ax.plot(times_guided, q_guided, 'g-', linewidth=2.2, label="AdaptiveQueueAwareAStar 队列长度")
        ax2.plot(times_baseline, occ_baseline, 'r--', linewidth=1.8, label="ImprovedAStar 占用率", alpha=0.65)
        ax2.plot(times_guided, occ_guided, 'g--', linewidth=1.8, label="AdaptiveQueueAwareAStar 占用率")

        node_hint = ", ".join(nodes_baseline[:3]) if nodes_baseline else "no-queue-node"
        ax.set_title(f'{line} 等待区排队\n[{node_hint}]', fontsize=13, fontweight='bold')
        ax.set_xlabel('时间 (s)')
        ax.set_ylabel('队列长度 (人)')
        ax2.set_ylabel('等待区占用率 / 设施负载率')
        ax.grid(True, linestyle=":", alpha=0.7)

        handles1, labels1 = ax.get_legend_handles_labels()
        handles2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(handles1 + handles2, labels1 + labels2, loc="upper right", fontsize=9)

    # 隐藏多余的子图
    for idx in range(len(lines), len(axes)): fig.delaxes(axes[idx])
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(_output_path("03_System_Line_Queue_Dynamics.png"), dpi=300, bbox_inches='tight')
    plt.close()

    # ==== 2. 各线路关键设施实际旅行时间 ====
    fig, axes = plt.subplots(math.ceil(len(lines) / 2), 2, figsize=(16, 5 * math.ceil(len(lines) / 2)))
    fig.suptitle('各线路关键设施实际旅行时间动态演化对比', fontsize=20, fontweight='bold', y=0.95)
    axes = np.atleast_1d(axes).flatten()

    for idx, line in enumerate(lines):
        ax = axes[idx]
        times_baseline, travel_baseline, nodes_baseline = _aggregate_line_node_series(
            G_base, metrics_baseline, line, "travel_time", normalize_by_area=False
        )
        times_guided, travel_guided, _ = _aggregate_line_node_series(
            G_base, metrics_guided, line, "travel_time", normalize_by_area=False
        )
        travel_baseline = _smooth_display_series(travel_baseline, window=5)
        travel_guided = _smooth_display_series(travel_guided, window=5)

        node_hint = ", ".join(nodes_baseline[:3]) if nodes_baseline else "no-queue-node"

        ax.plot(times_baseline, travel_baseline, 'r-', linewidth=2.5, label="ImprovedAStar", alpha=0.85)
        ax.plot(times_guided, travel_guided, 'b-', linewidth=2.8, label="AdaptiveQueueAwareAStar")

        ax.set_title(f'{line} 关键设施旅行时间\n[{node_hint}]', fontsize=13, fontweight='bold')
        ax.set_xlabel('时间 (s)')
        ax.set_ylabel('实际旅行时间 (s)')
        ax.grid(True, linestyle=":", alpha=0.7)
        ax.legend()

    for idx in range(len(lines), len(axes)): fig.delaxes(axes[idx])
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(_output_path("04_System_Line_Speed_Dynamics.png"), dpi=300, bbox_inches='tight')
    plt.close()


def get_evacuation_mode():
    print("\n" + "=" * 60)
    print("🚇 欢迎使用龙阳路站高精度客流仿真控制台")
    print("=" * 60)
    print("请选择客流加载模式：\n")
    print("  [1] 常规突发 (仅原有人员：站台 + 站厅 + 换乘)")
    print("  [2] 单向迫停 - 上行 (仅上行 Train 1 满载开门 + 原有人员)")
    print("  [3] 单向迫停 - 下行 (仅下行 Train 2 满载开门 + 原有人员)")
    print("  [4] 极限地狱 - 双向满载 (上下行列车同时开门 + 原有人员)")
    print("-" * 60)
    while True:
        choice = input("👉 请输入序号 [1 / 2 / 3 / 4] 并按回车: ").strip()
        if choice in ['1', '2', '3', '4']:
            return int(choice)
        print("❌ 输入无效，请重新输入！")



def run_system_mode_workflow(G):
    mode = get_evacuation_mode()
    G.graph["density_dependent_flow"] = True
    G.graph["spillback_enabled"] = True
    STATION_BASE_LOADS = {
        "L2": {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
        "L7": {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
        "L16": {"platform_waiting": 42, "hall_people": 15, "transfer_people": 27},
        "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
        "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
    }

    current_pop_dict, total_p = {}, 0
    for line, physics in TRAIN_PHYSICS.items():
        base = STATION_BASE_LOADS[line]
        train_total = int(round(_train_total_people(physics)))

        if mode == 1:
            t1, t2 = 0, 0
        elif mode == 2:
            t1, t2 = train_total, 0
        elif mode == 3:
            t1, t2 = 0, train_total
        else:
            t1, t2 = train_total, train_total

        pw = int(base["platform_waiting"])
        hp = int(base["hall_people"])
        tp = int(base["transfer_people"])

        current_pop_dict[line] = {"train_1": t1, "train_2": t2, "platform_waiting": pw, "hall_people": hp, "transfer_people": tp}
        total_p += (t1 + t2 + pw + hp + tp)

    output_dir, scenario_label = _set_system_mode_output_dir(mode)
    write_configuration_validation_report(
        G, os.path.join(output_dir, "configuration_validation_report.md")
    )
    write_resource_mapping_report(
        G, os.path.join(output_dir, "resource_mapping_report.md")
    )
    print("==== Scenario output: {} -> {}".format(scenario_label, output_dir))
    plot_initial_topology(G)
    print("\n==== 目标客流: {} 人 ====".format(total_p))

    metrics_paper = run_simulation_for_metrics_timed(
        G,
        current_pop_dict,
        method=PAPER_SINGLE_PATH_METHOD,
    )

    aa_graph = copy.deepcopy(G)
    print("==== AA routing: AdaptiveQueueAwareAStar (time-dependent predictive)")
    metrics_guided = run_simulation_for_metrics_timed(
        aa_graph,
        current_pop_dict,
        method=OUR_SINGLE_PATH_METHOD,
    )

    def print_completion_summary(label, metrics):
        evacuation_time = float(metrics.get("time", 0.0))
        target_people = float(total_p)
        remaining_people = float(metrics.get("remaining_people", target_people))
        evacuated_people = target_people - remaining_people
        cumulative_stationary = float(
            metrics.get("stationary_person_seconds", metrics.get("queueing_time", 0.0))
        )
        t95 = 0.0
        curve = metrics.get("evacuation_curve", {})
        target_remaining = target_people * 0.05
        for curve_time, remaining in zip(
            curve.get("times", []), curve.get("remaining", [])
        ):
            if remaining <= target_remaining + 0.5:
                t95 = float(curve_time)
                break
        print(
            f"algorithm={label} target_people={target_people:.0f} "
            f"evacuated_people={evacuated_people:.0f} remaining_people={remaining_people:.0f} "
            f"completed={metrics.get('completed', False)} "
            f"termination_reason={metrics.get('termination_reason', 'unknown')} "
            f"T95_seconds={t95:.1f} T100_seconds={evacuation_time:.1f} "
            f"cumulative_stationary_person_seconds={cumulative_stationary:.1f} "
            f"mean_stationary_time_seconds_per_person={cumulative_stationary / target_people if target_people > 0 else 0.0:.6f} "
            f"effective_evacuation_speed_m_per_s={metrics.get('effective_evacuation_speed', 0.0):.6f} "
            f"wall_clock_runtime_seconds={metrics.get('wall_clock_runtime_s', 0.0):.2f}"
        )

    print_completion_summary("ImprovedAStar", metrics_paper)
    print_completion_summary("AdaptiveQueueAwareAStar", metrics_guided)

    for label, metrics in (
        ("Improved", metrics_paper),
        ("AA", metrics_guided),
    ):
        pd.DataFrame(metrics.get("bottleneck_resources", [])).to_csv(
            os.path.join(output_dir, f"bottleneck_resources_{label}.csv"),
            index=False,
            encoding="utf-8-sig",
        )
        pd.DataFrame(metrics.get("spatial_bottlenecks", [])).to_csv(
            os.path.join(output_dir, f"spatial_bottlenecks_{label}.csv"),
            index=False,
            encoding="utf-8-sig",
        )

    method_metrics = [
        ("ImprovedAStar", metrics_paper),
        ("AdaptiveQueueAwareAStar", metrics_guided),
    ]
    summary_rows = []
    active_lines = [line for line, vals in current_pop_dict.items() if sum(vals.values()) > 0]
    for label, met in method_metrics:
        curve = met.get("evacuation_curve", {})
        t95 = 0.0
        for curve_time, remaining in zip(
            curve.get("times", []), curve.get("remaining", [])
        ):
            if remaining <= total_p * 0.05 + 0.5:
                t95 = float(curve_time)
                break
        summary_rows.append({
            "scenario_mode": mode, "scenario_label": scenario_label, "total_people": total_p,
            "method": label,
            "target_people": total_p,
            "evacuated_people": total_p - met.get("remaining_people", 0.0),
            "remaining_people": met.get("remaining_people", 0.0),
            "completed": met.get("completed", False),
            "termination_reason": met.get("termination_reason", "unknown"),
            "T95_seconds": t95,
            "T100_seconds": met["time"],
            "cumulative_stationary_person_seconds": met.get(
                "stationary_person_seconds", met["queueing_time"]
            ),
            "mean_stationary_time_seconds_per_person": met.get(
                "mean_stationary_time", 0.0
            ),
            "effective_evacuation_speed_m_per_s": met.get("effective_evacuation_speed", 0.0),
            "mean_total_evacuation_time_seconds_per_person": met.get("mean_total_evacuation_time", 0.0),
            "mean_station_throughput_people_per_second": (
                (total_p - met.get("remaining_people", 0.0)) / met["time"]
                if met["time"] > 0 else 0.0
            ),
            "moving_average_speed_m_per_s": met.get("moving_average_speed", met.get("avg_speed", 0.0)),
            "edge_traversal_average_speed_m_per_s": met.get("edge_traversal_average_speed", 0.0),
            "mean_moving_time_seconds_per_person": met.get("mean_moving_time", 0.0),
            "total_movement_distance_m": met.get("total_movement_distance", 0.0),
            "exit_load_jain_index": met.get("exit_load_jain_index", 0.0),
            "key_facility_load_jain_index": met.get("key_facility_load_jain_index", 0.0),
            "wall_clock_runtime_seconds": met.get("wall_clock_runtime_s"),
            "aa_astar_call_count": met.get("aa_astar_call_count", 0),
            "aa_old_path_evaluation_count": met.get("aa_old_path_evaluation_count", 0),
            "aa_same_path_reuse_count": met.get("aa_same_path_reuse_count", 0),
            "aa_astar_cutoff_no_improvement_count": met.get("aa_astar_cutoff_no_improvement_count", 0),
            "aa_safety_weight": met.get("aa_safety_weight", 0.0),
            "aa_cumulative_predicted_risk_time": met.get("aa_cumulative_predicted_risk_time", 0.0),
            "aa_average_predicted_density_risk": met.get("aa_average_predicted_density_risk", 0.0),
            "aa_predicted_density_above_3_count": met.get("aa_predicted_density_above_3_count", 0),
            "aa_predicted_density_above_3_5_count": met.get("aa_predicted_density_above_3_5_count", 0),
            "aa_skipped_jam_density_edges": met.get("aa_skipped_jam_density_edges", 0),
        })
    pd.DataFrame(summary_rows).to_csv(_output_path("02_system_method_summary.csv"), index=False, encoding="utf-8-sig")
    line_rows = []
    for label, met in method_metrics:
        line_events = {}
        for event in met.get("evacuation_arrival_events", []):
            source_group = str(event.get("source_group", ""))
            line_id, _, _ = _parse_source_group_id(source_group)
            amount = max(float(event.get("amount", 0.0)), 0.0)
            if line_id in active_lines and amount > 0.0:
                line_events.setdefault(line_id, []).append(
                    (float(event.get("time", 0.0)), amount)
                )
        for line in active_lines:
            events = sorted(line_events.get(line, []))
            line_t95 = None
            if events:
                threshold = 0.95 * sum(amount for _, amount in events)
                cumulative = 0.0
                for event_time, amount in events:
                    cumulative += amount
                    if cumulative + 1e-9 >= threshold:
                        line_t95 = event_time
                        break
            line_rows.append({
                "scenario_mode": mode, "scenario_label": scenario_label, "total_people": total_p,
                "method": label, "line": line,
                "T95_seconds": line_t95,
                "clearance_time_seconds": met["clearance_times_by_line"].get(line) if met["clearance_times_by_line"].get(line) is not None else met["time"],
                "is_last_clearance_line": False,
            })
        method_rows = [row for row in line_rows if row["method"] == label]
        if method_rows:
            max(method_rows, key=lambda row: row["clearance_time_seconds"])[
                "is_last_clearance_line"
            ] = True
    pd.DataFrame(line_rows).to_csv(_output_path("03_system_line_summary.csv"), index=False, encoding="utf-8-sig")
    exit_rows = []
    exit_line_rows = []
    for label, met in method_metrics:
        for exit_name, people in met.get("exit_usage", {}).items():
            exit_rows.append({
                "scenario_mode": mode,
                "scenario_label": scenario_label,
                "method": label,
                "exit": exit_name,
                "people": float(people),
            })
        for exit_name, line_map in met.get("exit_usage_by_line", {}).items():
            for line, people in line_map.items():
                exit_line_rows.append({
                    "scenario_mode": mode,
                    "scenario_label": scenario_label,
                    "method": label,
                    "exit": exit_name,
                    "source_line": line,
                    "people": float(people),
                })
    pd.DataFrame(exit_rows).to_csv(
        _output_path("04_system_exit_summary.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(exit_line_rows).to_csv(
        _output_path("04_system_exit_by_line.csv"),
        index=False,
        encoding="utf-8-sig",
    )
    plot_system_evacuation_curve(method_metrics, total_p)
    plot_charts_multi(G, method_metrics, total_p)
    plot_line_specific_analysis_multi(method_metrics, current_pop_dict)
    print("\nDone.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    G = build_graph()
    run_system_mode_workflow(G)
