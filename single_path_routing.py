"""
Single-path routing algorithms for metro station evacuation.

Implements two A*-based path planning methods unified under a time-cost framework:

  PaperImprovedAStar  — Meng et al. (2022) baseline: g(n) = α·l + β·(l/v)
                         where v follows the Fruin density-speed curve.
  AdaptiveQueueAwareAStar — Our method: g(n) = travel_time + waiting_time
                         with predicted congestion state and exit-aware h(n).

All edge costs are expressed in seconds to preserve physical interpretability.
"""

import math
import heapq
import hashlib
import time
from bisect import bisect_right
from pathlib import Path

import networkx as nx


# Bound by the shared simulation engine. These callbacks let AA
# evaluate the same travel time and effective edge flow rate that the shared
# simulation engine will actually execute, without copying physical rules into
# this routing-policy module.
_AA_PHYSICAL_EDGE_TRAVEL_TIME = None
_AA_PHYSICAL_EDGE_FLOW_CAPACITY = None
_AA_EDGE_RESOURCE_ID = None
_AA_RESOURCE_CAPACITY = None
_AA_PREDICTED_SPATIAL_WAIT = None
_AA_PREDICTED_SPATIAL_DENSITY = None

# AA-only, per-simulation-step routing commitments.  These are integer first-hop
# movements predicted from the same edge credit and receiving space that the
# shared executor will apply later in the step.  They are never written into
# node occupancy and therefore cannot alter the common physical layer.


def bind_physical_callbacks(
    edge_travel_time_fn=None,
    edge_flow_capacity_fn=None,
    edge_resource_id_fn=None,
    resource_capacity_fn=None,
    predicted_spatial_wait_fn=None,
    predicted_spatial_density_fn=None,
    gate_service_backlog_fn=None,
):
    """Bind shared-physics callbacks used by AA cost prediction."""
    global _AA_PHYSICAL_EDGE_TRAVEL_TIME
    global _AA_PHYSICAL_EDGE_FLOW_CAPACITY
    global _AA_EDGE_RESOURCE_ID
    global _AA_RESOURCE_CAPACITY
    global _AA_PREDICTED_SPATIAL_WAIT
    global _AA_PREDICTED_SPATIAL_DENSITY
    if edge_travel_time_fn is not None:
        _AA_PHYSICAL_EDGE_TRAVEL_TIME = edge_travel_time_fn
    if edge_flow_capacity_fn is not None:
        _AA_PHYSICAL_EDGE_FLOW_CAPACITY = edge_flow_capacity_fn
    if edge_resource_id_fn is not None:
        _AA_EDGE_RESOURCE_ID = edge_resource_id_fn
    if resource_capacity_fn is not None:
        _AA_RESOURCE_CAPACITY = resource_capacity_fn
    if predicted_spatial_wait_fn is not None:
        _AA_PREDICTED_SPATIAL_WAIT = predicted_spatial_wait_fn
    if predicted_spatial_density_fn is not None:
        _AA_PREDICTED_SPATIAL_DENSITY = predicted_spatial_density_fn
    # Kept as a compatibility hook for older callers; gate backlog is now a
    # diagnostics concept and is not used by AA routing cost.
    _ = gate_service_backlog_fn

# ═══════════════════════════════════════════════════════════════════════════════
# Method identifiers
# ═══════════════════════════════════════════════════════════════════════════════

PAPER_SINGLE_PATH_METHOD = "PaperImprovedAStar"
OUR_SINGLE_PATH_METHOD = "AdaptiveQueueAwareAStar"
LEGACY_INERTIA_ABLATION_METHOD = OUR_SINGLE_PATH_METHOD
OUR_SPLIT_GUIDANCE_METHOD = "OurSplitGuidance"
DENSITY_ONLY_ASTAR_METHOD = "DensityOnlyAStar"
CURRENT_QUEUE_AWARE_ASTAR_METHOD = "CurrentQueueAwareAStar"
MESOSCOPIC_PHYSICAL_TIME_METHOD = "MesoscopicPhysicalTimeAStar"
MESOSCOPIC_CURRENT_QUEUE_METHOD = "MesoscopicCurrentQueueAwareAStar"
EXPERIMENTAL_MESOSCOPIC_PREDICTIVE_METHOD = (
    "ExperimentalMesoscopicPredictiveQueueAwareAStar"
)
OUR_NO_WAITING_TIME_METHOD = DENSITY_ONLY_ASTAR_METHOD

METHOD_ALIASES = {
    "ClassicImproved": PAPER_SINGLE_PATH_METHOD,
    "OurSinglePath": OUR_SINGLE_PATH_METHOD,
    "NoWaitingTime": DENSITY_ONLY_ASTAR_METHOD,
}

# ═══════════════════════════════════════════════════════════════════════════════
# Physical constants — Fruin speed model (Meng et al. 2022, Eq. 5-9)
# ═══════════════════════════════════════════════════════════════════════════════

PAPER_FREE_SPEED = 1.427          # m/s,  free-flow walking speed (Fruin)
PAPER_DENSITY_FREE = 0.2          # p/m^2, threshold below which speed = free
PAPER_DENSITY_JAM = 4.0           # p/m^2, jam density (speed → 0)
PAPER_DENSITY_SLOPE = 0.3549      # speed reduction per unit density (Fruin)
PAPER_HIGH_DENSITY_THRESHOLD = 3.0
# A density-blocked edge is removed from the Improved A* candidate graph.
# Keep the legacy name as an alias because diagnostics and older callers use it.
PAPER_BLOCKED_EDGE_COST = float("inf")
PAPER_TEMPORARY_HIGH_COST = PAPER_BLOCKED_EDGE_COST
AA_SAFETY_WEIGHT_DEFAULT = 1.0
AA_SEARCH_MODE_DEFAULT = "multilabel"
AA_MULTILABEL_COMPARE_SAMPLE_RATE_DEFAULT = 0.01
ARRIVAL_TIME_EPS = 1e-9
EPS = 1e-9
PAPER_LENGTH_ALPHA = 0.15         # length weight in g(n)  (Meng et al. Eq. 4)
PAPER_SPEED_BETA = 0.85           # speed  weight in g(n)  (Meng et al. Eq. 4)
PAPER_HEURISTIC_GAMMA = 0.10      # heuristic weight in h(n) (Meng et al. Eq. 10)

# Facility speed limits (station adaptation of Meng et al.'s cruise-ship model)
PAPER_FACILITY_SPEED_LIMITS = {
    "flat": PAPER_FREE_SPEED,
    "stair": 0.75,
    "escalator": 0.50,
}

# ═══════════════════════════════════════════════════════════════════════════════
# LegacyInertiaAblation parameters. Formal mesoscopic algorithms do not read
# this fixed-K candidate limit or any node-level inertia thresholds.
# ═══════════════════════════════════════════════════════════════════════════════

K_CANDIDATE_PATHS = 3

OUR_PREDICTIVE_FAMILY = {
    OUR_SINGLE_PATH_METHOD,
    DENSITY_ONLY_ASTAR_METHOD,
    CURRENT_QUEUE_AWARE_ASTAR_METHOD,
}

# ═══════════════════════════════════════════════════════════════════════════════
# Method resolution
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_method(method):
    return METHOD_ALIASES.get(method, method)


def routing_base_method(method):
    method = normalize_method(method)
    if method in OUR_PREDICTIVE_FAMILY:
        return OUR_SINGLE_PATH_METHOD
    return method


def uses_dynamic_a_star(method):
    return routing_base_method(method) in {PAPER_SINGLE_PATH_METHOD, OUR_SINGLE_PATH_METHOD}


def uses_predictive_family(method):
    return normalize_method(method) in OUR_PREDICTIVE_FAMILY


def uses_predictive_single_path(method):
    """Backward-compat alias."""
    return uses_predictive_family(method)


# ═══════════════════════════════════════════════════════════════════════════════
# Heuristic h(n)
# ═══════════════════════════════════════════════════════════════════════════════

def heuristic_cost(u, v, d_dict, method):
    """h(n): estimated remaining cost from u to exit v.

    Paper baseline:  h = gamma * shortest_distance       (Meng et al. Eq. 10)
    Our method:      h = dist / v_free                  (free-flow lower bound, admissible)
    """
    method = normalize_method(method)
    base_method = routing_base_method(method)
    dist = float(d_dict.get(u, {}).get(v, 0.0))

    if base_method == PAPER_SINGLE_PATH_METHOD:
        return PAPER_HEURISTIC_GAMMA * dist

    if base_method == OUR_SINGLE_PATH_METHOD:
        return dist / PAPER_FREE_SPEED

    return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Network queries
# ═══════════════════════════════════════════════════════════════════════════════

def allowed_exit_nodes(G):
    case_line = G.graph.get("_single_path_case_line")
    exits = [n for n, data in G.nodes(data=True) if data.get("type") == "exit"]
    if not case_line:
        return exits
    line_tag = f"_{case_line}_"
    filtered = [n for n in exits if line_tag in n]
    return filtered or exits


def node_out_capacity(G, node):
    total = 0.0
    for succ in G.successors(node):
        total += float(G[node][succ].get("capacity", 0.0))
    return max(total, 0.001)


def is_capacity_service_node(G, node):
    if node not in G.nodes:
        return False
    node_type = str(G.nodes[node].get("type", "")).lower()
    return (
        node_type in {"stair", "escalator"}
        or node_type.startswith("gate")
        or "gate" in node_type
    )


def node_service_capacity(G, node):
    if node not in G.nodes:
        return 0.001
    capacity = float(G.nodes[node].get("capacity", 0.0) or 0.0)
    if not math.isfinite(capacity) or capacity <= 0:
        capacity = node_out_capacity(G, node)
    return max(capacity, 0.001)


def edge_resource_id(G, u, v):
    """Return the shared physical resource consumed by ``u -> v``."""
    if callable(_AA_EDGE_RESOURCE_ID):
        return _AA_EDGE_RESOURCE_ID(G, u, v)
    if is_capacity_service_node(G, v):
        return ("facility", v)
    return ("edge", u, v)


def resource_capacity_per_second(G, resource_id):
    """Return the shared engine's capacity for one resource."""
    if callable(_AA_RESOURCE_CAPACITY):
        return max(float(_AA_RESOURCE_CAPACITY(G, resource_id)), 0.0)
    if resource_id[0] == "facility":
        return node_service_capacity(G, resource_id[1])
    _, u, v = resource_id
    return max(float(G[u][v].get("capacity", 0.0)), 0.0)


def aa_current_batch_gate_service_time(G, resource_id, amount):
    """Return the current batch's mean service-time contribution.

    The legacy AA objective uses ``Q / mu + m / (2 * mu)`` for capacity
    facilities. Ordinary movement edges do not receive this batch service
    term.
    """
    if not resource_id or resource_id[0] != "facility":
        return 0.0

    amount = max(float(amount), 0.0)
    if amount <= 0.0:
        return 0.0

    service_rate = resource_capacity_per_second(G, resource_id)
    if service_rate <= 0.0:
        return float("inf")
    return amount / (2.0 * service_rate)


def physical_resource_queue(G, resource_id):
    """Current queue waiting for the physical resource capacity."""
    return max(
        float(G.graph.get("_resource_queues", {}).get(resource_id, 0.0)),
        0.0,
    )


def current_resource_queue(G, resource_id):
    """Physical resource queue plus this routing round's reassignment."""
    physical = physical_resource_queue(G, resource_id)
    adjustment = float(
        G.graph.get("_aa_round_queue_adjustment", {}).get(resource_id, 0.0)
    )
    return max(physical + adjustment, 0.0)


class _MaxPlusEventNode:
    """Treap node augmented with an exact chronological max-plus transform."""

    __slots__ = (
        "time",
        "amount",
        "priority",
        "left",
        "right",
        "summary",
        "total_amount",
    )

    def __init__(self, event_time, amount, priority):
        self.time = float(event_time)
        self.amount = int(amount)
        self.priority = int(priority)
        self.left = None
        self.right = None
        amount_float = float(self.amount)
        self.summary = (
            self.time,
            self.time,
            amount_float,
            amount_float,
        )
        self.total_amount = self.amount


def _max_plus_compose(p_first, b_first, p_second, b_second):
    """Return ``second(first(q))`` for transforms max(q + p, b)."""
    return (
        p_first + p_second,
        max(b_first + p_second, b_second),
    )


def _combine_event_summaries(first, second, service_rate):
    """Combine two non-overlapping chronological event summaries."""
    if first is None:
        return second
    if second is None:
        return first

    first_time, first_last, first_p, first_b = first
    second_time, second_last, second_p, second_b = second
    gap = max(float(second_time) - float(first_last), 0.0)
    combined_p, combined_b = _max_plus_compose(
        first_p,
        first_b,
        -float(service_rate) * gap,
        0.0,
    )
    combined_p, combined_b = _max_plus_compose(
        combined_p,
        combined_b,
        second_p,
        second_b,
    )
    return (
        first_time,
        second_last,
        combined_p,
        combined_b,
    )


def _update_event_node(node, service_rate):
    if node is None:
        return
    own_amount = float(node.amount)
    own_summary = (
        node.time,
        node.time,
        own_amount,
        own_amount,
    )
    summary = _combine_event_summaries(
        node.left.summary if node.left is not None else None,
        own_summary,
        service_rate,
    )
    node.summary = _combine_event_summaries(
        summary,
        node.right.summary if node.right is not None else None,
        service_rate,
    )
    node.total_amount = (
        int(node.amount)
        + (node.left.total_amount if node.left is not None else 0)
        + (node.right.total_amount if node.right is not None else 0)
    )


def _rotate_event_left(node, service_rate):
    promoted = node.right
    node.right = promoted.left
    promoted.left = node
    _update_event_node(node, service_rate)
    _update_event_node(promoted, service_rate)
    return promoted


def _rotate_event_right(node, service_rate):
    promoted = node.left
    node.left = promoted.right
    promoted.right = node
    _update_event_node(node, service_rate)
    _update_event_node(promoted, service_rate)
    return promoted


def _merge_event_treaps(left, right, service_rate):
    if left is None:
        return right
    if right is None:
        return left
    if left.priority <= right.priority:
        left.right = _merge_event_treaps(
            left.right,
            right,
            service_rate,
        )
        _update_event_node(left, service_rate)
        return left
    right.left = _merge_event_treaps(
        left,
        right.left,
        service_rate,
    )
    _update_event_node(right, service_rate)
    return right


def _change_event_treap(
    node,
    event_time,
    delta,
    priority,
    service_rate,
):
    if node is None:
        if delta <= 0:
            return None
        return _MaxPlusEventNode(event_time, delta, priority)

    if event_time < node.time:
        node.left = _change_event_treap(
            node.left,
            event_time,
            delta,
            priority,
            service_rate,
        )
        if (
            node.left is not None
            and node.left.priority < node.priority
        ):
            node = _rotate_event_right(node, service_rate)
    elif event_time > node.time:
        node.right = _change_event_treap(
            node.right,
            event_time,
            delta,
            priority,
            service_rate,
        )
        if (
            node.right is not None
            and node.right.priority < node.priority
        ):
            node = _rotate_event_left(node, service_rate)
    else:
        node.amount += int(delta)
        if node.amount <= 0:
            return _merge_event_treaps(
                node.left,
                node.right,
                service_rate,
            )

    _update_event_node(node, service_rate)
    return node


def _event_prefix_summary(node, target_time, service_rate):
    """Return the transform for all events at or before target_time."""
    if node is None:
        return None
    if node.time > target_time:
        return _event_prefix_summary(
            node.left,
            target_time,
            service_rate,
        )

    prefix = node.left.summary if node.left is not None else None
    own_amount = float(node.amount)
    prefix = _combine_event_summaries(
        prefix,
        (
            node.time,
            node.time,
            own_amount,
            own_amount,
        ),
        service_rate,
    )
    return _combine_event_summaries(
        prefix,
        _event_prefix_summary(
            node.right,
            target_time,
            service_rate,
        ),
        service_rate,
    )


def _event_prefix_amount(node, target_time):
    if node is None:
        return 0
    if node.time > target_time:
        return _event_prefix_amount(node.left, target_time)
    return (
        (node.left.total_amount if node.left is not None else 0)
        + int(node.amount)
        + _event_prefix_amount(node.right, target_time)
    )


def _next_event_priority(index):
    """Deterministic SplitMix64 priority for expected O(log n) treap depth."""
    sequence = int(index.get("sequence", 0)) + 1
    index["sequence"] = sequence
    value = (sequence + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return value ^ (value >> 31)


def _new_resource_event_index(G, resource_id):
    return {
        "resource_id": resource_id,
        "service_rate": resource_capacity_per_second(G, resource_id),
        "root": None,
        "event_version": 0,
        "sequence": 0,
        "query_cache": {},
    }


def _change_resource_event(index, event_time, delta):
    delta = int(delta)
    if delta == 0:
        return
    index["root"] = _change_event_treap(
        index.get("root"),
        float(event_time),
        delta,
        _next_event_priority(index),
        float(index["service_rate"]),
    )
    index["event_version"] = int(index.get("event_version", 0)) + 1
    index["query_cache"].clear()


def _build_resource_event_indices(G):
    current_time = float(G.graph.get("_sim_time", 0.0))
    transit_version = int(G.graph.get("_transit_queue_version", 0))
    cache_key = (current_time, transit_version)
    cache = G.graph.get("_aa_resource_event_indices_cache")
    if cache is not None and cache.get("key") == cache_key:
        return cache

    aggregated = {}
    for item in G.graph.get("_transit_queue", []):
        pending_resource = item.get("confirmed_arrival_resource_id")
        if (
            pending_resource is None
            and not item.get("service_capacity_consumed", False)
        ):
            pending_resource = item.get("resource_id")
            if pending_resource is None:
                destination = item.get("dest", item.get("v"))
                if (
                    destination is not None
                    and is_capacity_service_node(G, destination)
                ):
                    pending_resource = ("facility", destination)
        amount = max(int(item.get("amount", 0)), 0)
        if pending_resource is None or amount <= 0:
            continue
        event_time = max(
            float(item.get("arrive_time", current_time)),
            current_time,
        )
        resource_events = aggregated.setdefault(pending_resource, {})
        resource_events[event_time] = (
            resource_events.get(event_time, 0) + amount
        )

    for item in G.graph.get("_aa_round_prediction_events", []):
        resource_id = item.get("resource_id")
        amount = max(int(item.get("amount", 0)), 0)
        if resource_id is None or amount <= 0:
            continue
        event_time = max(
            float(item.get("predicted_arrival_time", current_time)),
            current_time,
        )
        resource_events = aggregated.setdefault(resource_id, {})
        resource_events[event_time] = (
            resource_events.get(event_time, 0) + amount
        )

    indices = {}
    for resource_id, resource_events in aggregated.items():
        index = _new_resource_event_index(G, resource_id)
        for event_time, amount in sorted(resource_events.items()):
            _change_resource_event(index, event_time, amount)
        indices[resource_id] = index

    cache = {
        "key": cache_key,
        "indices": indices,
    }
    G.graph["_aa_resource_event_indices_cache"] = cache
    return cache


def _resource_event_index(G, resource_id):
    cache = _build_resource_event_indices(G)
    indices = cache["indices"]
    index = indices.get(resource_id)
    if index is None:
        index = _new_resource_event_index(G, resource_id)
        indices[resource_id] = index
    return index


def insert_resource_prediction_event(
    G,
    resource_id,
    event_time,
    amount,
):
    """Insert a soft event into an already-materialized exact index."""
    cache = G.graph.get("_aa_resource_event_indices_cache")
    if cache is None:
        return
    expected_key = (
        float(G.graph.get("_sim_time", 0.0)),
        int(G.graph.get("_transit_queue_version", 0)),
    )
    if cache.get("key") != expected_key:
        G.graph.pop("_aa_resource_event_indices_cache", None)
        return
    index = cache["indices"].get(resource_id)
    if index is None:
        index = _new_resource_event_index(G, resource_id)
        cache["indices"][resource_id] = index
    _change_resource_event(
        index,
        max(float(event_time), expected_key[0]),
        int(amount),
    )


def note_queue_adjustment_changed(G, resource_id):
    versions = G.graph.setdefault(
        "_aa_queue_adjustment_versions",
        {},
    )
    versions[resource_id] = int(versions.get(resource_id, 0)) + 1
    cache = G.graph.get("_aa_resource_event_indices_cache")
    if cache is not None:
        index = cache.get("indices", {}).get(resource_id)
        if index is not None:
            index["query_cache"].clear()


def anticipated_demand(G, resource_id, target_time):
    """Reserved interface for uncertain upstream demand; intentionally unused."""
    return 0


def confirmed_arrivals_by_resource(G):
    """Return cached integer arrivals that have not consumed their resource.

    Normal executor records consume their entrance resource before transit and
    therefore carry ``service_capacity_consumed=True``. They are occupants in
    service, not future waiting customers, and must not be counted twice.
    An explicit ``confirmed_arrival_resource_id`` may be used by a future
    multi-stage executor when service genuinely remains pending.
    """
    current_time = float(G.graph.get("_sim_time", 0.0))
    cache = G.graph.get("_confirmed_resource_arrivals_cache")
    transit_queue = G.graph.get("_transit_queue", [])
    cache_key = (
        current_time,
        len(transit_queue),
    )
    if not cache or cache.get("key") != cache_key:
        events_by_resource = {}
        for item in transit_queue:
            pending_resource = item.get("confirmed_arrival_resource_id")
            if pending_resource is None and not item.get("service_capacity_consumed", False):
                pending_resource = item.get("resource_id")
                if pending_resource is None:
                    destination = item.get("dest", item.get("v"))
                    if destination is not None and is_capacity_service_node(G, destination):
                        pending_resource = ("facility", destination)
            if pending_resource is None:
                continue
            amount = int(item.get("amount", 0))
            if amount <= 0:
                continue
            event_time = max(float(item.get("arrive_time", current_time)), current_time)
            events_by_resource.setdefault(pending_resource, []).append((event_time, amount))
        for item in G.graph.get("_aa_round_prediction_events", []):
            resource_id = item.get("resource_id")
            amount = max(int(item.get("amount", 0)), 0)
            if resource_id is None or amount <= 0:
                continue
            event_time = max(
                float(item.get("predicted_arrival_time", current_time)), current_time
            )
            events_by_resource.setdefault(resource_id, []).append((event_time, amount))
        times_by_resource = {}

        for resource_id, resource_events in events_by_resource.items():
            resource_events.sort(key=lambda event: event[0])
            times_by_resource[resource_id] = [
                event_time
                for event_time, _ in resource_events
            ]

        cache = {
            "key": cache_key,
            "events_by_resource": events_by_resource,
            "times_by_resource": times_by_resource,
        }
        G.graph["_confirmed_resource_arrivals_cache"] = cache
    return cache["events_by_resource"]


def confirmed_arrival_events(G, resource_id, target_time):
    events_by_resource = confirmed_arrivals_by_resource(G)
    cache = G.graph.get("_confirmed_resource_arrivals_cache", {})

    events = events_by_resource.get(resource_id, ())
    times = cache.get("times_by_resource", {}).get(resource_id, ())

    end = bisect_right(
        times,
        float(target_time) + 1e-9,
    )

    return events[:end]


def _predicted_resource_queue_at_time_linear(G, resource_id, target_time):
    """Advance current waiting intent through exact confirmed arrival events."""
    current_time = float(G.graph.get("_sim_time", 0.0))
    target_time = max(float(target_time), current_time)
    queue = current_resource_queue(G, resource_id)
    events_by_resource = confirmed_arrivals_by_resource(G)
    cache = G.graph.get(
        "_confirmed_resource_arrivals_cache",
        {},
    )

    events = events_by_resource.get(resource_id, ())
    times = cache.get(
        "times_by_resource",
        {},
    ).get(resource_id, ())

    end = bisect_right(
        times,
        float(target_time) + 1e-9,
    )

    if queue <= 0.0 and end <= 0:
        return 0.0

    service_rate = resource_capacity_per_second(G, resource_id)
    if service_rate <= 0.0:
        return float("inf")

    previous_time = current_time
    for index in range(end):
        event_time, amount = events[index]
        event_time = min(max(float(event_time), previous_time), target_time)
        queue = max(queue - service_rate * (event_time - previous_time), 0.0)
        queue += int(amount)
        previous_time = event_time
    return max(queue - service_rate * (target_time - previous_time), 0.0)


def _predicted_resource_queue_at_time_indexed(
    G,
    resource_id,
    target_time,
):
    current_time = float(G.graph.get("_sim_time", 0.0))
    target_time = max(float(target_time), current_time)
    queue = current_resource_queue(G, resource_id)
    index = _resource_event_index(G, resource_id)
    service_rate = float(index["service_rate"])
    if service_rate <= 0.0:
        return float("inf")

    adjustment_version = int(
        G.graph.get(
            "_aa_queue_adjustment_versions",
            {},
        ).get(resource_id, 0)
    )
    cache_key = (
        resource_id,
        target_time,
        int(index.get("event_version", 0)),
        adjustment_version,
        current_time,
        queue,
    )
    query_cache = index["query_cache"]
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    summary = _event_prefix_summary(
        index.get("root"),
        target_time,
        service_rate,
    )
    if summary is None:
        result = max(
            queue - service_rate * (target_time - current_time),
            0.0,
        )
    else:
        first_time, last_time, transform_p, transform_b = summary
        result = max(
            queue - service_rate * max(first_time - current_time, 0.0),
            0.0,
        )
        result = max(result + transform_p, transform_b)
        result = max(
            result - service_rate * max(target_time - last_time, 0.0),
            0.0,
        )

    # Preserve the legacy +1e-9 event-inclusion boundary exactly. Events just
    # after target_time are clamped to target_time by the old implementation.
    root = index.get("root")
    near_amount = (
        _event_prefix_amount(root, target_time + 1e-9)
        - _event_prefix_amount(root, target_time)
    )
    if near_amount:
        result += near_amount

    query_cache[cache_key] = result
    return result


def predicted_resource_queue_at_time(G, resource_id, target_time):
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    diagnostics["predicted_queue_query_count"] = (
        int(diagnostics.get("predicted_queue_query_count", 0)) + 1
    )
    if bool(G.graph.get("_fast_exact_aa", True)):
        diagnostics["predicted_queue_index_query_count"] = (
            int(diagnostics.get("predicted_queue_index_query_count", 0)) + 1
        )
        return _predicted_resource_queue_at_time_indexed(
            G,
            resource_id,
            target_time,
        )

    diagnostics["predicted_queue_fallback_linear_scan_count"] = (
        int(
            diagnostics.get(
                "predicted_queue_fallback_linear_scan_count",
                0,
            )
        )
        + 1
    )
    return _predicted_resource_queue_at_time_linear(
        G,
        resource_id,
        target_time,
    )


def aa_planning_resource_queue(G, resource_id, target_time, predictive=True):
    """Resource queue used by AA planning, with explicit ablation switches.

    The switches affect route evaluation only. They never alter the common
    physical queue, service capacity, receiving limit, or spillback executor.
    """
    if not bool(G.graph.get("aa_resource_wait_enabled", True)):
        return 0.0
    if (
        not predictive
        or not bool(G.graph.get("aa_resource_queue_prediction_enabled", True))
    ):
        return current_resource_queue(G, resource_id)
    return predicted_resource_queue_at_time(G, resource_id, target_time)


def predicted_service_queue(G, node, travel_time, current_queue=None):
    """Backward-compatible facility wrapper around event-time prediction."""
    resource_id = ("facility", node)
    if current_queue is not None:
        queues = G.graph.setdefault("_resource_queues", {})
        sentinel = object()
        previous = queues.get(resource_id, sentinel)
        queues[resource_id] = max(float(current_queue), 0.0)
        try:
            return predicted_resource_queue_at_time(
                G,
                resource_id,
                float(G.graph.get("_sim_time", 0.0)) + max(float(travel_time), 0.0),
            )
        finally:
            if previous is sentinel:
                queues.pop(resource_id, None)
            else:
                queues[resource_id] = previous
    return predicted_resource_queue_at_time(
        G,
        resource_id,
        float(G.graph.get("_sim_time", 0.0)) + max(float(travel_time), 0.0),
    )


def spatial_effective_density(G, node, obstacle_area=0.0):
    if node not in G.nodes:
        return 0.0
    data = G.nodes[node]
    storage_mode = str(
        G.graph.get("service_node_spatial_storage_mode", "exempt")
    ).lower()
    finite_gate_storage = (
        storage_mode in {"queue_area", "finite_gate_buffer"}
        and is_capacity_service_node(G, node)
        and node in G.graph.get("gate_queue_area_nodes", {})
        and G.graph.get("gate_queue_area_nodes", {}).get(node) in G.nodes
    )
    legacy_service_storage = (
        str(G.graph.get("service_node_spatial_storage_mode", "exempt")).lower() == "legacy"
        and is_capacity_service_node(G, node)
    )
    if not finite_gate_storage and not legacy_service_storage and (
        data.get("density_exempt", False)
        or not data.get("spatial_storage_enabled", True)
    ):
        return 0.0
    area_node = (
        G.graph.get("gate_queue_area_nodes", {}).get(node)
        if finite_gate_storage
        else node
    )
    area_data = G.nodes[area_node]
    area = max(float(area_data.get("area", 1.0)), 0.1)
    obstacle_area = min(max(float(obstacle_area), 0.0), max(area - 0.1, 0.0))
    effective_area = max(area - obstacle_area, 0.1)
    people_at_node = float(data.get("people", 0.0))
    return people_at_node / effective_area


def node_congestion_index(G, node, obstacle_area=0.0):
    if is_capacity_service_node(G, node):
        return current_resource_queue(G, ("facility", node)), "resource_queue"
    return spatial_effective_density(G, node, obstacle_area), "density"


def edge_runtime_density(G, u, v):
    if not G.has_edge(u, v):
        return 0.0
    density = float(G[u][v].get("runtime_density", 0.0) or 0.0)
    if not math.isfinite(density):
        return 0.0
    return max(density, 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Edge geometry helpers
# ═══════════════════════════════════════════════════════════════════════════════

def density_risk_level(density):
    density = max(float(density), 0.0)

    if density <= 3.0:
        return 0.0

    if density <= 3.5:
        return (density - 3.0) / 0.5

    if density < PAPER_DENSITY_JAM:
        return 1.0 + (density - 3.5) / (
            PAPER_DENSITY_JAM - 3.5
        )

    return float("inf")


def predicted_spatial_density(G, node, eta, amount=0):
    if callable(_AA_PREDICTED_SPATIAL_DENSITY):
        return max(
            float(
                _AA_PREDICTED_SPATIAL_DENSITY(
                    G,
                    node,
                    eta,
                    amount,
                )
            ),
            0.0,
        )

    return spatial_effective_density(G, node)


def aa_safety_weight(G):
    return max(
        float(
            G.graph.get(
                "aa_safety_weight",
                AA_SAFETY_WEIGHT_DEFAULT,
            )
        ),
        0.0,
    )


def _record_density_risk_detail(G, detail):
    stats = G.graph.setdefault("_aa_density_risk_stats", {})
    risk_increment = float(detail.get("risk_increment", 0.0))
    segment_time = float(detail.get("physical_segment_time", 0.0))
    source_density = float(detail.get("source_predicted_density", 0.0))
    destination_density = float(detail.get("destination_predicted_density", 0.0))
    edge_density = float(detail.get("edge_density", 0.0))

    stats["cumulative_predicted_risk_time"] = (
        float(stats.get("cumulative_predicted_risk_time", 0.0)) + risk_increment
    )
    stats["predicted_risk_segment_time"] = (
        float(stats.get("predicted_risk_segment_time", 0.0)) + segment_time
    )
    stats["predicted_risk_segment_count"] = (
        int(stats.get("predicted_risk_segment_count", 0)) + 1
    )
    if max(source_density, destination_density, edge_density) > 3.0:
        stats["predicted_density_above_3_count"] = (
            int(stats.get("predicted_density_above_3_count", 0)) + 1
        )
    if max(source_density, destination_density, edge_density) > 3.5:
        stats["predicted_density_above_3_5_count"] = (
            int(stats.get("predicted_density_above_3_5_count", 0)) + 1
        )
    if source_density > 3.0 or destination_density > 3.0:
        stats["predicted_planning_node_moderate_risk_time"] = (
            float(stats.get("predicted_planning_node_moderate_risk_time", 0.0))
            + segment_time
        )
    if edge_density > 3.0:
        stats["predicted_planning_edge_moderate_risk_time"] = (
            float(stats.get("predicted_planning_edge_moderate_risk_time", 0.0))
            + segment_time
        )
    if source_density > 3.5 or destination_density > 3.5:
        stats["predicted_planning_node_severe_risk_time"] = (
            float(stats.get("predicted_planning_node_severe_risk_time", 0.0))
            + segment_time
        )
    if edge_density > 3.5:
        stats["predicted_planning_edge_severe_risk_time"] = (
            float(stats.get("predicted_planning_edge_severe_risk_time", 0.0))
            + segment_time
        )


def record_density_risk_details(G, details):
    for detail in details or ():
        _record_density_risk_detail(G, detail)


def aa_density_risk_summary(G):
    stats = dict(G.graph.get("_aa_density_risk_stats", {}))
    segment_time = float(stats.get("predicted_risk_segment_time", 0.0))
    cumulative_risk = float(stats.get("cumulative_predicted_risk_time", 0.0))
    stats["aa_safety_weight"] = aa_safety_weight(G)
    stats["average_predicted_density_risk"] = (
        cumulative_risk / segment_time if segment_time > 0.0 else 0.0
    )
    stats.setdefault("cumulative_predicted_risk_time", 0.0)
    stats.setdefault("predicted_density_above_3_count", 0)
    stats.setdefault("predicted_density_above_3_5_count", 0)
    stats.setdefault("skipped_jam_density_edges", 0)
    stats.setdefault("predicted_planning_node_moderate_risk_time", 0.0)
    stats.setdefault("predicted_planning_edge_moderate_risk_time", 0.0)
    stats.setdefault("predicted_planning_node_severe_risk_time", 0.0)
    stats.setdefault("predicted_planning_edge_severe_risk_time", 0.0)
    return stats


def edge_width_proxy(G, u, v):
    data = G[u][v]
    width_limit = data.get("width_limit")
    if width_limit is not None and float(width_limit) > 0:
        return float(width_limit)
    capacity = float(data.get("capacity", 0.0))
    if capacity > 0:
        return max(capacity / (5000.0 / 3600.0), 0.6)
    return 1.0


def paper_edge_area(G, u, v):
    data = G[u][v]
    length = max(float(data.get("length", 0.0)), 0.0)
    width = max(edge_width_proxy(G, u, v), 0.1)
    return max(length * width, 0.1)


def paper_obstacle_area(G, u, v):
    edge_obs = float(G[u][v].get("obstacle_area", 0.0))
    node_obs = float(G.nodes[v].get("obstacle_area", 0.0))
    return max(edge_obs + node_obs, 0.0)


def paper_effective_density(G, u, v):
    """Return only the occupancy density of the edge control volume.

    A queue stored at the downstream node is not physically located on every
    incoming edge.  Service-node delay is represented separately by
    ``predicted_service_queue`` in the AA cost.
    """
    return edge_runtime_density(G, u, v)


# ═══════════════════════════════════════════════════════════════════════════════
# Speed models
# ═══════════════════════════════════════════════════════════════════════════════

def paper_speed_from_density(density):
    """Fruin speed-density model (Meng et al. 2022, Eq. 5-7)."""
    if density <= PAPER_DENSITY_FREE:
        return PAPER_FREE_SPEED
    if density <= PAPER_DENSITY_JAM:
        return max(PAPER_FREE_SPEED - PAPER_DENSITY_SLOPE * density, 0.0)
    return 0.0


def paper_facility_speed_limit(G, u, v):
    edge_type = str(G[u][v].get("edge_type", "")).lower()
    u_type = str(G.nodes[u].get("type", "")).lower()
    v_type = str(G.nodes[v].get("type", "")).lower()
    if "stair" in edge_type or "stair" in u_type or "stair" in v_type:
        return PAPER_FACILITY_SPEED_LIMITS["stair"]
    if "escalator" in edge_type or "escalator" in u_type or "escalator" in v_type:
        return PAPER_FACILITY_SPEED_LIMITS["escalator"]
    return PAPER_FACILITY_SPEED_LIMITS["flat"]


def physical_edge_travel_time(G, u, v):
    """Return the shared engine's realized edge time for routing costs."""
    if callable(_AA_PHYSICAL_EDGE_TRAVEL_TIME):
        travel_time = float(_AA_PHYSICAL_EDGE_TRAVEL_TIME(G, u, v))
        return travel_time if math.isfinite(travel_time) else float("inf")

    # Standalone fallback for small routing-only tests.
    length = max(float(G[u][v].get("length", 0.0)), 0.0)
    density = paper_effective_density(G, u, v)
    walk_speed = min(
        paper_speed_from_density(density),
        paper_facility_speed_limit(G, u, v),
    )
    if walk_speed <= 0.001:
        return float("inf")
    return length / walk_speed


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cost functions — unified time-based framework
# ═══════════════════════════════════════════════════════════════════════════════

def _paper_baseline_travel_time(G, u, v, density):
    """β·t travel-time term for the Improved baseline.

    The formal baseline uses Meng et al.'s density-speed formula. Set
    G.graph['improved_shared_travel_time'] = True only for the shared-travel-
    time attribution variant.
    """
    if G.graph.get("improved_shared_travel_time", False):
        return physical_edge_travel_time(G, u, v)
    length = max(float(G[u][v].get("length", 0.0)), 0.0)
    walk_speed = min(
        paper_speed_from_density(density),
        paper_facility_speed_limit(G, u, v),
    )
    return length / walk_speed if walk_speed > 0.0 else float("inf")


def paper_edge_cost_from_density(
    G,
    u,
    v,
    density,
    *,
    apply_temporary_high_cost=True,
):
    """Return Improved's edge cost for one explicitly supplied density.

    Structure and the 3.0 p/m^2 cutoff follow Meng et al. (2022).  The travel
    time term beta*t uses the paper's own density-speed travel-time formula;
    the shared physical executor is applied later to both methods equally.
    The supplied ``density`` is used for the paper's density-blocking cutoff.
    """
    density = max(float(density), 0.0)
    if (
        apply_temporary_high_cost
        and density > PAPER_HIGH_DENSITY_THRESHOLD
    ):
        return PAPER_BLOCKED_EDGE_COST
    length = float(G[u][v].get("length", 0.0))
    travel_time = _paper_baseline_travel_time(G, u, v, density)
    if not math.isfinite(travel_time):
        return float("inf")
    return PAPER_LENGTH_ALPHA * length + PAPER_SPEED_BETA * travel_time


def paper_edge_cost(G, u, v):
    """Improved A* edge cost (Meng et al. 2022, Eq. 4).

    g_edge = α·l + β·t   where t is the SHARED executor's realized edge time
    (physical_edge_travel_time), not the baseline's own free-flow speed table.
    This keeps the literature cost structure (length penalty + travel time +
    3.0 p/m² cutoff) while removing the optimizer–executor speed mismatch that
    otherwise fell only on the baseline.

    The baseline observes current physical density and does not use AA's
    resource-queue prediction, committed arrivals, or service-rate waiting
    term. The common executor applies the same physical capacities and
    movement rules to both methods.
    """
    length = float(G[u][v].get("length", 0.0))
    density = paper_effective_density(G, u, v)
    if density > PAPER_HIGH_DENSITY_THRESHOLD:
        return PAPER_BLOCKED_EDGE_COST
    travel_time = _paper_baseline_travel_time(G, u, v, density)
    if not math.isfinite(travel_time):
        return float("inf")
    # g = α·l + β·t, with t from the shared physical executor
    return PAPER_LENGTH_ALPHA * length + PAPER_SPEED_BETA * travel_time


def adaptive_edge_cost(G, u, v, method):
    """AdaptiveQueueAwareAStar edge cost — unified time-based framework.

    g_edge = travel_time + waiting_time  (seconds)

    travel_time  = l / v(ρ_now)           ∀ edges
    waiting_time = Q_pred / μ             bottleneck nodes only

    The queue at the expected edge-arrival time is advanced from the current
    queue using only exact movements already committed to the transit queue:
        Q_pred = current queue + committed arrivals - service before arrival

    Variant (for ablation):
      NoWaitingTime — waiting_time = 0  (density-speed only, no bottleneck model)
    """
    method = normalize_method(method)
    if u not in G.nodes or v not in G.nodes or not G.has_edge(u, v):
        return float("inf")

    total_cost, _ = evaluate_candidate_path_with_cumulative_eta(
        G,
        [u, v],
        method,
    )
    return total_cost


def method_uses_waiting(method):
    return normalize_method(method) in {
        CURRENT_QUEUE_AWARE_ASTAR_METHOD,
        OUR_SINGLE_PATH_METHOD,
    }


def mesoscopic_edge_cost(G, u, v, method):
    """Static-at-decision edge cost for the two formal mesoscopic methods."""
    method = normalize_method(method)
    travel_time = physical_edge_travel_time(G, u, v)
    if not math.isfinite(travel_time):
        return float("inf")
    if method == MESOSCOPIC_PHYSICAL_TIME_METHOD:
        return travel_time
    if method != MESOSCOPIC_CURRENT_QUEUE_METHOD:
        raise ValueError(f"Unsupported formal mesoscopic method: {method}")
    resource_id = edge_resource_id(G, u, v)
    queue = current_resource_queue(G, resource_id)
    if queue <= 0:
        return travel_time
    service_rate = resource_capacity_per_second(G, resource_id)
    if service_rate <= 0:
        return float("inf")
    return travel_time + queue / service_rate


def mesoscopic_full_graph_path(G, current_node, method, shortest_dists=None):
    """Search the complete reachable graph; no fixed-K candidate pruning."""
    method = normalize_method(method)
    if method not in {MESOSCOPIC_PHYSICAL_TIME_METHOD, MESOSCOPIC_CURRENT_QUEUE_METHOD}:
        raise ValueError(f"Unsupported formal mesoscopic method: {method}")
    exits = allowed_exit_nodes(G)
    distance_map = shortest_dists or {}
    best = None
    for target in exits:
        try:
            path = nx.astar_path(
                G,
                current_node,
                target,
                heuristic=lambda node, goal: (
                    float(distance_map.get(node, {}).get(goal, 0.0)) / PAPER_FREE_SPEED
                ),
                weight=lambda u, v, data: mesoscopic_edge_cost(G, u, v, method),
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        cost = sum(
            mesoscopic_edge_cost(G, u, v, method)
            for u, v in zip(path, path[1:])
        )
        key = (cost, len(path), tuple(map(str, path)))
        if best is None or key < best[0]:
            best = (key, path)
    return None if best is None else best[1]


def evaluate_candidate_path_with_cumulative_eta(
    G,
    path,
    method,
    current_time=None,
    amount=1,
):
    """Evaluate one AA-family path with a single cumulative time origin.

    Waiting is paid immediately before entering the resource controlled by an
    edge. The ETA of every later resource therefore includes every preceding
    wait and physical traversal. Both retained and newly generated paths call
    this function, so inertia comparisons use exactly the same cost semantics.
    """
    method = normalize_method(method)
    if not path or len(path) <= 1:
        return float("inf"), []

    eta = (
        float(G.graph.get("_sim_time", 0.0))
        if current_time is None else float(current_time)
    )
    total_cost = 0.0
    details = []
    uses_waiting = method_uses_waiting(method)
    resource_queues = G.graph.get("_resource_queues", {})
    confirmed_by_resource = (
        confirmed_arrivals_by_resource(G)
        if method == OUR_SINGLE_PATH_METHOD else {}
    )

    for u, v in zip(path, path[1:]):
        if u not in G.nodes or v not in G.nodes or not G.has_edge(u, v):
            return float("inf"), []

        edge_data = G[u][v]
        resource_id = edge_data.get("_resource_id_cache")
        if resource_id is None:
            resource_id = edge_resource_id(G, u, v)
        predicted_wait = 0.0
        predicted_queue = 0.0
        has_waiting_state = (
            float(resource_queues.get(resource_id, 0.0)) > 0.0
            or resource_id in confirmed_by_resource
        )
        if uses_waiting and has_waiting_state:
            if method == CURRENT_QUEUE_AWARE_ASTAR_METHOD:
                predicted_queue = current_resource_queue(G, resource_id)
            else:
                predicted_queue = aa_planning_resource_queue(
                    G, resource_id, eta, predictive=True
                )
            if not math.isfinite(predicted_queue):
                return float("inf"), []
            if predicted_queue > 0.0:
                service_rate = resource_capacity_per_second(G, resource_id)
                if service_rate <= 0.0:
                    return float("inf"), []
                predicted_wait = max(predicted_queue / service_rate, 0.0)
            max_waits = G.graph.setdefault("_resource_max_predicted_wait", {})
            max_waits[resource_id] = max(
                float(max_waits.get(resource_id, 0.0)),
                predicted_wait,
            )
        batch_gate_service_time = (
            aa_current_batch_gate_service_time(G, resource_id, amount)
            if uses_waiting else 0.0
        )
        if not math.isfinite(batch_gate_service_time):
            return float("inf"), []

        travel_time = physical_edge_travel_time(G, u, v)
        if not math.isfinite(travel_time):
            return float("inf"), []

        resource_entry_time = eta
        eta += predicted_wait + batch_gate_service_time + travel_time
        total_cost += predicted_wait + batch_gate_service_time + travel_time
        details.append({
            "u": u,
            "v": v,
            "resource_id": resource_id,
            "resource_entry_time": resource_entry_time,
            "predicted_queue": predicted_queue,
            "predicted_wait": predicted_wait,
            "current_batch_gate_service_time": batch_gate_service_time,
            "travel_time": travel_time,
            "arrival_time": eta,
        })

    return total_cost, details


def predicted_spatial_wait(G, node, eta, amount=1):
    if callable(_AA_PREDICTED_SPATIAL_WAIT):
        return max(float(_AA_PREDICTED_SPATIAL_WAIT(G, node, eta, amount)), 0.0)
    return 0.0


def aa_planning_spatial_wait(G, node, eta, amount=1):
    """Spatial receiving wait used by AA planning, with an ablation switch."""
    if not bool(G.graph.get("aa_spatial_wait_enabled", True)):
        return 0.0
    return predicted_spatial_wait(G, node, eta, amount)


def skip_duplicate_gate_queue_spatial_wait(G, u, v):
    """Avoid charging the same physical gate queue area twice in AA planning."""
    if not is_capacity_service_node(G, v):
        return False
    queue_node = G.graph.get("gate_queue_area_nodes", {}).get(v)
    return queue_node == u


def spatial_wait_planning_amount(G, amount, resource_rate):
    """Estimate the simultaneous inflow used by AA spatial receiving prediction."""
    amount = max(float(amount), 0.0)
    if amount <= 0.0:
        return 0

    enabled = bool(G.graph.get("aa_spatial_batch_arrival_spread_enabled", False))
    if not enabled:
        return max(int(math.ceil(amount)), 1)

    if not math.isfinite(resource_rate) or resource_rate <= 0.0:
        return max(int(math.ceil(amount)), 1)

    horizon = max(float(G.graph.get("aa_spatial_arrival_spread_seconds", 1.0)), 1.0)
    adjusted = min(amount, max(resource_rate * horizon, 1.0))

    if adjusted + 1e-9 < amount:
        diagnostics = G.graph.setdefault("_aa_diagnostics", {})
        diagnostics["spatial_spread_amount_cap_count"] = (
            int(diagnostics.get("spatial_spread_amount_cap_count", 0)) + 1
        )
        diagnostics["spatial_spread_original_people"] = (
            float(diagnostics.get("spatial_spread_original_people", 0.0)) + amount
        )
        diagnostics["spatial_spread_planning_people"] = (
            float(diagnostics.get("spatial_spread_planning_people", 0.0)) + adjusted
        )

    return max(int(math.ceil(adjusted)), 1)


def ensure_aa_free_flow_exit_lower_bounds(G):
    lower_bounds = G.graph.get(
        "_aa_free_flow_exit_lower_bound"
    )

    if lower_bounds is not None:
        return lower_bounds

    exits = set(allowed_exit_nodes(G))
    distance = {}
    reverse = G.reverse(copy=False)

    for exit_node in exits:
        for node, value in (
            nx.single_source_dijkstra_path_length(
                reverse,
                exit_node,
                weight="length",
            ).items()
        ):
            distance[node] = min(
                distance.get(
                    node,
                    float("inf"),
                ),
                float(value),
            )

    lower_bounds = {
        node: value / PAPER_FREE_SPEED
        for node, value in distance.items()
    }

    G.graph[
        "_aa_free_flow_exit_lower_bound"
    ] = lower_bounds

    return lower_bounds


def aa_free_flow_exit_lower_bound(G, node):
    return float(
        ensure_aa_free_flow_exit_lower_bounds(
            G
        ).get(
            node,
            float("inf"),
        )
    )


def ensure_aa_step_edge_records(G):
    sim_time = float(G.graph.get("_sim_time", 0.0))

    if (
        G.graph.get("_aa_step_edge_records_time")
        == sim_time
    ):
        return G.graph["_aa_step_edge_records"]

    records = {}

    for u, v in G.edges():
        edge_data = G[u][v]

        resource_id = edge_data.get(
            "_resource_id_cache"
        )
        if resource_id is None:
            resource_id = edge_resource_id(G, u, v)
            edge_data["_resource_id_cache"] = resource_id

        travel_time = physical_edge_travel_time(
            G,
            u,
            v,
        )

        edge_density = edge_runtime_density(
            G,
            u,
            v,
        )

        records[(u, v)] = (
            resource_id,
            travel_time,
            edge_density,
            density_risk_level(edge_density),
            resource_capacity_per_second(G, resource_id),
        )

    G.graph["_aa_step_edge_records_time"] = sim_time
    G.graph["_aa_step_edge_records"] = records

    return records


def aa_detail_tuple_to_dict(detail):
    (
        u,
        v,
        resource_id,
        resource_entry_time,
        predicted_queue,
        predicted_wait,
        batch_gate_service_time,
        spatial_wait,
        travel_time,
        arrival_time,
        destination_density,
        source_density,
        edge_density,
        source_risk_level,
        destination_risk_level,
        edge_risk_level,
        segment_risk_level,
        waiting_risk,
        movement_risk,
        risk_increment,
        accumulated_risk,
        physical_segment_time,
        physical_elapsed_time,
        objective_cost,
    ) = detail
    return {
        "u": u,
        "v": v,
        "resource_id": resource_id,
        "resource_entry_time": resource_entry_time,
        "predicted_queue": predicted_queue,
        "predicted_wait": predicted_wait,
        "current_batch_gate_service_time": batch_gate_service_time,
        "spatial_wait": spatial_wait,
        "travel_time": travel_time,
        "arrival_time": arrival_time,
        "predicted_density": destination_density,
        "source_predicted_density": source_density,
        "destination_predicted_density": destination_density,
        "edge_density": edge_density,
        "source_density_risk_level": source_risk_level,
        "destination_density_risk_level": destination_risk_level,
        "edge_density_risk_level": edge_risk_level,
        "density_risk_level": segment_risk_level,
        "waiting_risk_increment": waiting_risk,
        "movement_risk_increment": movement_risk,
        "risk_increment": risk_increment,
        "accumulated_risk": accumulated_risk,
        "physical_segment_time": physical_segment_time,
        "physical_elapsed_time": physical_elapsed_time,
        "objective_cost": objective_cost,
    }


def aa_one_step_objective_lower_bound(
    G,
    start,
    current_time,
    amount,
    predictive=True,
    allowed_successors=None,
    return_successor=False,
):
    start_time = float(
        G.graph.get("_sim_time", 0.0) if current_time is None else current_time
    )
    lower_bounds = ensure_aa_free_flow_exit_lower_bounds(G)
    edge_records = ensure_aa_step_edge_records(G)
    safety_weight = aa_safety_weight(G)

    if predictive:
        source_density = predicted_spatial_density(
            G,
            start,
            start_time,
            amount=0,
        )
        source_risk_level = density_risk_level(source_density)
        if not math.isfinite(source_risk_level):
            source_risk_level = 2.0
    else:
        source_risk_level = 0.0

    allowed = (
        set(allowed_successors)
        if allowed_successors is not None
        else None
    )
    best = float("inf")
    best_successor = None
    for successor in G.successors(start):
        if allowed is not None and successor not in allowed:
            continue
        (
            resource_id,
            travel,
            edge_density,
            edge_risk_level,
            resource_rate,
        ) = edge_records[(start, successor)]
        if not math.isfinite(travel):
            continue

        queue = aa_planning_resource_queue(
            G, resource_id, start_time, predictive=predictive
        )
        if not math.isfinite(queue):
            continue

        wait = 0.0
        if queue > 0:
            if resource_rate <= 0:
                continue
            wait = queue / resource_rate
        batch_gate_service_time = aa_current_batch_gate_service_time(
            G,
            resource_id,
            amount,
        )
        if not math.isfinite(batch_gate_service_time):
            continue

        arrival_without_spatial_wait = (
            start_time + wait + batch_gate_service_time + travel
        )
        if not predictive:
            spatial_wait = 0.0
        elif skip_duplicate_gate_queue_spatial_wait(G, start, successor):
            spatial_wait = 0.0
        else:
            spatial_amount = spatial_wait_planning_amount(G, amount, resource_rate)
            spatial_wait = aa_planning_spatial_wait(
                G,
                successor,
                arrival_without_spatial_wait,
                spatial_amount,
            )
        if not math.isfinite(spatial_wait):
            continue

        segment_time = wait + batch_gate_service_time + travel + spatial_wait
        arrival_time = start_time + segment_time

        if predictive:
            destination_density = predicted_spatial_density(
                G,
                successor,
                arrival_time,
                amount=0,
            )
            destination_risk_level = density_risk_level(destination_density)
            if not math.isfinite(destination_risk_level) or not math.isfinite(edge_risk_level):
                continue
            waiting_risk = source_risk_level * (
                wait + batch_gate_service_time + spatial_wait
            )
            movement_risk = max(
                edge_risk_level,
                destination_risk_level,
            ) * travel
            risk_increment = waiting_risk + movement_risk
        else:
            risk_increment = 0.0

        first_segment_objective = (
            segment_time
            + safety_weight * risk_increment
        )
        candidate = (
            first_segment_objective
            + lower_bounds.get(successor, float("inf"))
        )
        if candidate < best:
            best = candidate
            best_successor = successor

    if return_successor:
        return best, best_successor
    return best


def invalidate_aa_routing_caches(G):
    for key in (
        "_aa_free_flow_exit_lower_bound",
        "_aa_topology_signature",
        "_aa_static_candidate_paths",
        "_aa_step_edge_records",
        "_aa_step_edge_records_time",
    ):
        G.graph.pop(key, None)


def _aa_diag_increment(G, key, amount=1):
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    diagnostics[key] = diagnostics.get(key, 0) + amount
    return diagnostics[key]


def _time_dependent_astar_single_label(
    G,
    start,
    current_time=None,
    amount=1,
    predictive=True,
    objective_cutoff=None,
    target_exits=None,
    edge_allowed=None,
    allow_gate_switch_edges=False,
):
    """Single-label approximation for ETA-dependent generalized costs.

    The physical arrival transition uses elapsed travel and waiting time, while
    the label objective also includes density-risk exposure.  Keeping only the
    lowest-objective label at each node can therefore discard a differently
    timed label with a cheaper continuation.  This implementation is retained
    for ablation and runtime comparison; formal routing defaults to the
    multi-label search below.
    """
    start_time = float(
        G.graph.get("_sim_time", 0.0) if current_time is None else current_time
    )
    cutoff = (
        float(objective_cutoff)
        if objective_cutoff is not None
        else float("inf")
    )
    safety_weight = aa_safety_weight(G)
    edge_records = ensure_aa_step_edge_records(G)
    density_cache = {}

    def cached_predicted_density(node, target_time):
        key = (node, float(target_time))

        if key not in density_cache:
            density_cache[key] = predicted_spatial_density(
                G,
                node,
                target_time,
                amount=0,
            )

        return density_cache[key]

    exits = (
        set(target_exits)
        if target_exits is not None
        else set(allowed_exit_nodes(G))
    )
    exits.intersection_update(G.nodes)
    if start in exits:
        return [start], 0.0, []
    lower_bounds = ensure_aa_free_flow_exit_lower_bounds(G)
    best_objective = {start: 0.0}
    elapsed_time = {start: 0.0}
    accumulated_risk = {start: 0.0}
    predecessor = {}
    detail_for_node = {}
    labels = [(lower_bounds.get(start, 0.0), 0.0, 0.0, str(start), start)]
    target = None
    while labels:
        estimated_total, objective_cost, elapsed, _, node = (
            heapq.heappop(labels)
        )
        if math.isfinite(cutoff) and estimated_total >= cutoff:
            break
        if objective_cost > best_objective.get(node, float("inf")) + 1e-9:
            continue
        if node in exits:
            target = node
            break
        eta = start_time + elapsed
        current_risk = accumulated_risk.get(node, 0.0)
        if predictive:
            source_density = cached_predicted_density(node, eta)
            source_risk_level = density_risk_level(source_density)

            if not math.isfinite(source_risk_level):
                source_risk_level = 2.0
        else:
            source_density = 0.0
            source_risk_level = 0.0
        for successor in G.successors(node):
            if (
                G[node][successor].get("gate_switch_only")
                and not allow_gate_switch_edges
            ):
                continue
            if edge_allowed is not None and not edge_allowed(node, successor):
                continue
            (
                resource_id,
                travel,
                edge_density,
                edge_risk_level,
                resource_rate,
            ) = edge_records[(node, successor)]
            if not math.isfinite(travel):
                continue
            queue = aa_planning_resource_queue(
                G, resource_id, eta, predictive=predictive
            )
            if not math.isfinite(queue):
                continue
            wait = 0.0
            if queue > 0:
                if resource_rate <= 0:
                    continue
                wait = queue / resource_rate
            batch_gate_service_time = aa_current_batch_gate_service_time(
                G,
                resource_id,
                amount,
            )
            if not math.isfinite(batch_gate_service_time):
                continue
            arrival_without_spatial_wait = (
                eta + wait + batch_gate_service_time + travel
            )

            if not predictive:
                spatial_wait = 0.0
            elif skip_duplicate_gate_queue_spatial_wait(G, node, successor):
                spatial_wait = 0.0
            else:
                spatial_amount = spatial_wait_planning_amount(G, amount, resource_rate)
                spatial_wait = aa_planning_spatial_wait(
                    G,
                    successor,
                    arrival_without_spatial_wait,
                    spatial_amount,
                )

            if not math.isfinite(spatial_wait):
                continue

            segment_time = (
                wait + batch_gate_service_time + travel + spatial_wait
            )
            candidate_time = elapsed + segment_time
            arrival_time = start_time + candidate_time

            if predictive:
                destination_density = cached_predicted_density(successor, arrival_time)
                destination_risk_level = density_risk_level(destination_density)

                if not math.isfinite(destination_risk_level) or not math.isfinite(edge_risk_level):
                    stats = G.graph.setdefault("_aa_density_risk_stats", {})
                    stats["skipped_jam_density_edges"] = (
                        int(stats.get("skipped_jam_density_edges", 0)) + 1
                    )
                    continue

                waiting_risk = source_risk_level * (
                    wait + batch_gate_service_time + spatial_wait
                )
                movement_risk = max(
                    edge_risk_level,
                    destination_risk_level,
                ) * travel
                risk_increment = waiting_risk + movement_risk
                segment_risk_level = max(
                    source_risk_level,
                    destination_risk_level,
                    edge_risk_level,
                )
            else:
                source_density = 0.0
                destination_density = 0.0
                edge_density = 0.0
                source_risk_level = 0.0
                destination_risk_level = 0.0
                edge_risk_level = 0.0
                waiting_risk = 0.0
                movement_risk = 0.0
                risk_increment = 0.0
                segment_risk_level = 0.0

            candidate_risk = current_risk + risk_increment
            candidate_objective = (
                candidate_time
                + safety_weight * candidate_risk
            )

            if candidate_objective + 1e-9 >= best_objective.get(successor, float("inf")):
                continue
            candidate_estimated_total = (
                candidate_objective
                + lower_bounds.get(successor, 0.0)
            )
            if math.isfinite(cutoff) and candidate_estimated_total >= cutoff:
                continue
            best_objective[successor] = candidate_objective
            elapsed_time[successor] = candidate_time
            accumulated_risk[successor] = candidate_risk
            predecessor[successor] = node
            detail_for_node[successor] = (
                node,
                successor,
                resource_id,
                eta,
                queue,
                wait,
                batch_gate_service_time,
                spatial_wait,
                travel,
                arrival_time,
                destination_density,
                source_density,
                edge_density,
                source_risk_level,
                destination_risk_level,
                edge_risk_level,
                segment_risk_level,
                waiting_risk,
                movement_risk,
                risk_increment,
                candidate_risk,
                segment_time,
                candidate_time,
                candidate_objective,
            )
            heapq.heappush(
                labels,
                (
                    candidate_estimated_total,
                    candidate_objective,
                    candidate_time,
                    str(successor),
                    successor,
                ),
            )
    if target is None:
        return None, float("inf"), []
    path = [target]
    details = []
    while path[-1] != start:
        child = path[-1]
        details.append(aa_detail_tuple_to_dict(detail_for_node[child]))
        path.append(predecessor[child])
    path.reverse()
    details.reverse()
    return path, best_objective[target], details


def _time_dependent_astar_multilabel(
    G,
    start,
    current_time=None,
    amount=1,
    predictive=True,
    objective_cutoff=None,
    target_exits=None,
    edge_allowed=None,
    allow_gate_switch_edges=False,
):
    """Continuous-time multi-label search for frozen ETA-dependent AA costs.

    Labels retain node, elapsed arrival time, accumulated risk, and generalized
    objective separately.  Distinct arrival times at the same node are not
    merged.  With the admissible free-flow lower bound, this searches the best
    simple path under the prediction state fixed for this routing call.
    """
    started = time.perf_counter()
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    diagnostics["multilabel_search_count"] = (
        int(diagnostics.get("multilabel_search_count", 0)) + 1
    )
    incumbent_path, incumbent_cost, incumbent_details = (
        _time_dependent_astar_single_label(
            G,
            start,
            current_time=current_time,
            amount=amount,
            predictive=predictive,
            objective_cutoff=objective_cutoff,
            target_exits=target_exits,
            edge_allowed=edge_allowed,
            allow_gate_switch_edges=allow_gate_switch_edges,
        )
    )
    start_time = float(
        G.graph.get("_sim_time", 0.0) if current_time is None else current_time
    )
    cutoff = (
        float(objective_cutoff)
        if objective_cutoff is not None
        else float("inf")
    )
    safety_weight = aa_safety_weight(G)
    edge_records = ensure_aa_step_edge_records(G)
    density_cache = {}

    def cached_predicted_density(node, target_time):
        key = (node, float(target_time))
        if key not in density_cache:
            density_cache[key] = predicted_spatial_density(
                G,
                node,
                target_time,
                amount=0,
            )
        return density_cache[key]

    exits = (
        set(target_exits)
        if target_exits is not None
        else set(allowed_exit_nodes(G))
    )
    exits.intersection_update(G.nodes)
    if start in exits:
        return [start], 0.0, []
    lower_bounds = ensure_aa_free_flow_exit_lower_bounds(G)

    def remaining_lower_bound(node):
        if bool(G.graph.get("aa_multilabel_zero_heuristic", False)):
            return 0.0
        return float(lower_bounds.get(node, 0.0))

    labels_by_id = {}
    labels_by_node = {}
    labels_by_bucket = {}
    open_heap = []
    next_label_id = 0
    index_bucket_width = float(
        G.graph.get("aa_multilabel_index_bucket_width", 1.0) or 1.0
    )
    if not math.isfinite(index_bucket_width) or index_bucket_width <= 0.0:
        index_bucket_width = 1.0

    def store_label(label):
        nonlocal next_label_id
        label_id = next_label_id
        next_label_id += 1
        label["label_id"] = label_id
        labels_by_id[label_id] = label
        labels_by_node.setdefault(label["node"], []).append(label_id)
        arrival_bucket = int(math.floor(label["elapsed"] / index_bucket_width))
        labels_by_bucket.setdefault((label["node"], arrival_bucket), []).append(
            label_id
        )
        diagnostics["multilabel_generated_label_count"] = (
            int(diagnostics.get("multilabel_generated_label_count", 0)) + 1
        )
        labels_for_node = labels_by_node.get(label["node"], ())
        diagnostics["multilabel_max_labels_per_node"] = max(
            int(diagnostics.get("multilabel_max_labels_per_node", 0)),
            sum(
                1
                for existing_id in labels_for_node
                if labels_by_id.get(existing_id, {}).get("active", True)
            ),
        )
        estimated_total = label["objective"] + remaining_lower_bound(label["node"])
        heapq.heappush(
            open_heap,
            (
                estimated_total,
                label["objective"],
                label["elapsed"],
                label["risk"],
                str(label["node"]),
                label_id,
            ),
        )
        diagnostics["multilabel_max_open_heap_size"] = max(
            int(diagnostics.get("multilabel_max_open_heap_size", 0)),
            len(open_heap),
        )
        return label_id

    store_label({
        "node": start,
        "elapsed": 0.0,
        "risk": 0.0,
        "objective": 0.0,
        "predecessor_label_id": None,
        "detail": None,
        "visited_nodes": frozenset((start,)),
        "active": True,
    })

    best_exit_label_id = None
    best_exit_objective = min(float(incumbent_cost), cutoff)

    while open_heap:
        estimated_total, objective_cost, elapsed, _, _, label_id = (
            heapq.heappop(open_heap)
        )
        if (
            best_exit_label_id is not None
            and estimated_total >= best_exit_objective - EPS
        ):
            break
        if math.isfinite(cutoff) and estimated_total >= cutoff - EPS:
            break
        label = labels_by_id.get(label_id)
        if label is None or not label.get("active", True):
            continue
        if objective_cost > float(label["objective"]) + EPS:
            continue
        diagnostics["multilabel_expanded_label_count"] = (
            int(diagnostics.get("multilabel_expanded_label_count", 0)) + 1
        )
        node = label["node"]
        if node in exits:
            if objective_cost < best_exit_objective - EPS:
                best_exit_objective = objective_cost
                best_exit_label_id = label_id
            continue

        eta = start_time + elapsed
        if predictive:
            source_density = cached_predicted_density(node, eta)
            source_risk_level = density_risk_level(source_density)
            if not math.isfinite(source_risk_level):
                source_risk_level = 2.0
        else:
            source_density = 0.0
            source_risk_level = 0.0

        for successor in G.successors(node):
            if successor in label["visited_nodes"]:
                diagnostics["multilabel_pruned_cycle_count"] = (
                    int(diagnostics.get("multilabel_pruned_cycle_count", 0))
                    + 1
                )
                continue
            if (
                G[node][successor].get("gate_switch_only")
                and not allow_gate_switch_edges
            ):
                continue
            if edge_allowed is not None and not edge_allowed(node, successor):
                continue
            (
                resource_id,
                travel,
                edge_density,
                edge_risk_level,
                resource_rate,
            ) = edge_records[(node, successor)]
            if not math.isfinite(travel):
                continue
            queue = aa_planning_resource_queue(
                G, resource_id, eta, predictive=predictive
            )
            if not math.isfinite(queue):
                continue
            wait = 0.0
            if queue > 0:
                if resource_rate <= 0:
                    continue
                wait = queue / resource_rate
            batch_gate_service_time = aa_current_batch_gate_service_time(
                G,
                resource_id,
                amount,
            )
            if not math.isfinite(batch_gate_service_time):
                continue
            arrival_without_spatial_wait = (
                eta + wait + batch_gate_service_time + travel
            )
            if not predictive:
                spatial_wait = 0.0
            elif skip_duplicate_gate_queue_spatial_wait(G, node, successor):
                spatial_wait = 0.0
            else:
                spatial_amount = spatial_wait_planning_amount(G, amount, resource_rate)
                spatial_wait = aa_planning_spatial_wait(
                    G,
                    successor,
                    arrival_without_spatial_wait,
                    spatial_amount,
                )
            if not math.isfinite(spatial_wait):
                continue

            segment_time = wait + batch_gate_service_time + travel + spatial_wait
            candidate_time = elapsed + segment_time
            arrival_time = start_time + candidate_time

            if predictive:
                destination_density = cached_predicted_density(
                    successor,
                    arrival_time,
                )
                destination_risk_level = density_risk_level(destination_density)
                if (
                    not math.isfinite(destination_risk_level)
                    or not math.isfinite(edge_risk_level)
                ):
                    stats = G.graph.setdefault("_aa_density_risk_stats", {})
                    stats["skipped_jam_density_edges"] = (
                        int(stats.get("skipped_jam_density_edges", 0)) + 1
                    )
                    continue
                waiting_risk = source_risk_level * (
                    wait + batch_gate_service_time + spatial_wait
                )
                movement_risk = max(
                    edge_risk_level,
                    destination_risk_level,
                ) * travel
                risk_increment = waiting_risk + movement_risk
                segment_risk_level = max(
                    source_risk_level,
                    destination_risk_level,
                    edge_risk_level,
                )
            else:
                source_density = 0.0
                destination_density = 0.0
                edge_density = 0.0
                source_risk_level = 0.0
                destination_risk_level = 0.0
                edge_risk_level = 0.0
                waiting_risk = 0.0
                movement_risk = 0.0
                risk_increment = 0.0
                segment_risk_level = 0.0

            candidate_risk = float(label["risk"]) + risk_increment
            candidate_objective = candidate_time + safety_weight * candidate_risk
            candidate_estimated_total = (
                candidate_objective + remaining_lower_bound(successor)
            )
            if (
                math.isfinite(best_exit_objective)
                and candidate_estimated_total >= best_exit_objective - EPS
            ):
                diagnostics["multilabel_pruned_upper_bound_count"] = (
                    int(diagnostics.get("multilabel_pruned_upper_bound_count", 0))
                    + 1
                )
                continue
            if math.isfinite(cutoff) and candidate_estimated_total >= cutoff - EPS:
                diagnostics["multilabel_pruned_upper_bound_count"] = (
                    int(diagnostics.get("multilabel_pruned_upper_bound_count", 0))
                    + 1
                )
                continue

            dominated = False
            for old_id in list(labels_by_node.get(successor, ())):
                old = labels_by_id.get(old_id)
                if old is None or not old.get("active", True):
                    continue
                same_arrival = (
                    abs(float(old["elapsed"]) - candidate_time)
                    <= ARRIVAL_TIME_EPS
                )
                if not same_arrival:
                    continue
                if (
                    float(old["risk"]) <= candidate_risk + EPS
                    and float(old["objective"]) <= candidate_objective + EPS
                ):
                    dominated = True
                    diagnostics["multilabel_pruned_same_arrival_count"] = (
                        int(
                            diagnostics.get(
                                "multilabel_pruned_same_arrival_count",
                                0,
                            )
                        )
                        + 1
                    )
                    break
                if (
                    candidate_risk <= float(old["risk"]) + EPS
                    and candidate_objective <= float(old["objective"]) + EPS
                ):
                    old["active"] = False
            if dominated:
                continue

            detail = (
                node,
                successor,
                resource_id,
                eta,
                queue,
                wait,
                batch_gate_service_time,
                spatial_wait,
                travel,
                arrival_time,
                destination_density,
                source_density,
                edge_density,
                source_risk_level,
                destination_risk_level,
                edge_risk_level,
                segment_risk_level,
                waiting_risk,
                movement_risk,
                risk_increment,
                candidate_risk,
                segment_time,
                candidate_time,
                candidate_objective,
            )
            store_label({
                "node": successor,
                "elapsed": candidate_time,
                "risk": candidate_risk,
                "objective": candidate_objective,
                "predecessor_label_id": label_id,
                "detail": detail,
                "visited_nodes": label["visited_nodes"] | frozenset((successor,)),
                "active": True,
            })

    diagnostics["multilabel_runtime_seconds"] = (
        float(diagnostics.get("multilabel_runtime_seconds", 0.0))
        + (time.perf_counter() - started)
    )
    G.graph["_aa_last_multilabel_labels_by_node"] = labels_by_node
    G.graph["_aa_last_multilabel_labels_by_id"] = labels_by_id
    G.graph["_aa_last_multilabel_labels_by_bucket"] = labels_by_bucket

    if best_exit_label_id is None:
        if (
            incumbent_path
            and math.isfinite(incumbent_cost)
            and incumbent_cost < cutoff - EPS
        ):
            return incumbent_path, incumbent_cost, incumbent_details
        return None, float("inf"), []

    label_path = []
    current_label_id = best_exit_label_id
    while current_label_id is not None:
        label = labels_by_id[current_label_id]
        label_path.append(label)
        current_label_id = label["predecessor_label_id"]
    label_path.reverse()
    path = [label["node"] for label in label_path]
    details = [
        aa_detail_tuple_to_dict(label["detail"])
        for label in label_path[1:]
    ]
    return path, best_exit_objective, details


def _aa_compare_should_sample(G, start, current_time, amount):
    rate = float(
        G.graph.get(
            "aa_multilabel_compare_sample_rate",
            AA_MULTILABEL_COMPARE_SAMPLE_RATE_DEFAULT,
        )
        or 0.0
    )
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    payload = "|".join(map(str, (
        start,
        current_time,
        amount,
        G.graph.get("_sim_time", 0.0),
        G.graph.get("_simulation_step", G.graph.get("_step", "")),
    )))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:15]
    sample_value = int(digest, 16) / float(16 ** 15)
    return sample_value < rate


def _record_multilabel_compare(
    G,
    single_path,
    single_cost,
    multi_path,
    multi_cost,
):
    diagnostics = G.graph.setdefault("_aa_diagnostics", {})
    diagnostics["search_compare_total_count"] = (
        int(diagnostics.get("search_compare_total_count", 0)) + 1
    )
    if (single_path or [])[:2] != (multi_path or [])[:2]:
        diagnostics["search_compare_first_hop_difference_count"] = (
            int(
                diagnostics.get(
                    "search_compare_first_hop_difference_count",
                    0,
                )
            )
            + 1
        )
    if list(single_path or []) != list(multi_path or []):
        diagnostics["search_compare_full_path_difference_count"] = (
            int(
                diagnostics.get(
                    "search_compare_full_path_difference_count",
                    0,
                )
            )
            + 1
        )
    objective_difference = float(single_cost) - float(multi_cost)
    if math.isfinite(objective_difference):
        diagnostics["search_compare_objective_difference_sum"] = (
            float(
                diagnostics.get(
                    "search_compare_objective_difference_sum",
                    0.0,
                )
            )
            + objective_difference
        )
        diagnostics["search_compare_objective_difference_max"] = max(
            float(
                diagnostics.get(
                    "search_compare_objective_difference_max",
                    0.0,
                )
            ),
            objective_difference,
        )
        if objective_difference > EPS:
            diagnostics["search_compare_multilabel_better_count"] = (
                int(
                    diagnostics.get(
                        "search_compare_multilabel_better_count",
                        0,
                    )
                )
                + 1
            )


def time_dependent_astar(
    G,
    start,
    current_time=None,
    amount=1,
    predictive=True,
    objective_cutoff=None,
    target_exits=None,
    edge_allowed=None,
    allow_gate_switch_edges=False,
):
    search_mode = str(
        G.graph.get("aa_search_mode", AA_SEARCH_MODE_DEFAULT)
    ).lower()
    if search_mode not in {"multilabel", "single_label", "compare"}:
        raise ValueError(
            "aa_search_mode must be 'multilabel', 'single_label', or 'compare'; "
            f"got {search_mode!r}"
        )
    if search_mode == "multilabel":
        return _time_dependent_astar_multilabel(
            G,
            start,
            current_time=current_time,
            amount=amount,
            predictive=predictive,
            objective_cutoff=objective_cutoff,
            target_exits=target_exits,
            edge_allowed=edge_allowed,
            allow_gate_switch_edges=allow_gate_switch_edges,
        )
    single = _time_dependent_astar_single_label(
        G,
        start,
        current_time=current_time,
        amount=amount,
        predictive=predictive,
        objective_cutoff=objective_cutoff,
        target_exits=target_exits,
        edge_allowed=edge_allowed,
        allow_gate_switch_edges=allow_gate_switch_edges,
    )
    if search_mode == "compare" and _aa_compare_should_sample(
        G,
        start,
        current_time,
        amount,
    ):
        multi = _time_dependent_astar_multilabel(
            G,
            start,
            current_time=current_time,
            amount=amount,
            predictive=predictive,
            objective_cutoff=objective_cutoff,
            target_exits=target_exits,
            edge_allowed=edge_allowed,
            allow_gate_switch_edges=allow_gate_switch_edges,
        )
        _record_multilabel_compare(
            G,
            single[0],
            single[1],
            multi[0],
            multi[1],
        )
    return single


def diagnose_time_dependent_exit_candidates(
    G,
    start,
    current_time,
    amount,
    targets,
):
    """Evaluate selected AA exit alternatives without affecting route choice."""
    rows = []
    for target in targets:
        path, objective, details = time_dependent_astar(
            G,
            start,
            current_time=current_time,
            amount=amount,
            predictive=True,
            target_exits=(target,),
        )
        if not path or not details or not math.isfinite(objective):
            rows.append({
                "candidate_exit": target,
                "feasible": False,
                "path": [],
                "walking_time": float("inf"),
                "front_queue_people_sum": float("inf"),
                "queue_wait_time": float("inf"),
                "current_batch_gate_service_time": 0.0,
                "current_batch_gate_service_time_formula": 0.0,
                "terminal_edge_batch_mean_discharge_time": float("inf"),
                "objective_with_terminal_discharge_diagnostic": float("inf"),
                "spatial_wait_time": float("inf"),
                "density_risk": float("inf"),
                "objective_cost": float("inf"),
            })
            continue

        gate_service_time = sum(
            float(item.get("current_batch_gate_service_time", 0.0))
            for item in details
        )
        terminal_discharge_time = 0.0
        if path[-1] in G.nodes and G.nodes[path[-1]].get("type") == "exit":
            terminal_resource = details[-1].get("resource_id")
            if terminal_resource and terminal_resource[0] == "edge":
                terminal_rate = resource_capacity_per_second(
                    G, terminal_resource
                )
                if math.isfinite(terminal_rate) and terminal_rate > 0.0:
                    terminal_discharge_time = max(float(amount), 0.0) / (
                        2.0 * terminal_rate
                    )

        rows.append({
            "candidate_exit": target,
            "feasible": True,
            "path": list(path),
            "walking_time": sum(
                float(item.get("travel_time", 0.0)) for item in details
            ),
            "front_queue_people_sum": sum(
                float(item.get("predicted_queue", 0.0)) for item in details
            ),
            "queue_wait_time": sum(
                float(item.get("predicted_wait", 0.0)) for item in details
            ),
            "current_batch_gate_service_time": gate_service_time,
            "current_batch_gate_service_time_formula": gate_service_time,
            "terminal_edge_batch_mean_discharge_time": (
                terminal_discharge_time
            ),
            "objective_with_terminal_discharge_diagnostic": (
                float(objective) + terminal_discharge_time
            ),
            "spatial_wait_time": sum(
                float(item.get("spatial_wait", 0.0)) for item in details
            ),
            "density_risk": float(
                details[-1].get("accumulated_risk", 0.0)
            ),
            "objective_cost": float(objective),
        })
    return rows


def register_round_prediction_events(
    G,
    details,
    amount,
    source_group,
    batch_id,
):
    """
    Register AA soft resource intentions for later batches in the same
    simulation step.

    Important:
    - These records are planning intentions only.
    - They may increase predicted resource queues and waiting costs.
    - They are not accepted physical movements.
    - They must never create node spatial-occupancy events.
    """
    amount = max(int(amount), 0)
    if amount <= 0:
        return

    events = G.graph.setdefault("_aa_round_prediction_events", [])
    versions = G.graph.setdefault("_aa_round_prediction_versions", {})
    seen_resources = set()

    for detail in details:
        resource_id = detail.get("resource_id")
        if resource_id is None or resource_id in seen_resources:
            continue

        seen_resources.add(resource_id)
        resource_time = float(detail["resource_entry_time"])

        event = {
            "resource_id": resource_id,
            "predicted_arrival_time": resource_time,
            "amount": amount,
            "source_group": source_group,
            "batch_id": batch_id,
            "event_kind": "soft_planning_intent",
        }
        events.append(event)
        versions[resource_id] = int(versions.get(resource_id, 0)) + 1

        if bool(G.graph.get("_fast_exact_aa", True)):
            insert_resource_prediction_event(
                G,
                resource_id,
                resource_time,
                amount,
            )
            continue

        # The AA queue-prediction cache may already exist because earlier
        # batches in this round have queried it. Add only the soft RESOURCE
        # intention to that cache. Never add a spatial node event here.
        cache = G.graph.get("_confirmed_resource_arrivals_cache")
        if cache is None:
            continue

        resource_events = cache["events_by_resource"].setdefault(
            resource_id,
            [],
        )
        resource_times = cache.setdefault(
            "times_by_resource",
            {},
        ).setdefault(
            resource_id,
            [],
        )

        insert_at = bisect_right(resource_times, resource_time)
        resource_times.insert(insert_at, resource_time)
        resource_events.insert(
            insert_at,
            (resource_time, amount),
        )


def evaluate_time_dependent_path(
    G,
    path,
    current_time=None,
    amount=1,
    predictive=True,
):
    if not path or len(path) < 2:
        return float("inf"), []
    eta = float(G.graph.get("_sim_time", 0.0) if current_time is None else current_time)
    start_time = eta
    safety_weight = aa_safety_weight(G)
    edge_records = ensure_aa_step_edge_records(G)
    accumulated_risk = 0.0
    details = []
    for u, v in zip(path, path[1:]):
        if not G.has_edge(u, v):
            return float("inf"), []
        (
            resource_id,
            travel,
            edge_density,
            edge_risk_level,
            resource_rate,
        ) = edge_records[(u, v)]
        queue = aa_planning_resource_queue(
            G, resource_id, eta, predictive=predictive
        )
        wait = 0.0
        if queue > 0:
            if resource_rate <= 0:
                return float("inf"), []
            wait = queue / resource_rate
        batch_gate_service_time = aa_current_batch_gate_service_time(
            G,
            resource_id,
            amount,
        )
        if not math.isfinite(batch_gate_service_time):
            return float("inf"), []
        if not math.isfinite(travel):
            return float("inf"), []

        arrival_without_spatial_wait = (
            eta + wait + batch_gate_service_time + travel
        )

        if not predictive:
            spatial_wait = 0.0
        elif skip_duplicate_gate_queue_spatial_wait(G, u, v):
            spatial_wait = 0.0
        else:
            spatial_amount = spatial_wait_planning_amount(G, amount, resource_rate)
            spatial_wait = aa_planning_spatial_wait(
                G,
                v,
                arrival_without_spatial_wait,
                spatial_amount,
            )

        if not math.isfinite(spatial_wait):
            return float("inf"), []

        entry_time = eta
        segment_time = wait + batch_gate_service_time + travel + spatial_wait
        eta += segment_time
        physical_elapsed_time = eta - start_time

        if predictive:
            source_density = predicted_spatial_density(
                G,
                u,
                entry_time,
                amount=0,
            )
            source_risk_level = density_risk_level(source_density)
            if not math.isfinite(source_risk_level):
                source_risk_level = 2.0
            destination_density = predicted_spatial_density(
                G,
                v,
                eta,
                amount=0,
            )
            destination_risk_level = density_risk_level(destination_density)

            if not math.isfinite(destination_risk_level) or not math.isfinite(edge_risk_level):
                stats = G.graph.setdefault("_aa_density_risk_stats", {})
                stats["skipped_jam_density_edges"] = (
                    int(stats.get("skipped_jam_density_edges", 0)) + 1
                )
                return float("inf"), []

            waiting_risk = source_risk_level * (
                wait + batch_gate_service_time + spatial_wait
            )
            movement_risk = max(
                edge_risk_level,
                destination_risk_level,
            ) * travel
            risk_increment = waiting_risk + movement_risk
            segment_risk_level = max(
                source_risk_level,
                destination_risk_level,
                edge_risk_level,
            )
        else:
            source_density = 0.0
            destination_density = 0.0
            edge_density = 0.0
            source_risk_level = 0.0
            destination_risk_level = 0.0
            edge_risk_level = 0.0
            waiting_risk = 0.0
            movement_risk = 0.0
            risk_increment = 0.0
            segment_risk_level = 0.0

        accumulated_risk += risk_increment
        objective_cost = (
            physical_elapsed_time
            + safety_weight * accumulated_risk
        )
        details.append({
            "u": u, "v": v, "resource_id": resource_id,
            "resource_entry_time": entry_time, "predicted_queue": queue,
            "predicted_wait": wait, "spatial_wait": spatial_wait,
            "current_batch_gate_service_time": batch_gate_service_time,
            "travel_time": travel, "arrival_time": eta,
            "predicted_density": destination_density,
            "source_predicted_density": source_density,
            "destination_predicted_density": destination_density,
            "edge_density": edge_density,
            "source_density_risk_level": source_risk_level,
            "destination_density_risk_level": destination_risk_level,
            "edge_density_risk_level": edge_risk_level,
            "density_risk_level": segment_risk_level,
            "waiting_risk_increment": waiting_risk,
            "movement_risk_increment": movement_risk,
            "risk_increment": risk_increment,
            "accumulated_risk": accumulated_risk,
            "physical_segment_time": segment_time,
            "physical_elapsed_time": physical_elapsed_time,
            "objective_cost": objective_cost,
        })
    return details[-1]["objective_cost"], details


def edge_dynamic_cost(G, u, v, method, speed_fn=None):
    """Dispatch edge cost to the correct algorithm.

    *speed_fn* is kept for backward compatibility but unused in the new framework
    (Fruin speed model is called directly).
    """
    normalized_method = normalize_method(method)
    base_method = routing_base_method(normalized_method)

    if base_method == PAPER_SINGLE_PATH_METHOD:
        return paper_edge_cost(G, u, v)

    if base_method == OUR_SINGLE_PATH_METHOD:
        return adaptive_edge_cost(G, u, v, normalized_method)

    # Fallback: geometric length
    return float(G[u][v].get("length", 0.0))


# ═══════════════════════════════════════════════════════════════════════════════
# Dynamic weight update (called every simulation step)
# ═══════════════════════════════════════════════════════════════════════════════

def update_dynamic_weights(G, method, speed_fn=None, weight_key="sim_weight"):
    """Write per-edge costs and precompute support data for g(n) and h(n)."""
    normalized_method = normalize_method(method)

    # First pass: per-edge costs (g(n))
    for u, v, data in G.edges(data=True):
        if data.get("gate_switch_only"):
            data[weight_key] = float("inf")
            continue
        data[weight_key] = edge_dynamic_cost(G, u, v, normalized_method)



# ═══════════════════════════════════════════════════════════════════════════════
# Path enumeration — A* search over all exits
# ═══════════════════════════════════════════════════════════════════════════════

def _aa_distinct_next_hop_paths(
    G, current_node, exits, method, weight_key, shortest_dists=None
):
    """Return cached, loop-free A* candidates through distinct facilities.

    Static structural candidates are generated with A* and cached. Each time
    step only recomputes their dynamic AA costs. Branching over the first two
    hops exposes alternatives that reach the same exit through different
    stairs, escalators, gates or corridors, while execution remains one
    next-hop per node.
    """
    topology_signature = G.graph.get("_aa_topology_signature")
    if topology_signature is None:
        topology_signature = (G.number_of_nodes(), G.number_of_edges())
        G.graph["_aa_topology_signature"] = topology_signature
    topology_key = (
        *topology_signature,
        tuple(sorted(exits, key=str)),
        current_node,
    )
    cache = G.graph.setdefault("_aa_static_candidate_paths", {})
    structural_paths = cache.get(topology_key)
    if structural_paths is None:
        distance_map = shortest_dists or {}
        generated = []
        seen = set()

        def add_path(prefix, start, target):
            try:
                tail = nx.astar_path(
                    G,
                    start,
                    target,
                    heuristic=lambda node, goal: float(
                        distance_map.get(node, {}).get(goal, 0.0)
                    ),
                    weight=lambda u, v, data: (
                        None
                        if data.get("gate_switch_only")
                        else float(data.get("length", 0.0))
                    ),
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return
            path = list(prefix) + list(tail)
            key = tuple(path)
            if len(path) <= 1 or len(set(path)) != len(path) or key in seen:
                return
            seen.add(key)
            generated.append(path)

        for target in exits:
            for next_hop in G.successors(current_node):
                if G[current_node][next_hop].get("gate_switch_only"):
                    continue
                add_path([current_node], next_hop, target)
                for second_hop in G.successors(next_hop):
                    if G[next_hop][second_hop].get("gate_switch_only"):
                        continue
                    add_path([current_node, next_hop], second_hop, target)

        selected = []
        by_exit = {}
        for path in sorted(
            generated,
            key=lambda p: (
                sum(float(G[u][v].get("length", 0.0)) for u, v in zip(p, p[1:])),
                len(p),
                tuple(map(str, p)),
            ),
        ):
            target = path[-1]
            facility_signature = tuple(
                node for node in path if is_capacity_service_node(G, node)
            )
            signatures = by_exit.setdefault(target, set())
            if facility_signature in signatures or len(signatures) >= K_CANDIDATE_PATHS:
                continue
            signatures.add(facility_signature)
            selected.append(path)
        structural_paths = selected
        cache[topology_key] = structural_paths

    candidates = []
    for path in structural_paths:
        total_cost = _aa_live_path_cost(G, path, method)
        if math.isfinite(total_cost):
            candidates.append({
                "target": path[-1],
                "path": path,
                "next_hop": path[1],
                "cost": total_cost,
            })
    candidates.sort(key=lambda item: (item["cost"], len(item["path"]), str(item["next_hop"])))
    return candidates


def _aa_live_path_cost(G, path, method):
    """Return cumulative-ETA cost for a retained or newly generated path."""
    total_cost, _ = evaluate_candidate_path_with_cumulative_eta(G, path, method)
    return total_cost


def enumerate_exit_paths(G, current_node, method, shortest_dists, speed_fn=None, weight_key="sim_weight"):
    """Run A* from *current_node* to every allowed exit; return sorted candidates.

    For AdaptiveQueueAwareAStar: h(n) uses congestion-aware shortest time
    precomputed by update_dynamic_weights() (Bai et al. 2025, Eq. 8 adapted).
    Edge costs and heuristic share the same sim_weight model.
    """
    method_normalized = normalize_method(method)
    exits = allowed_exit_nodes(G)
    if not exits:
        return []

    if routing_base_method(method_normalized) == OUR_SINGLE_PATH_METHOD:
        # AA structural paths are cached with length-based A*. Only those few
        # candidates receive live cumulative-ETA scoring; a full O(|E|)
        # dynamic-weight rewrite is both redundant and expensive.
        return _aa_distinct_next_hop_paths(
            G,
            current_node,
            exits,
            method_normalized,
            weight_key,
            shortest_dists,
        )

    # Compute edge weights once per simulation step (guarded by step counter).
    # This prevents redundant O(|E|) recomputation for every active node.
    sim_time = float(G.graph.get("_sim_time", -1.0))
    last_update = G.graph.get("_dyn_weight_step", -1.0)
    if sim_time != last_update:
        update_dynamic_weights(G, method_normalized, speed_fn, weight_key=weight_key)
        G.graph["_dyn_weight_step"] = sim_time

    # Reuse the immutable distance mapping. Copying it for every active node
    # dominated routing time in large scenarios.
    heuristic_data = shortest_dists or {}

    candidates = []

    for target in exits:
        try:
            if uses_dynamic_a_star(method_normalized):

                def _heuristic(u, v, d_dict=heuristic_data, meth=method_normalized):
                    return heuristic_cost(u, v, d_dict, meth)

                path = nx.astar_path(
                    G,
                    current_node,
                    target,
                    heuristic=_heuristic,
                    weight=weight_key,
                )
            else:
                path = nx.shortest_path(G, current_node, target, weight=weight_key)
        except nx.NetworkXNoPath:
            continue

        if len(path) <= 1:
            continue

        cost = sum(G[path[i]][path[i + 1]][weight_key] for i in range(len(path) - 1))
        # NetworkX may still return an all-infinite path when every structural
        # alternative is blocked. Such a path is not an admissible route.
        if not math.isfinite(cost):
            continue
        candidates.append({
            "target": target,
            "path": path,
            "next_hop": path[1],
            "cost": cost,
        })

    candidates.sort(key=lambda item: item["cost"])
    return candidates


def get_best_path_to_exit(G, current_node, method, shortest_dists, speed_fn=None):
    candidates = enumerate_exit_paths(G, current_node, method, shortest_dists, speed_fn)
    if not candidates:
        return None
    return candidates[0]["path"]


def get_best_next_node(G, current_node, method, shortest_dists, speed_fn=None):
    candidates = enumerate_exit_paths(G, current_node, method, shortest_dists, speed_fn)
    if not candidates:
        return None
    return candidates[0]["next_hop"]


# ═══════════════════════════════════════════════════════════════════════════════
# Backward-compatibility stubs for code that still references old names
# ═══════════════════════════════════════════════════════════════════════════════

# These functions are kept so that network.py, split_guidance.py, etc.
# continue to compile.  Their internal logic has been absorbed into
# adaptive_edge_cost() and update_dynamic_weights().

def our_penalty_weights(method):
    """Backward-compat: return empty dict (no more separate penalty weights)."""
    return {"source_release": 0.0, "downstream_release": 0.0, "exit_pressure": 0.0}


def our_edge_cost_components(G, u, v, speed_fn, method=OUR_SINGLE_PATH_METHOD):
    """Backward-compat stub delegating to adaptive_edge_cost."""
    cost = adaptive_edge_cost(G, u, v, method)
    return {
        "base_cost": cost,
        "gate_queue_penalty": 0.0,
        "service_penalty": 0.0,
        "source_release_penalty": 0.0,
        "downstream_release_penalty": 0.0,
        "exit_pressure_penalty": 0.0,
        "total_cost": cost,
    }


def our_path_cost_components(G, path, speed_fn, method=OUR_SINGLE_PATH_METHOD):
    """Backward-compat stub."""
    return {"total_cost": sum(
        adaptive_edge_cost(G, path[i], path[i + 1], method)
        for i in range(len(path) - 1)
    )}


def our_effective_density(G, u, v):
    """Backward-compat stub."""
    return paper_effective_density(G, u, v)


def _source_group_title(source_group_id):
    base, separator, zone = source_group_id.partition("::")
    parts = base.split("_")
    line_id = parts[0].upper()
    suffix = "_".join(parts[1:])

    if suffix == "hall":
        title = f"{line_id}_HALL_PEOPLE"
    elif suffix.endswith("_transfer"):
        target = suffix[: -len("_transfer")].upper()
        title = f"{line_id}_TRANSFER_PEOPLE / {target}"
    elif suffix == "platform":
        zone_label = zone.replace("Platform_", "").replace("_Wait", "").upper()
        title = f"{line_id}_PLATFORM_WAITING / {zone_label}"
    elif suffix.startswith("train"):
        train_part, _, zone_part = suffix.partition("_")
        train_number = train_part[len("train"):]
        title = f"{line_id}_TRAIN_{train_number}"
        if zone_part:
            car_map = {
                "Z1": "CAR1+CAR2",
                "Z2": "CAR3+CAR4",
                "Z3": "CAR5+CAR6",
                "Z4": "CAR7+CAR8",
            }
            title += f" / {zone_part.upper()} / {car_map.get(zone_part.upper(), '')}".rstrip(" / ")
    else:
        title = base.upper()

    return title.upper()


def _route_nodes_for_display(graph, path):
    visible = []
    for node in path:
        data = graph.nodes[node]
        node_type = str(data.get("type", "")).lower()
        node_name = str(node)
        if node_type in {"virtual", "platform", "train", "train_car"}:
            continue
        if node_name.startswith(("Platform_", "Train_")):
            continue
        if not visible or visible[-1] != node_name:
            visible.append(node_name)
    return tuple(visible)


def _find_residual_path(adjacency, residual, start, exit_nodes):
    stack = [(start, [start], {start})]
    while stack:
        node, path, visited = stack.pop()
        if node in exit_nodes:
            return path
        successors = sorted(adjacency.get(node, ()), reverse=True)
        for successor in successors:
            if successor in visited or residual.get((node, successor), 0.0) <= 1e-6:
                continue
            stack.append((successor, path + [successor], visited | {successor}))
    return None


def _decompose_source_group_routes(graph, edge_flows, source_group_id):
    residual = {
        edge: float(group_flows.get(source_group_id, 0.0))
        for edge, group_flows in edge_flows.items()
        if float(group_flows.get(source_group_id, 0.0)) > 1e-6
    }
    adjacency = {}
    inflow = {}
    outflow = {}
    for (source, destination), amount in residual.items():
        adjacency.setdefault(source, []).append(destination)
        outflow[source] = outflow.get(source, 0.0) + amount
        inflow[destination] = inflow.get(destination, 0.0) + amount

    exit_nodes = {
        node for node, data in graph.nodes(data=True) if data.get("type") == "exit"
    }
    sources = sorted(
        node for node, amount in outflow.items()
        if amount - inflow.get(node, 0.0) > 1e-6 and node not in exit_nodes
    )
    routes = {}
    for source in sources:
        supply = outflow.get(source, 0.0) - inflow.get(source, 0.0)
        while supply > 1e-6:
            path = _find_residual_path(adjacency, residual, source, exit_nodes)
            if not path or len(path) < 2:
                break
            amount = min(
                supply,
                *(residual[(path[idx], path[idx + 1])] for idx in range(len(path) - 1)),
            )
            for idx in range(len(path) - 1):
                edge = (path[idx], path[idx + 1])
                residual[edge] = max(residual[edge] - amount, 0.0)
            supply -= amount
            display_path = _route_nodes_for_display(graph, path)
            if display_path:
                routes[display_path] = routes.get(display_path, 0.0) + amount
    return routes


def _integerize_routes(routes, total_people):
    ordered = sorted(routes.items(), key=lambda item: (-item[1], item[0]))
    raw_total = sum(amount for _, amount in ordered)
    if total_people <= 0 or raw_total <= 0:
        return []

    quotas = [amount * total_people / raw_total for _, amount in ordered]
    people = [int(math.floor(quota)) for quota in quotas]
    for index in sorted(
        range(len(ordered)),
        key=lambda idx: (-(quotas[idx] - people[idx]), ordered[idx][0]),
    )[: total_people - sum(people)]:
        people[index] += 1

    percentage_units = [count * 1000.0 / total_people for count in people]
    tenths = [int(math.floor(value)) for value in percentage_units]
    for index in sorted(
        range(len(ordered)),
        key=lambda idx: (-(percentage_units[idx] - tenths[idx]), ordered[idx][0]),
    )[: 1000 - sum(tenths)]:
        tenths[index] += 1

    return [
        (path, count, units / 10.0)
        for (path, _), count, units in zip(ordered, people, tenths)
        if count > 0
    ]


def write_all_mode4_paths(graph, metrics):
    """Write aggregate edge-flow route reconstruction for diagnostics."""
    source_totals = metrics.get("source_group_totals", {})
    edge_flows = metrics.get("edge_flow_by_source_group", {})
    output_path = Path("outputs") / "aa_test_mode4_all_paths.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as output:
        output.write(
            "> NOTE: Routes below are reconstructed from aggregate edge flows. "
            "After different source groups merge, downstream segments cannot be "
            "matched to individual passengers uniquely. Clearance times and exit "
            "usage are authoritative; these complete paths are diagnostic only.\n\n"
        )
        for source_group_id in sorted(source_totals):
            total_people = int(round(float(source_totals[source_group_id])))
            routes = _decompose_source_group_routes(graph, edge_flows, source_group_id)
            integer_routes = _integerize_routes(routes, total_people)
            output.write(
                f"**{_source_group_title(source_group_id)} ({total_people} PEOPLE)**\n\n"
            )
            for path, people, percentage in integer_routes:
                output.write(
                    f"{' -> '.join(path)}: {percentage:.1f}% ({people} people)\n"
                )
            output.write("\n")
    return output_path


def run_mode4_test():
    """Run only Mode 4 AA with test routing and production network physics."""
    import algorithm_comparison as comparison

    comparison.MODE = 4
    comparison.net.OUTPUT_DIR = None
    graph = comparison.net.build_graph()
    graph.graph["density_dependent_flow"] = True
    graph.graph["split_l2_train_source_groups_by_zone"] = True
    population, total_people = comparison.build_population()

    print("=" * 72)
    print("  Mode 4 AA queue-aware single-path test")
    print(f"  Total population: {total_people}")
    print("  ImprovedAStar is not executed by this test.")
    print("=" * 72)
    result = comparison.run_one(
        graph,
        population,
        comparison.net.OUR_SINGLE_PATH_METHOD,
        "AdaptiveQueueAwareAStar",
    )
    print(f"  AA evacuation time: {result['evacuation_time']:.1f}s")
    for line_id, clear_time in sorted(
        result["_raw_metrics"].get("clearance_times_by_line", {}).items()
    ):
        print(f"  {line_id} clearance time: {clear_time:.1f}s")
    output_path = write_all_mode4_paths(graph, result["_raw_metrics"])
    print(f"  Aggregate reconstructed paths (diagnostic only): {output_path}")


if __name__ == "__main__":
    run_mode4_test()
