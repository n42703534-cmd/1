import csv
import statistics
import sys
import time
import types
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def _import_network_modules():
    try:
        import network  # type: ignore
        import single_path_routing as spr  # type: ignore
        return network, spr
    except ModuleNotFoundError as exc:
        if exc.name != "pandas":
            raise
        pd = types.ModuleType("pandas")

        class _DummyDataFrame:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def to_csv(self, *args, **kwargs):
                raise RuntimeError("Dummy pandas.DataFrame cannot write CSV in this script.")

        pd.DataFrame = _DummyDataFrame
        sys.modules["pandas"] = pd
        import network  # type: ignore
        import single_path_routing as spr  # type: ignore
        return network, spr


network, spr = _import_network_modules()


OUTPUT_CASE_CSV = "156_L7_waiting_zone_algorithm_case_summary.csv"
OUTPUT_METHOD_CSV = "157_L7_waiting_zone_algorithm_summary_by_method.csv"
OUTPUT_PLOT = "158_L7_waiting_zone_algorithm_metrics.png"
OUTPUT_REPORT = "159_L7_waiting_zone_algorithm_report.md"

PLANNING_REPEAT = 100
EVACUEES = 100
LINE_ID = "L7"
METHODS = [
    ("ImprovedAStar", spr.PAPER_SINGLE_PATH_METHOD),
    ("AdaptiveQueueAwareAStar", spr.OUR_SINGLE_PATH_METHOD),
    ("OurSplitGuidance", spr.OUR_SPLIT_GUIDANCE_METHOD),
]


def _sorted_l7_waiting_origins(G):
    nodes = network._platform_waiting_zone_nodes(G, LINE_ID)
    nodes.sort(key=lambda n: int(G.nodes[n].get("car_index", 0)))
    return nodes


def _path_text(path):
    if not path:
        return "N/A"
    return " -> ".join(path)


def _facility_role_label(G, node):
    node_type = str(G.nodes[node].get("type", "")).lower()
    if node_type == "stair":
        return "stair"
    if node_type == "escalator":
        return "escalator"
    return node_type or "other"


def _build_branch_path_map(case_state, origin, method, shortest_dists):
    method = spr.normalize_method(method)
    if method != spr.OUR_SPLIT_GUIDANCE_METHOD:
        return {}

    candidates = network.split_router.select_candidate_paths(
        case_state,
        origin,
        method,
        shortest_dists,
        network.fruin_speed,
    )
    return {item["next_hop"]: item["path"] for item in candidates}


def _initial_split_details(case_state, origin, method):
    shortest_dists = dict(network.nx.all_pairs_dijkstra_path_length(case_state, weight="length"))
    branch_path_map = _build_branch_path_map(case_state, origin, method, shortest_dists)
    moves = [
        (u, v, int(amount))
        for u, v, amount in network.get_step_moves(case_state, method, shortest_dists)
        if u == origin and amount > 0
    ]

    if not moves:
        return {
            "initial_split_summary": "N/A",
            "initial_exit_breakdown": "N/A",
            "stair_people": 0,
            "escalator_people": 0,
            "split_branch_count": 0,
        }

    stair_people = 0
    escalator_people = 0
    exit_totals = {}
    branch_parts = []

    for _, next_hop, amount in moves:
        role = _facility_role_label(case_state, next_hop)
        if role == "stair":
            stair_people += amount
        elif role == "escalator":
            escalator_people += amount

        branch_path = branch_path_map.get(next_hop)
        if not branch_path:
            downstream = network.get_best_path_to_exit(case_state, next_hop, method, shortest_dists)
            if downstream:
                branch_path = [origin] + list(downstream)
            else:
                branch_path = [origin, next_hop]

        target_exit = branch_path[-1] if branch_path else "N/A"
        exit_totals[target_exit] = exit_totals.get(target_exit, 0) + amount
        branch_parts.append(f"{amount} -> {next_hop} -> {target_exit}")

    exit_parts = [f"{amount} -> {exit_name}" for exit_name, amount in sorted(exit_totals.items())]
    return {
        "initial_split_summary": "; ".join(branch_parts),
        "initial_exit_breakdown": "; ".join(exit_parts),
        "stair_people": stair_people,
        "escalator_people": escalator_people,
        "split_branch_count": len(moves),
    }


def _actual_split_details(case_state, origin, method, metrics):
    shortest_dists = dict(network.nx.all_pairs_dijkstra_path_length(case_state, weight="length"))
    branch_path_map = _build_branch_path_map(case_state, origin, method, shortest_dists)
    edge_stats = metrics.get("edge_stats", {})
    line_id = case_state.graph.get("_single_path_case_line", LINE_ID)

    stair_people = 0
    escalator_people = 0
    branch_parts = []
    branch_count = 0

    for next_hop in case_state.successors(origin):
        edge_key = network._edge_key(origin, next_hop)
        amount = int(round(float(edge_stats.get(edge_key, {}).get("flow_total", 0.0))))
        if amount <= 0:
            continue

        branch_count += 1
        role = _facility_role_label(case_state, next_hop)
        if role == "stair":
            stair_people += amount
        elif role == "escalator":
            escalator_people += amount

        branch_path = branch_path_map.get(next_hop)
        if not branch_path:
            downstream = network.get_best_path_to_exit(case_state, next_hop, method, shortest_dists)
            if downstream:
                branch_path = [origin] + list(downstream)
            else:
                branch_path = [origin, next_hop]

        target_exit = branch_path[-1] if branch_path else "N/A"
        branch_parts.append(f"{amount} -> {next_hop} -> {target_exit}")

    if branch_count <= 0:
        return _initial_split_details(case_state, origin, method)

    exit_totals = {}
    for exit_name, line_usage in metrics.get("exit_usage_by_line", {}).items():
        amount = int(round(float(line_usage.get(line_id, 0.0))))
        if amount > 0:
            exit_totals[exit_name] = amount

    exit_parts = [f"{amount} -> {exit_name}" for exit_name, amount in sorted(exit_totals.items())]
    return {
        "initial_split_summary": "; ".join(branch_parts),
        "initial_exit_breakdown": "; ".join(exit_parts),
        "stair_people": stair_people,
        "escalator_people": escalator_people,
        "split_branch_count": branch_count,
    }


def _average_planning_runtime(case_state, origin, method, repeats=PLANNING_REPEAT):
    shortest_dists = dict(network.nx.all_pairs_dijkstra_path_length(case_state, weight="length"))
    start = time.perf_counter()
    last_path = None
    for _ in range(repeats):
        last_path = network.get_best_path_to_exit(case_state, origin, method, shortest_dists)
    elapsed = time.perf_counter() - start
    return elapsed * 1000.0 / repeats, last_path


def _run_case_metrics(case_state, method, planned_path):
    start = time.perf_counter()
    metrics = network.run_simulation_for_existing_state(case_state, method=method)
    runtime_s = time.perf_counter() - start
    return metrics, runtime_s


def _write_case_csv(rows):
    fieldnames = [
        "origin",
        "method",
        "target_exit",
        "initial_path",
        "initial_split_summary",
        "initial_exit_breakdown",
        "stair_people",
        "escalator_people",
        "split_branch_count",
        "planning_runtime_ms_avg100",
        "simulation_runtime_s",
        "evacuation_time_s",
        "queueing_time_person_s",
        "congestion_exposure_time_person_s",
    ]
    with open(OUTPUT_CASE_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_method_csv(summary_rows):
    fieldnames = [
        "method",
        "cases",
        "avg_planning_runtime_ms_avg100",
        "avg_simulation_runtime_s",
        "avg_evacuation_time_s",
        "avg_queueing_time_person_s",
        "avg_congestion_exposure_time_person_s",
        "best_evacuation_case_count",
        "best_queue_case_count",
        "best_exposure_case_count",
    ]
    with open(OUTPUT_METHOD_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)


def _plot_metrics(rows, origins):
    methods = [name for name, _ in METHODS]
    x = np.arange(len(origins))
    width = 0.14
    colors = ["#4C78A8", "#72B7B2", "#F58518", "#E45756", "#54A24B"]

    metric_specs = [
        ("evacuation_time_s", "Evacuation Time (s)"),
        ("queueing_time_person_s", "Queueing Time (person-s)"),
        ("congestion_exposure_time_person_s", "Congestion Exposure (person-s)"),
        ("planning_runtime_ms_avg100", "Planning Runtime (ms, avg of 100)"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(17, 10))
    fig.suptitle("L7 Waiting-Zone Routing Comparison (100 evacuees per origin)", fontsize=18, fontweight="bold")
    axes = axes.flatten()

    for ax, (metric_key, title) in zip(axes, metric_specs):
        for idx, method in enumerate(methods):
            vals = []
            for origin in origins:
                row = next(r for r in rows if r["origin"] == origin and r["method"] == method)
                vals.append(float(row[metric_key]))
            ax.bar(
                x + (idx - (len(methods) - 1) / 2.0) * width,
                vals,
                width=width,
                label=method,
                color=colors[idx],
                edgecolor="black",
                linewidth=0.7,
            )
        ax.set_xticks(x)
        ax.set_xticklabels([origin.replace("Platform_L7_", "").replace("_Wait", "") for origin in origins], rotation=0)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_axisbelow(True)

    axes[0].legend(loc="upper left", fontsize=10)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(OUTPUT_PLOT, dpi=300, bbox_inches="tight")
    plt.close()


def _build_method_summary(case_rows, origins):
    methods = [name for name, _ in METHODS]
    best_time = {}
    best_queue = {}
    best_exposure = {}
    for origin in origins:
        subset = [r for r in case_rows if r["origin"] == origin]
        best_time[origin] = min(float(r["evacuation_time_s"]) for r in subset)
        best_queue[origin] = min(float(r["queueing_time_person_s"]) for r in subset)
        best_exposure[origin] = min(float(r["congestion_exposure_time_person_s"]) for r in subset)

    summary_rows = []
    for method in methods:
        subset = [r for r in case_rows if r["method"] == method]
        summary_rows.append({
            "method": method,
            "cases": len(subset),
            "avg_planning_runtime_ms_avg100": round(statistics.mean(float(r["planning_runtime_ms_avg100"]) for r in subset), 3),
            "avg_simulation_runtime_s": round(statistics.mean(float(r["simulation_runtime_s"]) for r in subset), 4),
            "avg_evacuation_time_s": round(statistics.mean(float(r["evacuation_time_s"]) for r in subset), 3),
            "avg_queueing_time_person_s": round(statistics.mean(float(r["queueing_time_person_s"]) for r in subset), 3),
            "avg_congestion_exposure_time_person_s": round(statistics.mean(float(r["congestion_exposure_time_person_s"]) for r in subset), 3),
            "best_evacuation_case_count": sum(1 for r in subset if float(r["evacuation_time_s"]) <= best_time[r["origin"]] + 1e-9),
            "best_queue_case_count": sum(1 for r in subset if float(r["queueing_time_person_s"]) <= best_queue[r["origin"]] + 1e-9),
            "best_exposure_case_count": sum(1 for r in subset if float(r["congestion_exposure_time_person_s"]) <= best_exposure[r["origin"]] + 1e-9),
        })
    return summary_rows


def _write_report(case_rows, summary_rows, origins):
    lines = []
    lines.append("# L7 Waiting-Zone Routing Comparison")
    lines.append("")
    lines.append(f"- Line: `{LINE_ID}`")
    lines.append(f"- Origins: `{', '.join(origin.replace('Platform_L7_', '').replace('_Wait', '') for origin in origins)}`")
    lines.append(f"- Evacuees per origin: `{EVACUEES}`")
    lines.append(f"- Methods: `{', '.join(name for name, _ in METHODS)}`")
    lines.append(f"- Planning runtime: average of `{PLANNING_REPEAT}` repeated route computations")
    lines.append("")
    lines.append("## Method Summary")
    lines.append("")
    for row in summary_rows:
        lines.append(
            f"- `{row['method']}`: planning `{row['avg_planning_runtime_ms_avg100']} ms`, "
            f"simulation `{row['avg_simulation_runtime_s']} s`, "
            f"evacuation `{row['avg_evacuation_time_s']} s`, "
            f"queueing `{row['avg_queueing_time_person_s']}`, "
            f"exposure `{row['avg_congestion_exposure_time_person_s']}`"
        )
    lines.append("")
    lines.append("## Per-Origin Details")
    lines.append("")
    for origin in origins:
        lines.append(f"### {origin}")
        subset = [r for r in case_rows if r["origin"] == origin]
        for row in subset:
            lines.append(
                f"- `{row['method']}`: target exit `{row['target_exit']}`, "
                f"path `{row['initial_path']}`, "
                f"first split `{row['initial_split_summary']}`, "
                f"stair `{row['stair_people']}` / escalator `{row['escalator_people']}`, "
                f"exit breakdown `{row['initial_exit_breakdown']}`, "
                f"planning `{row['planning_runtime_ms_avg100']} ms`, "
                f"simulation `{row['simulation_runtime_s']} s`, "
                f"evacuation `{row['evacuation_time_s']} s`, "
                f"queueing `{row['queueing_time_person_s']}`, "
                f"exposure `{row['congestion_exposure_time_person_s']}`"
            )
        lines.append("")
    Path(OUTPUT_REPORT).write_text("\n".join(lines), encoding="utf-8")


def main():
    G = network.build_graph()
    origins = _sorted_l7_waiting_origins(G)
    case_rows = []

    for origin in origins:
        case_spec = {
            "case_id": origin.replace("Platform_L7_", "").replace("_Wait", ""),
            "line": LINE_ID,
            "origin": origin,
            "start_role": "platform_waiting_zone",
        }

        for method_label, method_key in METHODS:
            planning_state = network.build_single_path_case_state(G, case_spec, evacuees=EVACUEES)
            planning_runtime_ms, planned_path = _average_planning_runtime(planning_state, origin, method_key)

            sim_state = network.build_single_path_case_state(G, case_spec, evacuees=EVACUEES)
            metrics, simulation_runtime_s = _run_case_metrics(sim_state, method_key, planned_path)
            split_details = _actual_split_details(sim_state, origin, method_key, metrics)

            case_rows.append({
                "origin": origin,
                "method": method_label,
                "target_exit": planned_path[-1] if planned_path else "N/A",
                "initial_path": _path_text(planned_path),
                "initial_split_summary": split_details["initial_split_summary"],
                "initial_exit_breakdown": split_details["initial_exit_breakdown"],
                "stair_people": split_details["stair_people"],
                "escalator_people": split_details["escalator_people"],
                "split_branch_count": split_details["split_branch_count"],
                "planning_runtime_ms_avg100": round(planning_runtime_ms, 4),
                "simulation_runtime_s": round(simulation_runtime_s, 4),
                "evacuation_time_s": round(float(metrics["time"]), 3),
                "queueing_time_person_s": round(float(metrics["queueing_time"]), 3),
                "congestion_exposure_time_person_s": round(float(metrics["congestion_exposure_time"]), 3),
            })

    summary_rows = _build_method_summary(case_rows, origins)
    _write_case_csv(case_rows)
    _write_method_csv(summary_rows)
    _plot_metrics(case_rows, origins)
    _write_report(case_rows, summary_rows, origins)

    print(f"Generated {OUTPUT_CASE_CSV}")
    print(f"Generated {OUTPUT_METHOD_CSV}")
    print(f"Generated {OUTPUT_PLOT}")
    print(f"Generated {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()
