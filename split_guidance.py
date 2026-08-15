from single_path_routing import (
    enumerate_exit_paths,
    normalize_method,
    update_dynamic_weights,
)


def enumerate_successor_paths(
    G,
    current_node,
    method,
    shortest_dists,
    speed_fn,
    weight_key="sim_weight",
):
    """
    枚举"当前节点的每一个直接下一跳"所对应的最佳后续疏散路径。

    这和"每个出口只保留一条最优路径"不同：如果同一个出口既可以走楼梯、
    也可以走扶梯，那么这里会把两条设施分支都保留下来，便于等待区做真正的分流。
    """
    if current_node not in G.nodes:
        return []

    method = normalize_method(method)
    update_dynamic_weights(G, method, speed_fn, weight_key=weight_key)
    candidates = []

    for succ in G.successors(current_node):
        edge_cost = float(G[current_node][succ].get(weight_key, float("inf")))
        if edge_cost == float("inf"):
            continue

        if G.nodes[succ].get("type") == "exit":
            candidates.append(
                {
                    "target": succ,
                    "path": [current_node, succ],
                    "next_hop": succ,
                    "cost": edge_cost,
                }
            )
            continue

        downstream_paths = enumerate_exit_paths(
            G,
            succ,
            method,
            shortest_dists,
            speed_fn,
            weight_key=weight_key,
        )
        if not downstream_paths:
            continue

        best_downstream = downstream_paths[0]
        downstream_path = list(best_downstream["path"])
        if current_node in downstream_path[1:]:
            continue

        candidates.append(
            {
                "target": best_downstream["target"],
                "path": [current_node] + downstream_path,
                "next_hop": succ,
                "cost": edge_cost + float(best_downstream["cost"]),
            }
        )

    candidates.sort(key=lambda item: item["cost"])
    return candidates


def select_candidate_paths(
    G,
    current_node,
    method,
    shortest_dists,
    speed_fn,
    score_ratio=1.15,
    score_slack=2.0,
    max_paths=None,
):
    candidates = enumerate_successor_paths(
        G,
        current_node,
        method,
        shortest_dists,
        speed_fn,
    )
    if not candidates:
        return []

    best_cost = candidates[0]["cost"]
    picked = [
        item
        for item in candidates
        if item["cost"] <= best_cost * score_ratio or item["cost"] <= best_cost + score_slack
    ]

    if max_paths is not None:
        picked = picked[:max_paths]

    if not picked:
        picked = candidates[:1]

    return picked


def collapse_candidates_to_next_hops(candidate_paths):
    by_next_hop = {}
    for item in candidate_paths:
        next_hop = item["next_hop"]
        best = by_next_hop.get(next_hop)
        if best is None or item["cost"] < best["cost"]:
            by_next_hop[next_hop] = dict(item)
    return sorted(by_next_hop.values(), key=lambda item: item["cost"])


def allocate_split_flows(G, current_node, hop_candidates, delta_t, min_split_share=0.05):
    remaining = float(G.nodes[current_node].get("people", 0.0))
    if remaining <= 0.0 or not hop_candidates:
        return []

    capacity_left = {
        item["next_hop"]: float(G[current_node][item["next_hop"]]["capacity"]) * delta_t
        for item in hop_candidates
    }
    score_map = {item["next_hop"]: max(float(item["cost"]), 1e-6) for item in hop_candidates}

    moves = []
    active = [item["next_hop"] for item in hop_candidates]

    while remaining > 1e-9 and active:
        inv = {hop: 1.0 / score_map[hop] for hop in active}
        total_inv = sum(inv.values())
        if total_inv <= 0.0:
            break

        proposed = {hop: remaining * inv[hop] / total_inv for hop in active}
        min_allowed = remaining * min_split_share

        filtered = [hop for hop in active if proposed[hop] >= min_allowed]
        if not filtered:
            filtered = [min(active, key=lambda hop: score_map[hop])]

        if len(filtered) != len(active):
            active = filtered
            continue

        allocated = 0.0
        for hop in active:
            flow = min(proposed[hop], capacity_left[hop])
            if flow > 0.0:
                moves.append((current_node, hop, flow))
                allocated += flow
                capacity_left[hop] -= flow

        if allocated <= 1e-9:
            break

        remaining -= allocated
        active = [hop for hop in active if capacity_left[hop] > 1e-9]

    return moves


def get_split_next_moves(
    G,
    current_node,
    method,
    shortest_dists,
    speed_fn,
    delta_t,
    score_ratio=1.15,
    score_slack=2.0,
    min_split_share=0.05,
    max_paths=None,
):
    method = normalize_method(method)
    candidate_paths = select_candidate_paths(
        G,
        current_node,
        method,
        shortest_dists,
        speed_fn,
        score_ratio=score_ratio,
        score_slack=score_slack,
        max_paths=max_paths,
    )
    if not candidate_paths:
        return []

    hop_candidates = collapse_candidates_to_next_hops(candidate_paths)
    return allocate_split_flows(
        G,
        current_node,
        hop_candidates,
        delta_t,
        min_split_share=min_split_share,
    )
