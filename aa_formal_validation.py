"""Staged, fair validation for the reconstructed predictive AA.

Examples:
  python aa_formal_validation.py --mode 1
  python aa_formal_validation.py --mode 2 --gain-min 0.20
  python aa_formal_validation.py --mode 4 --gain-min 0.20
"""
import argparse
import csv
import json
from pathlib import Path

import algorithm_comparison as comparison
import network as net
import single_path_routing as spr


BASE_LOADS = comparison.BASE_LOADS


def population(mode):
    result = {}
    for line, physics in net.TRAIN_PHYSICS.items():
        train = int(round(net._train_total_people(physics)))
        result[line] = {
            "train_1": train if mode in (2, 4) else 0,
            "train_2": train if mode in (3, 4) else 0,
            **{key: int(value) for key, value in BASE_LOADS[line].items()},
        }
    return result


def quantile_time(metrics, percentage, initial):
    curve = metrics.get("evacuation_curve", {})
    times, remaining = curve.get("times", []), curve.get("remaining", [])
    initial = float(initial)
    target = initial * (1.0 - percentage / 100.0)
    for time_value, remaining_value in zip(times, remaining):
        if float(remaining_value) <= target + 0.5:
            return float(time_value)
    return ""


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(mode, gain_min, output):
    pop = population(mode)
    graph = net.build_graph()

    # 与正式场景B保持一致
    graph.graph["density_dependent_flow"] = True
    graph.graph["spillback_enabled"] = True
    graph.graph["service_node_spatial_storage_mode"] = "queue_area"

    if mode == 4:
        graph.graph["split_l2_train_source_groups_by_zone"] = True

    cases = [
    ("AdaptiveQueueAwareAStar", net.OUR_SINGLE_PATH_METHOD, gain_min),
    ]
    results = []
    for label, method, threshold in cases:
        print(f"Starting {label} (mode={mode}, g_min={gain_min})", flush=True)
        if threshold is not None:
            graph.graph["aa_reroute_gain_min"] = threshold
        result = comparison.run_one(
            graph, pop, method, label, collect_detailed_series=False
        )
        results.append(result)
        print(
            f"Finished {label}: completed={result['completed']} "
            f"remaining={result['remaining_people']} time={result['evacuation_time']}",
            flush=True,
        )

    output.mkdir(parents=True, exist_ok=True)
    formal_rows, prediction_rows, resource_rows, tail_rows = [], [], [], []
    for result in results:
        metrics = result["_raw_metrics"]
        diag = metrics.get("aa_diagnostics", {})
        row = {
            "scenario_mode": mode,
            "algorithm": result["method"],
            **{
                f"T{p}": quantile_time(metrics, p, result["target_people"])
                for p in (50, 80, 90, 95, 99, 100)
            },
            "T100_minus_T99": "",
            "resource_queue_person_seconds": metrics.get("resource_queue_person_seconds", 0),
            "unassigned_wait_person_seconds": metrics.get("unassigned_wait_person_seconds", 0),
            "spatial_blocked_person_seconds": metrics.get("spatial_blocked_person_seconds", 0),
            "stationary_person_seconds": metrics.get("stationary_person_seconds", 0),
            "in_transit_person_seconds": metrics.get("in_transit_person_seconds", 0),
            "total_system_person_seconds": metrics.get("total_system_person_seconds", 0),
            "moderate_congestion_exposure": metrics.get("moderate_congestion_exposure_time", 0),
            "peak_density": metrics.get("peak_density", 0),
            "total_distance": metrics.get("total_movement_distance", 0),
            "mean_moving_time": metrics.get("mean_moving_time", 0),
            "mean_total_evacuation_time": metrics.get("mean_total_evacuation_time", 0),
            "reroute_count": diag.get("reroute_count", 0),
            "effective_reroute_count": diag.get("effective_reroute_count", 0),
            "reverse_reroute_count": diag.get("reverse_reroute_count", 0),
            "A_B_A_cycle_count": diag.get("a_b_a_cycle_count", 0),
            "prediction_mean_absolute_error": (
                metrics.get("prediction_mean_absolute_error", 0)
                if result["method"] == "AdaptiveQueueAwareAStar" else ""
            ),
            "prediction_bias": (
                metrics.get("prediction_bias", 0)
                if result["method"] == "AdaptiveQueueAwareAStar" else ""
            ),
            "runtime_seconds": result.get("wall_clock_s", 0),
            "completed": metrics.get("completed", False),
        }
        if row["T100"] != "" and row["T99"] != "":
            row["T100_minus_T99"] = float(row["T100"]) - float(row["T99"])
        formal_rows.append(row)
        for item in metrics.get("aa_prediction_accuracy", []):
            prediction_rows.append({"scenario_mode": mode, "algorithm": result["method"], **item})
        for resource_id, item in metrics.get("resource_stats", {}).items():
            resource_rows.append({
                "scenario_mode": mode, "algorithm": result["method"],
                "resource_id": net.resource_id_text(resource_id), **item,
            })
        for line, clear_time in metrics.get("clearance_times_by_line", {}).items():
            tail_rows.append({
                "scenario_mode": mode, "algorithm": result["method"],
                "line": line, "clearance_time": clear_time,
                "T100": metrics.get("time", 0),
                "tail_gap": (
                    float(metrics.get("time", 0)) - float(clear_time)
                    if clear_time is not None else ""
                ),
            })

    write_csv(output / "aa_formal_comparison.csv", formal_rows, list(formal_rows[0]))
    prediction_fields = list(prediction_rows[0]) if prediction_rows else [
        "scenario_mode", "algorithm", "batch_id", "source_group", "resource_id",
        "predicted_time", "actual_time", "predicted_queue", "actual_queue", "error",
        "absolute_error",
    ]
    write_csv(output / "aa_prediction_accuracy.csv", prediction_rows, prediction_fields)
    resource_fields = sorted({key for row in resource_rows for key in row})
    write_csv(output / "aa_resource_utilization.csv", resource_rows, resource_fields)
    write_csv(output / "aa_tail_diagnostic.csv", tail_rows, list(tail_rows[0]) if tail_rows else [
        "scenario_mode", "algorithm", "line", "clearance_time", "T100", "tail_gap"
    ])
    (output / "run_config.json").write_text(json.dumps({
        "mode": mode, "gain_min": gain_min,
        "physical_parameters_modified": False,
        "algorithms": [case[0] for case in cases],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    print("=" * 60)
    print("AA 正式验证")
    print("1. Mode 1：常规突发")
    print("2. Mode 2：上行满载列车")
    print("3. Mode 3：下行满载列车")
    print("4. Mode 4：双向满载列车")
    print("=" * 60)

    while True:
        try:
            mode = int(input("请选择运行模式（1/2/3/4）：").strip())
            if mode in (1, 2, 3, 4):
                break
        except ValueError:
            pass

        print("输入无效，请输入 1、2、3 或 4。")

    while True:
        gain_input = input(
            "请输入 g_min（0、0.15或0.20，直接回车默认0.20）："
        ).strip()

        if gain_input == "":
            gain_min = 0.20
            break

        try:
            gain_min = float(gain_input)
        except ValueError:
            print("输入无效，请输入 0、0.15 或 0.20。")
            continue

        if gain_min in (0.0, 0.15, 0.20):
            break

        print("g_min 只允许输入 0、0.15 或 0.20。")

    output = Path("outputs/aa_formal_validation")

    run(
        mode,
        gain_min,
        output / f"mode{mode}_g{gain_min:.2f}",
    )
