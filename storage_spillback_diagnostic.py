"""Run the three Mode-4 storage/spillback diagnostics requested in the audit."""

from __future__ import annotations

import csv
from pathlib import Path

import algorithm_comparison as comparison
import network as net


SCENARIOS = (
    ("A_strict_legacy_service_storage", "legacy", True),
    ("B_service_nodes_exempt", "exempt", True),
    ("C_no_spatial_spillback_diagnostic", "exempt", False),
)

SUMMARY_FIELDS = [
    "scenario", "algorithm", "completed", "termination_reason", "target_people",
    "evacuated_people", "remaining_people", "evacuation_time",
    "mean_station_throughput", "resource_queueing_time", "mean_resource_queue",
    "moderate_exposure", "severe_exposure", "runtime",
]

RESOURCE_FIELDS = [
    "resource_id", "resource_type", "capacity_per_second", "total_throughput",
    "peak_queue", "queueing_person_seconds", "mean_queue", "maximum_predicted_wait",
    "utilization", "first_queue_time", "last_queue_time", "associated_edges",
]

SPATIAL_FIELDS = [
    "node", "node_type", "effective_area", "storage_capacity", "peak_people",
    "peak_density", "time_at_receiving_limit", "blocked_or_rejected_inflow",
]


def _write_rows(path, fields, rows):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    comparison.MODE = 4
    population, total_people = comparison.build_population()
    base_graph = net.build_graph()
    base_graph.graph["split_l2_train_source_groups_by_zone"] = True
    net.write_resource_mapping_report(base_graph, "resource_mapping_report.md")

    summary_rows = []
    formal_results = {}
    for scenario, storage_mode, spillback_enabled in SCENARIOS:
        scenario_graph = base_graph.copy()
        scenario_graph.graph["density_dependent_flow"] = True
        scenario_graph.graph["spillback_enabled"] = spillback_enabled
        scenario_graph.graph["service_node_spatial_storage_mode"] = storage_mode
        print(f"\n=== {scenario} ===")

        for method, algorithm in (
            (net.PAPER_SINGLE_PATH_METHOD, "ImprovedAStar"),
            (net.OUR_SINGLE_PATH_METHOD, "AdaptiveQueueAwareAStar"),
        ):
            result = comparison.run_one(
                scenario_graph,
                population,
                method,
                algorithm,
                collect_detailed_series=False,
            )
            raw = result["_raw_metrics"]
            summary_rows.append({
                "scenario": scenario,
                "algorithm": algorithm,
                "completed": result["completed"],
                "termination_reason": result["termination_reason"],
                "target_people": result["target_people"],
                "evacuated_people": result["evacuated_people"],
                "remaining_people": result["remaining_people"],
                "evacuation_time": result["evacuation_time"],
                "mean_station_throughput": result["mean_station_throughput"],
                "resource_queueing_time": result["resource_queueing_time"],
                "mean_resource_queue": result["mean_resource_queue"],
                "moderate_exposure": result["moderate_congestion_exposure"],
                "severe_exposure": result["severe_congestion_exposure"],
                "runtime": result["wall_clock_runtime"],
            })
            if scenario == "B_service_nodes_exempt":
                formal_results[algorithm] = raw

    _write_rows("storage_spillback_diagnostic.csv", SUMMARY_FIELDS, summary_rows)
    for algorithm, raw in formal_results.items():
        label = "Improved" if algorithm == "ImprovedAStar" else "AA"
        _write_rows(
            f"bottleneck_resources_{label}.csv",
            RESOURCE_FIELDS,
            raw.get("bottleneck_resources", []),
        )
        _write_rows(
            f"spatial_bottlenecks_{label}.csv",
            SPATIAL_FIELDS,
            raw.get("spatial_bottlenecks", []),
        )

    print(f"\nCompleted six runs for {total_people} people.")


if __name__ == "__main__":
    main()
