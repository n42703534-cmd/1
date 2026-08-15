"""Formal scenario-B comparison for rolling-horizon mesoscopic routing."""

import csv
from pathlib import Path

import algorithm_comparison as comparison
import network as net


METHODS = (
    (net.PAPER_SINGLE_PATH_METHOD, "ImprovedAStar"),
    (net.spr.MESOSCOPIC_PHYSICAL_TIME_METHOD, "MesoscopicPhysicalTimeAStar"),
    (net.spr.MESOSCOPIC_CURRENT_QUEUE_METHOD, "MesoscopicCurrentQueueAwareAStar"),
    (net.OUR_SINGLE_PATH_METHOD, "LegacyAdaptiveQueueAwareAStar"),
)


def _write_csv(path, rows):
    rows = list(rows)
    if not rows:
        Path(path).write_text("", encoding="utf-8-sig")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _tail_events(events, count):
    selected = []
    remaining = count
    for event in reversed(sorted(events, key=lambda row: float(row.get("time", 0.0)))):
        if remaining <= 0:
            break
        amount = min(int(event.get("amount", 0)), remaining)
        row = dict(event)
        row["tail_selected_amount"] = amount
        selected.append(row)
        remaining -= amount
    return list(reversed(selected))


def main():
    comparison.MODE = 4
    population, total = comparison.build_population()
    base = net.build_graph()
    base.graph["density_dependent_flow"] = True
    base.graph["spillback_enabled"] = True
    base.graph["service_node_spatial_storage_mode"] = "queue_area"
    net.write_routing_decision_nodes_report(base)

    comparison_rows = []
    utilization_rows = []
    tail_rows = []
    for method, label in METHODS:
        print(f"\n=== {label} ===", flush=True)
        result = comparison.run_one(
            base,
            population,
            method,
            label,
            stop_at_time=6000.0,
            collect_detailed_series=False,
        )
        metrics = result["_raw_metrics"]
        curve = metrics.get("evacuation_curve", {})
        t50 = comparison.compute_Txx(curve, total, 50)
        t80 = comparison.compute_Txx(curve, total, 80)
        t90 = comparison.compute_Txx(curve, total, 90)
        t95 = comparison.compute_Txx(curve, total, 95)
        t99 = comparison.compute_Txx(curve, total, 99)
        t100 = float(metrics.get("time", 0.0))
        t_last100_start = comparison.compute_Txx(curve, total, 100 * (total - 100) / total)
        t_last10_start = comparison.compute_Txx(curve, total, 100 * (total - 10) / total)
        diagnostics = metrics.get("mesoscopic_diagnostics", {})
        comparison_rows.append({
            "algorithm": label,
            "completed": metrics.get("completed"),
            "termination_reason": metrics.get("termination_reason"),
            "remaining_people": metrics.get("remaining_people"),
            "T50": t50,
            "T80": t80,
            "T90": t90,
            "T95": t95,
            "T99": t99,
            "T100": t100,
            "T100_minus_T99": t100 - t99,
            "last_100_clearance_seconds": t100 - t_last100_start,
            "last_10_clearance_seconds": t100 - t_last10_start,
            "resource_queueing_person_seconds": metrics.get("resource_queueing_time", 0.0),
            "mean_resource_queue": metrics.get("resource_queueing_time", 0.0) / max(t100, 1.0),
            "total_movement_distance": metrics.get("total_movement_distance", 0.0),
            "mean_moving_time": metrics.get("mean_moving_time", 0.0),
            "mean_station_throughput": total / max(t100, 1.0),
            "peak_density": metrics.get("peak_density", 0.0),
            "moderate_3p0_exposure": metrics.get("moderate_congestion_exposure_time", 0.0),
            "internal_3p5_diagnostic_exposure": metrics.get("severe_congestion_exposure_time", 0.0),
            "path_decisions": diagnostics.get("decision_count", 0),
            "segment_commitments": diagnostics.get("segment_commitment_count", 0),
            "nondecision_replans": diagnostics.get("nondecision_replan_count", 0),
            "reroutes_after_rejection": diagnostics.get("reroute_after_rejection_count", 0),
            "wall_clock_runtime": result.get("wall_clock_runtime", 0.0),
            "exit_usage": "; ".join(
                f"{name}={int(value)}"
                for name, value in sorted(metrics.get("exit_usage", {}).items())
            ),
            "top_spatial_bottlenecks": "; ".join(
                f"{row.get('node')}:{float(row.get('blocked_or_rejected_inflow', 0)):.0f}"
                for row in metrics.get("spatial_bottlenecks", [])[:5]
            ),
        })
        for resource_id, stat in metrics.get("resource_stats", {}).items():
            row = {"algorithm": label, "resource_id": net.resource_id_text(resource_id)}
            for key in (
                "resource_type", "capacity_per_second", "total_throughput", "busy_time",
                "total_available_integer_capacity", "used_integer_capacity",
                "unused_integer_capacity", "upstream_reachable_demand_person_steps",
                "idle_time_with_reachable_demand", "peak_queue", "mean_queue", "utilization",
            ):
                row[key] = stat.get(key, 0)
            utilization_rows.append(row)
        events = metrics.get("evacuation_arrival_events", [])
        for tail_size in (100, 10):
            for event in _tail_events(events, tail_size):
                tail_rows.append({"algorithm": label, "tail_size": tail_size, **event})

    _write_csv("mesoscopic_algorithm_comparison.csv", comparison_rows)
    _write_csv("resource_utilization_comparison.csv", utilization_rows)
    _write_csv("tail_evacuation_diagnostic.csv", tail_rows)
    print("\nWrote mesoscopic comparison diagnostics.", flush=True)


if __name__ == "__main__":
    main()
