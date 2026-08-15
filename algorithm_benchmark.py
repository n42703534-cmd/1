"""
algorithm_benchmark.py — Pure algorithm-level comparison on static congestion snapshot.

Compares Improved A* (Meng et al., 2022) vs AdaptiveQueueAwareAStar on:
  1. Average expanded nodes (search efficiency)
  2. Average path time cost (unified walk+wait evaluation)
  3. Average search time (ms, per OD query)

Runs on a frozen snapshot taken at a mid-point of a Mode 1 / Mode 4 simulation.
"""
import copy
import time
import csv
import os
import math
import sys

import networkx as nx
import network as net
import single_path_routing as spr

OUTPUT_DIR = os.path.join("outputs", "algorithm_benchmark")


def _counted_astar_path(G, source, target, heuristic, weight):
    """Run A* and count nodes expanded (heuristic evaluations)."""
    count = [0]

    def _counting_heuristic(u, v):
        count[0] += 1
        return heuristic(u, v)

    try:
        path = nx.astar_path(G, source, target, heuristic=_counting_heuristic, weight=weight)
    except nx.NetworkXNoPath:
        return None, 0
    return path, count[0]


def evaluate_path_time_cost(G, path):
    """Unified evaluation: compute walk+wait cost for any path (in seconds)."""
    if not path or len(path) <= 1:
        return float("inf")
    total = 0.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        # Walk time
        density = spr.paper_effective_density(G, u, v)
        walk_speed = min(spr.paper_speed_from_density(density),
                         spr.paper_facility_speed_limit(G, u, v))
        if walk_speed <= 0.001:
            return float("inf")
        length = float(G[u][v].get("length", 0.0))
        travel = length / walk_speed
        # Wait time (bottleneck nodes only)
        wait = 0.0
        if spr.is_capacity_service_node(G, v):
            people = float(G.nodes[v].get("people", 0.0)) + spr.node_reserved_inflow(G, v)
            mu = spr.node_service_capacity(G, v)
            wait = max(people / mu, 0.0)
        total += travel + wait
    return total


def run_benchmark(G, active_sources, shortest_dists, method_a, method_b):
    """Run OD comparison between two methods on a frozen graph."""
    exits = spr.allowed_exit_nodes(G)

    results = []
    for source in active_sources:
        for target in exits:
            # --- Method A (Improved A*) ---
            G.graph.pop("_dyn_weight_step", None)  # force re-compute
            t0 = time.perf_counter()
            path_a, expanded_a = _counted_astar_path(
                G, source, target,
                heuristic=lambda u, v: spr.heuristic_cost(u, v, shortest_dists, method_a),
                weight="sim_weight",
            )
            wall_a = (time.perf_counter() - t0) * 1000  # ms
            cost_a = evaluate_path_time_cost(G, path_a) if path_a else float("inf")

            # --- Method B (AdaptiveQueueAwareAStar) ---
            G.graph.pop("_dyn_weight_step", None)
            t0 = time.perf_counter()
            path_b, expanded_b = _counted_astar_path(
                G, source, target,
                heuristic=lambda u, v: spr.heuristic_cost(u, v, shortest_dists, method_b),
                weight="sim_weight",
            )
            wall_b = (time.perf_counter() - t0) * 1000
            cost_b = evaluate_path_time_cost(G, path_b) if path_b else float("inf")

            if path_a and path_b:
                results.append({
                    "source": source,
                    "target": target,
                    "expanded_A": expanded_a,
                    "expanded_B": expanded_b,
                    "cost_A": round(cost_a, 3),
                    "cost_B": round(cost_b, 3),
                    "time_A_ms": round(wall_a, 3),
                    "time_B_ms": round(wall_b, 3),
                })

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pure algorithm benchmark")
    parser.add_argument("--mode", type=int, default=1, choices=[1, 4],
                        help="Scenario: 1=regular surge, 4=bidirectional full")
    parser.add_argument("--snapshot-time", type=float, default=200.0,
                        help="Simulation time (s) at which to freeze the graph")
    parser.add_argument("--max-pairs", type=int, default=500,
                        help="Max OD pairs to test (limits runtime)")
    args = parser.parse_args()

    net.OUTPUT_DIR = None
    G = net.build_graph()
    pop_dict, total_people = _build_population(args.mode)

    print(f"Mode {args.mode} | {total_people} people | snapshot at t={args.snapshot_time}s")
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Run simulation up to snapshot time
    print(f"\nRunning simulation to t={args.snapshot_time}s ...")
    G_sim = copy.deepcopy(G)
    net.init_people(G_sim, pop_dict)
    targets = net._infer_target_by_line_from_graph_state(G_sim)
    metrics = net._run_simulation_for_metrics_core(G_sim, net.OUR_SINGLE_PATH_METHOD, targets,
                                                    stop_at_time=args.snapshot_time)
    remaining = sum(G_sim.nodes[n].get("people", 0) for n in G_sim.nodes())
    print(f"  Remaining: {remaining:.0f} people,  t={metrics['time']:.1f}s")

    # Precompute heuristic distances
    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(G_sim, weight="length"))
    spr.update_dynamic_weights(G_sim, net.OUR_SINGLE_PATH_METHOD)

    # Identify active source nodes
    active_sources = [n for n in G_sim.nodes()
                      if G_sim.nodes[n].get("people", 0) > 5 and G_sim.nodes[n].get("type") != "exit"]
    print(f"Active sources: {len(active_sources)}")
    if len(active_sources) > 30:
        active_sources = active_sources[:30]
        print(f"  (capped at 30 for runtime)")

    method_a = net.PAPER_SINGLE_PATH_METHOD  # Improved A*
    method_b = net.OUR_SINGLE_PATH_METHOD     # AdaptiveQueueAwareAStar

    print(f"\nRunning {len(active_sources)} sources x {len(spr.allowed_exit_nodes(G_sim))} exits ...")
    results = run_benchmark(G_sim, active_sources, shortest_dists, method_a, method_b)

    if not results:
        print("ERROR: no valid paths found")
        return

    # Summarise
    n = len(results)
    avg_exp_a = sum(r["expanded_A"] for r in results) / n
    avg_exp_b = sum(r["expanded_B"] for r in results) / n
    avg_cost_a = sum(r["cost_A"] for r in results) / n
    avg_cost_b = sum(r["cost_B"] for r in results) / n
    avg_time_a = sum(r["time_A_ms"] for r in results) / n
    avg_time_b = sum(r["time_B_ms"] for r in results) / n

    print(f"\n{'='*70}")
    print(f"  Pure Algorithm Benchmark — Mode {args.mode}, {n} OD pairs")
    print(f"{'='*70}")
    print(f"  {'Metric':<30} {'Improved A*':>15} {'AdaptiveQueueAwareAStar':>22}")
    print(f"  {'-'*30} {'-'*15} {'-'*22}")
    print(f"  {'Avg expanded nodes':<30} {avg_exp_a:>15.1f} {avg_exp_b:>22.1f}")
    print(f"  {'Avg path time cost (s)':<30} {avg_cost_a:>15.2f} {avg_cost_b:>22.2f}")
    print(f"  {'Avg search time (ms)':<30} {avg_time_a:>15.2f} {avg_time_b:>22.2f}")
    print(f"{'='*70}")
    print(f"  Cost reduction: {(1 - avg_cost_b / max(avg_cost_a, 0.001)) * 100:.1f}%")
    print(f"  Node reduction:  {(1 - avg_exp_b / max(avg_exp_a, 0.001)) * 100:.1f}%")

    # Save
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(OUTPUT_DIR, f"mode{args.mode}_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "benchmark_results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "target",
                                                "expanded_A", "expanded_B",
                                                "cost_A", "cost_B",
                                                "time_A_ms", "time_B_ms"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  Results saved to: {out_dir}")

    # Summary CSV
    summary_path = os.path.join(out_dir, "benchmark_summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "ImprovedAStar", "AdaptiveQueueAwareAStar", "improvement_pct"])
        writer.writerow(["avg_expanded_nodes", f"{avg_exp_a:.1f}", f"{avg_exp_b:.1f}",
                         f"{(1 - avg_exp_b / max(avg_exp_a, 0.001)) * 100:.1f}"])
        writer.writerow(["avg_path_time_cost_s", f"{avg_cost_a:.2f}", f"{avg_cost_b:.2f}",
                         f"{(1 - avg_cost_b / max(avg_cost_a, 0.001)) * 100:.1f}"])
        writer.writerow(["avg_search_time_ms", f"{avg_time_a:.2f}", f"{avg_time_b:.2f}",
                         f"{(1 - avg_time_b / max(avg_time_a, 0.001)) * 100:.1f}"])
    print(f"  Summary saved to: {summary_path}")


def _build_population(mode):
    BASE = {
        "L2":  {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
        "L7":  {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
        "L16": {"platform_waiting": 42,  "hall_people": 15,  "transfer_people": 27},
        "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
        "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
    }
    pop, total = {}, 0
    for line, physics in net.TRAIN_PHYSICS.items():
        base = BASE[line]
        train_total = int(round(net._train_total_people(physics)))
        t1, t2 = (0, 0) if mode == 1 else (train_total, train_total)
        pop[line] = {"train_1": t1, "train_2": t2,
                      "platform_waiting": int(base["platform_waiting"]),
                      "hall_people": int(base["hall_people"]),
                      "transfer_people": int(base["transfer_people"])}
        total += sum(pop[line].values())
    return pop, total


if __name__ == "__main__":
    main()
