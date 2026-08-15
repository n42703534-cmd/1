"""
算法对比：AdaptiveQueueAwareAStar vs ImprovedAStar
基于多目标框架评估解质量、路径稳定性、计算开销、系统效果。

对标 ETACO (Yang et al., 2025) 的评价体系：
  OV  = 仿真总目标函数值
  OR  = OV 改善率 (OV_baseline - OV_our) / OV_baseline × 100%
  路径稳定性 = 切换次数 / (源节点数 × 时间步数)
"""

from __future__ import annotations
4
import csv
import copy
import hashlib
import io
import json
import math
import re
import sys
import time
import types
from pathlib import Path

# ---------- noop matplotlib stub (headless 兼容) ----------
def _bootstrap():
    import importlib.util
    if importlib.util.find_spec("matplotlib") is None:
        _matplotlib = types.ModuleType("matplotlib")
        _pyplot = types.ModuleType("matplotlib.pyplot")
        _patches = types.ModuleType("matplotlib.patches")
        for _m in [_matplotlib, _pyplot, _patches]:
            setattr(_m, "__path__", [])
        _pyplot.figure = lambda *a, **kw: None
        _pyplot.subplots = lambda *a, **kw: (None, None)
        _pyplot.plot = lambda *a, **kw: None
        _pyplot.bar = lambda *a, **kw: None
        _pyplot.savefig = lambda *a, **kw: None
        _pyplot.close = lambda *a, **kw: None
        _pyplot.tight_layout = lambda *a, **kw: None
        _pyplot.grid = lambda *a, **kw: None
        _pyplot.xlabel = lambda *a, **kw: None
        _pyplot.ylabel = lambda *a, **kw: None
        _pyplot.title = lambda *a, **kw: None
        _pyplot.legend = lambda *a, **kw: None
        _pyplot.suptitle = lambda *a, **kw: None
        _pyplot.rcParams = {}
        _pyplot.gca = lambda *a, **kw: None
        _pyplot.gcf = lambda *a, **kw: None
        _patches.Patch = object
        _matplotlib.pyplot = _pyplot
        _matplotlib.patches = _patches
        sys.modules["matplotlib"] = _matplotlib
        sys.modules["matplotlib.pyplot"] = _pyplot
        sys.modules["matplotlib.patches"] = _patches


_bootstrap()

import networkx as nx
import network as net
import single_path_routing as spr

# ---------- 仿真参数 ----------
MODE = 1  # mode1 常规突发
TARGET_TIME = 600  # 测试用，完整仿真改为 6000

MODEL_REVISION = "arrival-service-predictive-v1-gate-buffer-crossline-commit-20260804"
EXPERIMENT_CHANGE_LOG = [
    "Formal metric cleanup: removed non-discriminative high-density exposure and overlapping spatial-blocked waiting from formal comparisons; simulation accounting is unchanged.",
    "Efficiency audit: retained the exact per-A* density cache, simulation-step edge records, lower-bound pruning, and same-path evaluation reuse already present in formal AA.",
]
J_SCORING_MODE = "high_load_v2"
J_HIGH_LOAD_REFERENCES = {
    "t100_s": 1900.0,
    "r_area_s_per_person": 500.0,
    "queue_s_per_person": 35.0,
    "exit_hhi": 0.10,
}
J_HIGH_LOAD_WEIGHTS = {
    "t100": 0.20,
    "r_area": 0.25,
    "queue": 0.20,
    "hhi": 0.15,
}

BASE_LOADS = {
    "L2":  {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
    "L7":  {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
    "L16": {"platform_waiting": 42,  "hall_people": 15,  "transfer_people": 27},
    "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
    "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
}


def build_population():
    """构建 mode1 客流"""
    pop = {}
    total = 0
    for line, physics in net.TRAIN_PHYSICS.items():
        base = BASE_LOADS[line]
        train_total = int(round(net._train_total_people(physics)))
        if MODE == 1:
            t1, t2 = 0, 0
        else:
            t1, t2 = train_total, train_total
        pop[line] = {
            "train_1": t1,
            "train_2": t2,
            "platform_waiting": int(base["platform_waiting"]),
            "hall_people": int(base["hall_people"]),
            "transfer_people": int(base["transfer_people"]),
        }
        total += sum(pop[line].values())
    return pop, total


def compute_or(ov_baseline: float, ov_our: float) -> float:
    """OV 改善率"""
    if ov_baseline <= 0:
        return 0.0
    return (ov_baseline - ov_our) / ov_baseline * 100.0


def compute_exit_gini(exit_usage: dict) -> float:
    """出口使用 Gini 系数（0=完全均衡, 1=完全不均衡）"""
    # Keep zero-use exits in the evaluation population.  Dropping them would
    # incorrectly reward a method that concentrates everyone into only a few
    # of the exits available in the shared simulation graph.
    values = sorted(max(float(v), 0.0) for v in exit_usage.values())
    n = len(values)
    if n <= 1:
        return 0.0
    total = sum(values)
    if total <= 0:
        return 0.0
    cumulative = 0.0
    gini_sum = 0.0
    for i, v in enumerate(values):
        cumulative += v / total
        gini_sum += (i + 1) * (v / total)
    return (2 * gini_sum - n - 1) / n


def compute_jain_index(values) -> float:
    values = [max(float(value), 0.0) for value in values]
    squared_sum = sum(value * value for value in values)
    if not values or squared_sum <= 0.0:
        return 0.0
    return sum(values) ** 2 / (len(values) * squared_sum)


def compute_Txx(evac_curve: dict, total_people: float, pct: float) -> float:
    """疏散完成 pct% 的时间（T50, T80, T95, T100）"""
    if total_people <= 0:
        return 0.0
    target_remaining = total_people * (1.0 - pct / 100.0)
    times = evac_curve.get("times", [])
    remaining = evac_curve.get("remaining", [])
    if not times or not remaining:
        return 0.0
    for t, r in zip(times, remaining):
        if r <= target_remaining + 0.5:
            return float(t)
    return float(times[-1]) if times else 0.0


def compute_line_t95(metrics: dict) -> dict[str, float | None]:
    """Return event-weighted T95 for each source line."""
    events_by_line = {}
    for event in metrics.get("evacuation_arrival_events", []):
        source_group = str(event.get("source_group", ""))
        line_id, _, _ = net._parse_source_group_id(source_group)
        amount = max(float(event.get("amount", 0.0)), 0.0)
        if line_id not in net.ALL_LINE_IDS or amount <= 0.0:
            continue
        events_by_line.setdefault(line_id, []).append(
            (float(event.get("time", 0.0)), amount)
        )

    result = {}
    for line_id in net.ALL_LINE_IDS:
        events = sorted(events_by_line.get(line_id, []))
        total = sum(amount for _, amount in events)
        if total <= 0.0:
            result[line_id] = None
            continue
        threshold = 0.95 * total
        cumulative = 0.0
        result[line_id] = events[-1][0]
        for event_time, amount in events:
            cumulative += amount
            if cumulative + 1e-9 >= threshold:
                result[line_id] = event_time
                break
    return result


def compute_R_area(evac_curve: dict, total_people: float) -> float:
    """剩余人数曲线下面积（归一化：面积/总人数，越小越好）"""
    times = evac_curve.get("times", [])
    remaining = evac_curve.get("remaining", [])
    if len(times) < 2 or total_people <= 0:
        return 0.0
    area = 0.0
    for i in range(1, len(times)):
        dt = times[i] - times[i - 1]
        avg_r = (remaining[i] + remaining[i - 1]) / 2.0
        area += avg_r * dt
    return area / total_people  # 归一化：平均每人延迟秒数


def compute_composite_J(metrics: dict, total_people: float) -> dict:
    """Deprecated compatibility score; excluded from formal comparisons."""
    evac_curve = metrics.get("evacuation_curve", {})
    t100 = metrics.get("time", 0.0)
    t50 = compute_Txx(evac_curve, total_people, 50)
    t80 = compute_Txx(evac_curve, total_people, 80)
    t95 = compute_Txx(evac_curve, total_people, 95)
    t99 = compute_Txx(evac_curve, total_people, 99)
    r_area = compute_R_area(evac_curve, total_people)
    queue = metrics.get("queueing_time", 0.0)
    exit_usage = metrics.get("exit_usage", {})
    hhi = sum((float(v) / max(total_people, 1)) ** 2 for v in exit_usage.values())

    scoring_mode = J_SCORING_MODE if MODE == 4 else "legacy_600s"
    if scoring_mode == "legacy_600s":
        w = {"t100": 0.35, "queue": 0.25, "hhi": 0.15}
        components = {
            "t100": w["t100"] * t100 / 600.0,
            "queue": w["queue"] * queue / max(total_people * 600.0, 1),
            "hhi": w["hhi"] * hhi * 10.0,
        }
    else:
        refs = J_HIGH_LOAD_REFERENCES
        w = J_HIGH_LOAD_WEIGHTS
        components = {
            "t100": w["t100"] * t100 / refs["t100_s"],
            "r_area": w["r_area"] * r_area / refs["r_area_s_per_person"],
            "queue": w["queue"] * (queue / max(total_people, 1.0)) / refs["queue_s_per_person"],
            "hhi": w["hhi"] * hhi / refs["exit_hhi"],
        }
    j_score = sum(components.values())
    return {
        "t50": t50, "t80": t80, "t95": t95, "t99": t99, "t100": t100,
        "r_area": r_area,
        "queue_time": queue,
        "hhi": hhi, "j_score": j_score,
        "j_version": scoring_mode,
        "j_components": components,
    }


def format_pct(value: float) -> str:
    if abs(value) < 0.01:
        return " 0.0%"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def run_one(
    G_base,
    pop_dict,
    method,
    method_name,
    *,
    stop_at_time=6000.0,
    collect_detailed_series=False,
    run_directory=None,
):
    """运行一次仿真，返回核心指标"""
    G = copy.deepcopy(G_base)
    # Pathfinder export observes only actually accepted moves. Route tracing is
    # enabled for both formal comparison methods and is never consulted by
    # routing, capacity, receiving, or movement execution.
    G.graph["_track_executed_routes"] = method in {
        net.PAPER_SINGLE_PATH_METHOD,
        net.OUR_SINGLE_PATH_METHOD,
    }
    if run_directory is not None:
        run_directory = Path(run_directory)
        run_directory.mkdir(parents=True, exist_ok=True)
        G.graph["_run_log_path"] = str(run_directory / "run.log")
    net.init_people(G, pop_dict)
    targets = net._infer_target_by_line_from_graph_state(G)
    sg_totals = net._source_group_totals_from_graph(G)
    initial_ppl = sum(G.nodes[n].get("people", 0) for n in G.nodes())
    t0 = time.perf_counter()
    metrics = net._run_simulation_for_metrics_core(
        G,
        method,
        targets,
        stop_at_time=stop_at_time,
        collect_detailed_series=collect_detailed_series,
    )
    metrics["source_group_totals"] = sg_totals
    wall_clock = time.perf_counter() - t0
    final_ppl = sum(G.nodes[n].get("people", 0) for n in G.nodes())
    total_evac = sum(float(v) for v in metrics.get("exit_usage", {}).values())
    evacuation_time = float(metrics.get("time", 0.0))
    resource_queueing_time = float(metrics.get("resource_queueing_time", 0.0))
    stationary_time = float(
        metrics.get("stationary_person_seconds", metrics.get("queueing_time", 0.0))
    )
    summary = {
        "algorithm": method_name,
        "target_people": initial_ppl,
        "evacuated_people": total_evac,
        "remaining_people": float(metrics.get("remaining_people", initial_ppl - total_evac)),
        "completed": bool(metrics.get("completed", False)),
        "termination_reason": metrics.get("termination_reason", "unknown"),
        "evacuation_time": evacuation_time,
        "mean_station_throughput": total_evac / evacuation_time if evacuation_time > 0 else 0.0,
        "cumulative_stationary_person_seconds": stationary_time,
        "mean_stationary_time_seconds_per_person": (
            stationary_time / initial_ppl if initial_ppl > 0 else 0.0
        ),
        "diagnostic_resource_queueing_person_seconds": resource_queueing_time,
        "mean_resource_queue": resource_queueing_time / evacuation_time if evacuation_time > 0 else 0.0,
        "exit_load_jain_index": float(metrics.get("exit_load_jain_index", 0.0)),
        "key_facility_load_jain_index": float(
            metrics.get("key_facility_load_jain_index", 0.0)
        ),
        "wall_clock_runtime": wall_clock,
    }
    if run_directory is not None:
        with (run_directory / "run.log").open("a", encoding="utf-8") as log_handle:
            log_handle.write(
                f"completed method={method_name} sim_time={evacuation_time:.1f}s "
                f"wall_clock={wall_clock:.2f}s evacuated={total_evac:.0f} "
                f"remaining={metrics.get('remaining_people', 0.0):.0f}\n"
            )
    print(
        f"    algorithm={method_name} target_people={initial_ppl:.0f} "
        f"evacuated_people={total_evac:.0f} "
        f"remaining_people={summary['remaining_people']:.0f} "
        f"completed={summary['completed']} "
        f"termination_reason={summary['termination_reason']} "
        f"T100_seconds={evacuation_time:.1f} "
                f"cumulative_stationary_person_seconds={stationary_time:.1f} "
        f"wall_clock_runtime_seconds={wall_clock:.2f}"
    )

    exit_usage = metrics.get("exit_usage", {})
    eval_metrics = compute_composite_J(metrics, initial_ppl)
    active_person_seconds = eval_metrics["r_area"] * max(initial_ppl, 0.0)
    effective_evacuation_speed = (
        float(metrics.get("effective_evacuation_speed", 0.0))
        if "effective_evacuation_speed" in metrics
        else (
            metrics.get("total_movement_distance", 0.0) / active_person_seconds
            if active_person_seconds > 0 else 0.0
        )
    )

    return {
        "method": method_name,
        "evacuation_time": metrics["time"],
        "eval": eval_metrics,
        "queueing_time": metrics["queueing_time"],
        "stationary_time": stationary_time,
        "resource_queueing_time": metrics.get("resource_queueing_time", 0.0),
        # Diagnostic-only component already represented within total
        # waiting/queueing accounting; not an independent formal performance metric.
        "_diagnostic_spatial_blocked_person_seconds": metrics.get(
            "spatial_blocked_exposure_person_seconds",
            metrics.get("spatial_blocked_person_seconds", 0.0),
        ),
        "_diagnostic_high_density_exposure_person_seconds": metrics.get(
            "high_density_exposure_person_seconds", 0.0
        ),
        "peak_density": metrics["peak_density"],
        "peak_overflow_queue": metrics.get("peak_overflow_queue", 0.0),
        "avg_speed": metrics.get("moving_average_speed", metrics["avg_speed"]),
        "moving_average_speed": metrics.get("moving_average_speed", metrics["avg_speed"]),
        "effective_evacuation_speed": effective_evacuation_speed,
        "edge_traversal_avg_speed": metrics.get(
            "edge_traversal_average_speed",
            metrics.get("edge_traversal_avg_speed", 0.0),
        ),
        "total_movement_distance": metrics.get("total_movement_distance", 0.0),
        "moving_person_seconds": metrics.get("moving_person_seconds", 0.0),
        "total_system_person_seconds": metrics.get("total_system_person_seconds", 0.0),
        "mean_moving_time": metrics.get("mean_moving_time", 0.0),
        "mean_queueing_time": metrics.get("mean_queueing_time", 0.0),
        "mean_stationary_time": (
            stationary_time / initial_ppl if initial_ppl > 0 else 0.0
        ),
        "mean_total_evacuation_time": metrics.get("mean_total_evacuation_time", 0.0),
        "exit_gini": compute_exit_gini(exit_usage),
        "exit_load_jain_index": float(metrics.get("exit_load_jain_index", 0.0)),
        "key_facility_load_jain_index": float(
            metrics.get("key_facility_load_jain_index", 0.0)
        ),
        "wall_clock_s": wall_clock,
        **summary,
        "exit_usage": exit_usage,
        "clearance_times": metrics.get("clearance_times_by_line", {}),
        "line_t95": compute_line_t95(metrics),
        "_simulation_graph": (
            G
            if method in {
                net.PAPER_SINGLE_PATH_METHOD,
                net.OUR_SINGLE_PATH_METHOD,
            }
            else None
        ),
        "_raw_metrics": metrics,
    }


def save_all_results(results: list[dict], pop_dict: dict, output_dir: str, scenario_name: str):
    """保存所有结果到 output_dir 下的多个 CSV 文件。"""
    import os, datetime
    os.makedirs(output_dir, exist_ok=True)

    def _diagnostic_label(method_name):
        if method_name == "ImprovedAStar":
            return "Improved"
        if method_name == "AdaptiveQueueAwareAStar":
            return "AA"
        return method_name.replace(" ", "_")

    resource_fields = [
        "resource_id", "resource_type", "capacity_per_second", "total_throughput",
        "peak_queue", "queueing_person_seconds", "mean_queue", "maximum_predicted_wait",
        "utilization", "first_queue_time", "last_queue_time", "associated_edges",
    ]
    spatial_fields = [
        "node", "node_type", "effective_area", "storage_capacity", "peak_people",
        "peak_density", "time_at_receiving_limit", "blocked_or_rejected_inflow",
    ]
    for result in results:
        raw = result["_raw_metrics"]
        label = _diagnostic_label(result["method"])
        with open(
            os.path.join(output_dir, f"bottleneck_resources_{label}.csv"),
            "w", newline="", encoding="utf-8-sig",
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=resource_fields)
            writer.writeheader()
            writer.writerows(raw.get("bottleneck_resources", []))
        with open(
            os.path.join(output_dir, f"spatial_bottlenecks_{label}.csv"),
            "w", newline="", encoding="utf-8-sig",
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=spatial_fields)
            writer.writeheader()
            writer.writerows(raw.get("spatial_bottlenecks", []))

    # ── 1. summary_metrics.csv ──
    with open(os.path.join(output_dir, "summary_metrics.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "method", "target_people", "evacuated_people", "remaining_people",
            "completed", "termination_reason", "T95_seconds", "T100_seconds",
            "cumulative_stationary_person_seconds",
            "mean_stationary_time_seconds_per_person",
            "effective_evacuation_speed_m_per_s",
            "mean_total_evacuation_time_seconds_per_person",
            "mean_station_throughput_people_per_second",
            "moving_average_speed_m_per_s",
            "edge_traversal_average_speed_m_per_s",
            "mean_moving_time_seconds_per_person", "total_movement_distance_m",
            "exit_load_jain_index", "key_facility_load_jain_index",
            "wall_clock_runtime_seconds",
        ])
        for r in results:
            e = r["eval"]
            writer.writerow([
                r["method"],
                round(r["target_people"], 1), round(r["evacuated_people"], 1),
                round(r["remaining_people"], 1), r["completed"], r["termination_reason"],
                round(e["t95"], 2), round(e["t100"], 2),
                round(r["stationary_time"], 1), round(r["mean_stationary_time"], 6),
                round(r["effective_evacuation_speed"], 4),
                round(r["mean_total_evacuation_time"], 6),
                round(r["mean_station_throughput"], 6),
                round(r["moving_average_speed"], 4),
                round(r["edge_traversal_avg_speed"], 4),
                round(r["mean_moving_time"], 6),
                round(r["total_movement_distance"], 6),
                round(r["exit_load_jain_index"], 6),
                round(r["key_facility_load_jain_index"], 6),
                round(r["wall_clock_s"], 2),
            ])
    print(f"  [OK] summary_metrics.csv")

    # ── 2. improvement_vs_baseline.csv ──
    if len(results) >= 2:
        baseline = results[0]
        with open(os.path.join(output_dir, "improvement_vs_baseline.csv"), "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "baseline", "ours", "improvement_pct"])
            for key, label in [
                ("t95", "T95_seconds"), ("t100", "T100_seconds"),
                ("stationary_time", "cumulative_stationary_person_seconds"),
                ("mean_stationary_time", "mean_stationary_time_seconds_per_person"),
                ("effective_evacuation_speed", "effective_evacuation_speed_m_per_s"),
                ("moving_average_speed", "moving_average_speed_m_per_s"),
                ("edge_traversal_avg_speed", "edge_traversal_average_speed_m_per_s"),
                ("exit_load_jain_index", "exit_load_jain_index"),
                ("key_facility_load_jain_index", "key_facility_load_jain_index"),
                ("wall_clock_s", "wall_clock_runtime_seconds"),
            ]:
                b_val = baseline["eval"][key] if key in baseline["eval"] else baseline.get(key, 0)
                for r in results[1:]:
                    o_val = r["eval"][key] if key in r["eval"] else r.get(key, 0)
                    higher_is_better = key in {
                        "effective_evacuation_speed", "moving_average_speed",
                        "edge_traversal_avg_speed", "exit_load_jain_index",
                        "key_facility_load_jain_index"
                    }
                    imp = (
                        (o_val - b_val) / max(abs(b_val), 0.001) * 100
                        if higher_is_better
                        else (b_val - o_val) / max(abs(b_val), 0.001) * 100
                    )
                    writer.writerow([f"{label} ({r['method']})", round(b_val, 2), round(o_val, 2), round(imp, 2)])
        print(f"  [OK] improvement_vs_baseline.csv")

    # ── 3. line_clearance.csv ──
    with open(os.path.join(output_dir, "line_clearance.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        for r in results:
            clearances = r.get("clearance_times", {})
            finite = [
                (line, float(value)) for line, value in clearances.items()
                if value is not None
            ]
            last_line = max(finite, key=lambda item: item[1])[0] if finite else ""
            if f.tell() == 0:
                writer.writerow([
                    "method", "line", "T95_seconds",
                    "clearance_time_seconds", "is_last_clearance_line",
                ])
            for line in sorted(clearances):
                clearance = clearances.get(line)
                writer.writerow([
                    r["method"], line,
                    r.get("line_t95", {}).get(line, ""),
                    "" if clearance is None else round(clearance, 1),
                    line == last_line,
                ])
    print(f"  [OK] line_clearance.csv")

    # ── 4. exit_usage.csv ──
    with open(os.path.join(output_dir, "exit_usage.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        methods = [r["method"] for r in results]
        writer.writerow(["exit"] + methods + [f"{m}_pct" for m in methods])
        all_exits = set()
        for r in results:
            all_exits.update(r.get("exit_usage", {}).keys())
        totals = {r["method"]: max(sum(r["exit_usage"].values()), 1) for r in results}
        for ext in sorted(all_exits):
            row = [ext]
            for r in results:
                row.append(round(r["exit_usage"].get(ext, 0), 1))
            for r in results:
                row.append(round(r["exit_usage"].get(ext, 0) / totals[r["method"]] * 100, 2))
            writer.writerow(row)
    print(f"  [OK] exit_usage.csv")

    # ── 5. facility_throughput.csv ──
    def _node_throughput(edge_flows):
        """Count arrivals at each node once (not both incident edge ends)."""
        tp = {}
        for ek, flow in edge_flows.items():
            parts = ek.split("->")
            if len(parts) == 2:
                v = parts[1].strip(); tp[v] = tp.get(v, 0.0) + flow
        return tp

    G_ref = net.build_graph()
    net.write_resource_mapping_report(
        G_ref,
        os.path.join(output_dir, "resource_mapping_report.md"),
    )
    def _node_type(name):
        if name in G_ref.nodes:
            return G_ref.nodes[name].get("type", "")
        return ""

    with open(os.path.join(output_dir, "facility_throughput.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        methods = [r["method"] for r in results]
        writer.writerow(["facility", "type", "total_flow_all_methods"] + methods)
        all_tp = {}
        for r in results:
            tp = _node_throughput(r["_raw_metrics"].get("edge_flow_totals", {}))
            for node, flow in tp.items():
                if node not in all_tp:
                    all_tp[node] = {}
                all_tp[node][r["method"]] = flow
        total_by_node = {n: sum(vals.values()) for n, vals in all_tp.items()}
        for node in sorted(all_tp.keys(), key=lambda n: -total_by_node.get(n, 0)):
            nt = _node_type(node)
            row = [node, nt, round(total_by_node[node], 1)]
            for r in results:
                row.append(round(all_tp[node].get(r["method"], 0), 1))
            writer.writerow(row)
    print(f"  [OK] facility_throughput.csv")

    with open(os.path.join(output_dir, "load_balance.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "item", "ImprovedAStar", "AdaptiveQueueAwareAStar"])
        by_method = {r["method"]: r for r in results}
        baseline = by_method.get("ImprovedAStar", results[0])
        adaptive = by_method.get("AdaptiveQueueAwareAStar", results[-1])
        for exit_name in sorted(set(baseline["exit_usage"]) | set(adaptive["exit_usage"])):
            writer.writerow(["exit", exit_name, baseline["exit_usage"].get(exit_name, 0.0), adaptive["exit_usage"].get(exit_name, 0.0)])
        baseline_facilities = baseline["_raw_metrics"].get("key_facility_throughput", {})
        adaptive_facilities = adaptive["_raw_metrics"].get("key_facility_throughput", {})
        for facility in sorted(set(baseline_facilities) | set(adaptive_facilities)):
            writer.writerow(["key_facility", facility, baseline_facilities.get(facility, 0.0), adaptive_facilities.get(facility, 0.0)])
        writer.writerow(["exit_jain", "ALL", baseline["exit_load_jain_index"], adaptive["exit_load_jain_index"]])
        writer.writerow(["key_facility_jain", "ALL", baseline["key_facility_load_jain_index"], adaptive["key_facility_load_jain_index"]])
    print(f"  [OK] load_balance.csv")

    # ── 6. route_chain.csv ──
    with open(os.path.join(output_dir, "route_chain.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["source_group", "method", "chain_type", "node", "people"])
        for r in results:
            raw = r["_raw_metrics"]
            nt_sg = raw.get("node_throughput_by_sg", {})
            exit_sg = raw.get("exit_usage_by_source_group", {})
            all_sg = set()
            for nsg in nt_sg.values():
                all_sg.update(nsg.keys())
            for esg in exit_sg.values():
                all_sg.update(esg.keys())
            for sg in sorted(all_sg):
                # intermediate facilities
                for fac, sg_map in nt_sg.items():
                    if sg in sg_map and sg_map[sg] > 0.5:
                        writer.writerow([sg, r["method"], "facility", fac, round(sg_map[sg], 1)])
                # exits
                for ext, sg_map in exit_sg.items():
                    if sg in sg_map and sg_map[sg] > 0.5:
                        writer.writerow([sg, r["method"], "exit", ext, round(sg_map[sg], 1)])
    print(f"  [OK] route_chain.csv")

    # ── 7. exit_by_source_group.csv (兼容 pathfinder_inject.py) ──
    rows = []
    for r in results:
        method_label = r["method"]
        raw = r["_raw_metrics"]
        exit_by_sg = raw.get("exit_usage_by_source_group", {})
        source_group_totals = raw.get("source_group_totals", {})

        for exit_name, sg_map in exit_by_sg.items():
            for sg_id, people in sg_map.items():
                if float(people) <= 0:
                    continue
                line_id, source_type, zone_name = net._parse_source_group_id(sg_id)
                total_sg = float(source_group_totals.get(sg_id, people))
                share = float(people) / max(total_sg, 0.001)
                rows.append({
                    "method_label": method_label,
                    "source_group": sg_id,
                    "line": line_id,
                    "source_type": source_type,
                    "source_zone": zone_name,
                    "configured_people": int(round(total_sg)),
                    "evacuated_people": int(round(total_sg)),
                    "exit_name": exit_name,
                    "people": round(float(people), 1),
                    "share_within_group": round(share, 4),
                })

    with open(os.path.join(output_dir, "exit_by_source_group.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "method_label", "source_group", "line", "source_type", "source_zone",
            "configured_people", "evacuated_people", "exit_name", "people", "share_within_group",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"  [OK] exit_by_source_group.csv ({len(rows)} 行)")

    # ── 8. README.txt ──
    with open(os.path.join(output_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(f"Model revision: {MODEL_REVISION}\n")
        f.write(f"Network module: {os.path.abspath(net.__file__)}\n")
        f.write("Formal comparison reports raw interpretable metrics; the deprecated composite score is omitted.\n")
        f.write(f"算法对比实验输出\n")
        f.write(f"场景: {scenario_name}\n")
        f.write(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"\n文件说明:\n")
        f.write(f"  summary_metrics.csv          - 综合指标汇总\n")
        f.write(f"  improvement_vs_baseline.csv  - 相对baseline改善率\n")
        f.write(f"  line_clearance.csv           - 各线路清空时间\n")
        f.write(f"  exit_usage.csv               - 出口使用分布\n")
        f.write(f"  facility_throughput.csv      - 各设施通过人数\n")
        f.write(f"  route_chain.csv              - 路由链路分解\n")
        f.write(f"  exit_by_source_group.csv     - 按source group的出口分布\n")
    print(f"  [OK] README.txt")

    if len(results) >= 2:
        baseline, adaptive = results[0], results[1]

        def _improvement(baseline_value, adaptive_value, higher_is_better=False):
            denominator = max(abs(float(baseline_value)), 1e-9)
            delta = adaptive_value - baseline_value if higher_is_better else baseline_value - adaptive_value
            return 100.0 * delta / denominator

        report_metrics = [
            ("T95 (s)", baseline["eval"]["t95"], adaptive["eval"]["t95"], False),
            ("T100 (s)", baseline["eval"]["t100"], adaptive["eval"]["t100"], False),
            ("Cumulative stationary time (person*s)", baseline["stationary_time"], adaptive["stationary_time"], False),
            ("Mean stationary time (s/person)", baseline["mean_stationary_time"], adaptive["mean_stationary_time"], False),
            ("Effective evacuation speed (m/s)", baseline["effective_evacuation_speed"], adaptive["effective_evacuation_speed"], True),
            ("Moving average speed (m/s)", baseline["moving_average_speed"], adaptive["moving_average_speed"], True),
            ("Exit-load Jain index", baseline["exit_load_jain_index"], adaptive["exit_load_jain_index"], True),
            ("Key-facility-load Jain index", baseline["key_facility_load_jain_index"], adaptive["key_facility_load_jain_index"], True),
            ("Wall-clock runtime (s)", baseline["wall_clock_s"], adaptive["wall_clock_s"], False),
        ]
        report_lines = [
            "# Mode 4 formal comparison report", "",
            "## Scope and definitions", "",
            "- Population: 17,905; AA gain_min: 0.20; only ImprovedAStar and AdaptiveQueueAwareAStar are compared.",
            "- `effective_evacuation_speed_m_per_s` is the primary speed metric. Moving and edge-traversal average speeds are motion-state diagnostics only.",
            "- High-density exposure was removed from the formal comparison because the configured density cap equals the exposure threshold and the observed exposure is dominated by the common initial train-unloading state.",
            "- Formal waiting uses `cumulative_stationary_person_seconds`, which includes resource queues, spatially blocked people, and other non-moving in-station people.",
            "- Load balance uses Jain's index J=(sum x)^2/(n*sum x^2), retaining available zero-use exits and key facilities.",
            "- Both methods use the same graph, population, physical execution, capacities, stopping rule and metric accumulator.", "",
            "## Core results", "",
            "| Metric | ImprovedAStar | AdaptiveQueueAwareAStar | Improvement |",
            "|---|---:|---:|---:|",
        ]
        for label, b_value, a_value, higher_is_better in report_metrics:
            report_lines.append(
                f"| {label} | {b_value:.4f} | {a_value:.4f} | {_improvement(b_value, a_value, higher_is_better):+.2f}% |"
            )
        report_lines.extend(["", "## Change and efficiency log", ""])
        report_lines.extend(f"- {entry}" for entry in EXPERIMENT_CHANGE_LOG)
        report_lines.extend([
            "", "## Conservation and fairness confirmation", "",
            f"- ImprovedAStar: target={baseline['target_people']:.0f}, evacuated={baseline['evacuated_people']:.0f}, remaining={baseline['remaining_people']:.0f}, completed={baseline['completed']}.",
            f"- AdaptiveQueueAwareAStar: target={adaptive['target_people']:.0f}, evacuated={adaptive['evacuated_people']:.0f}, remaining={adaptive['remaining_people']:.0f}, completed={adaptive['completed']}.",
            "- Complete exit and key-facility counts and Jain indices are in `load_balance.csv`; detailed facility counts are in `facility_throughput.csv`.",
        ])
        Path(os.path.join(output_dir, "mode4_formal_report.md")).write_text(
            "\n".join(report_lines), encoding="utf-8"
        )
        print("  [OK] mode4_formal_report.md")

    print(f"\n   全部数据已保存到: {output_dir}")


def _legacy_main():
    import argparse, sys as _sys
    parser = argparse.ArgumentParser(description="算法对比实验")
    parser.add_argument("--mode", type=int, default=0, choices=[0, 1, 4], help="场景: 1=常规突发, 4=双向满载, 0=交互选择")
    parser.add_argument(
        "--ablation",
        action="store_true",
        help="also run DensityOnlyAStar and CurrentQueueAwareAStar",
    )
    args, _ = parser.parse_known_args()

    global MODE
    MODE = args.mode
    if MODE == 0:
        print("选择场景:")
        print("  [1] mode1 常规突发 (2187人)")
        print("  [4] mode4 双向满载 (~15718人)")
        while True:
            choice = input("请输入: ").strip()
            if choice in ("1", "4"):
                MODE = int(choice)
                break
            print("  无效，请输 1 或 4")

    scenario_name = {1: "mode1 常规突发", 4: "mode4 双向满载"}[MODE]
    print("=" * 72)
    print(f"  算法对比：AdaptiveQueueAwareAStar vs ImprovedAStar")
    print(f"  场景: {scenario_name}")
    print("=" * 72)

    # 1. 构建图和客流
    net.OUTPUT_DIR = None
    G = net.build_graph()
    # Formal Improved baseline: exclude the non-published Q/mu gate-wait term.
    G.graph["improved_gate_queue_term"] = False
    # Formal Improved baseline: use the literature density-speed travel time.
    G.graph["improved_shared_travel_time"] = False
    G.graph["density_dependent_flow"] = True
    G.graph["spillback_enabled"] = True
    G.graph["aa_reroute_gain_min"] = 0.20
    G.graph["aa_spatial_batch_arrival_spread_enabled"] = True
    G.graph["aa_spatial_arrival_spread_seconds"] = 1.0
    if MODE == 4:
        G.graph["split_l2_train_source_groups_by_zone"] = True
    print(f"  Model revision: {MODEL_REVISION}")
    print(f"  Network module: {net.__file__}")
    print(
        f"  Spillback: {net.HIGH_LOAD_SPILLBACK_ENABLED}, "
        f"jam_density={net.HIGH_LOAD_JAM_DENSITY_P_PER_M2:.1f} p/m2, "
        f"buffer={net.HIGH_LOAD_MIN_RECEIVING_BUFFER_SECONDS:.1f}s"
    )
    pop_dict, total_people = build_population()
    print(f"\n  总人数: {total_people}")
    print(f"  网络规模: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")

    # 2. 运行两个算法
    print("\n  [1/2] 运行 ImprovedAStar (baseline)...")
    result_baseline = run_one(G, pop_dict, net.PAPER_SINGLE_PATH_METHOD, "ImprovedAStar")

    print("  [2/2] 运行 AdaptiveQueueAwareAStar...")
    result_our = run_one(G, pop_dict, net.OUR_SINGLE_PATH_METHOD, "AdaptiveQueueAwareAStar")
    comparison_results = [result_baseline, result_our]
    if args.ablation:
        print("  [3/4] Running DensityOnlyAStar...")
        comparison_results.append(
            run_one(G, pop_dict, spr.DENSITY_ONLY_ASTAR_METHOD, "DensityOnlyAStar")
        )
        print("  [4/4] Running CurrentQueueAwareAStar...")
        comparison_results.append(
            run_one(
                G,
                pop_dict,
                spr.CURRENT_QUEUE_AWARE_ASTAR_METHOD,
                "CurrentQueueAwareAStar",
            )
        )

    # 3. 计算对比指标
    or_time = compute_or(result_baseline["evacuation_time"], result_our["evacuation_time"])
    or_queue = compute_or(
        result_baseline["stationary_time"], result_our["stationary_time"]
    )

    # 4. 输出
    print("\n" + "=" * 72)
    print("  综合评估")
    print("=" * 72)
    print(f"  {'指标':<28} {'ImprovedAStar':>12} {'AdaptiveSNH':>12} {'改善':>8}")
    print(f"  {'-'*28} {'-'*12} {'-'*12} {'-'*8}")
    for key, label in [("t95", "T95 (s)"), ("t100", "T100 (s)")]:
        b = result_baseline["eval"][key]
        o = result_our["eval"][key]
        imp = f"{compute_or(b, o):+.1f}%"
        print(f"  {label:<28} {b:>12.2f} {o:>12.2f} {imp:>8}")

    print("\n" + "=" * 72)
    print("  系统效果")
    print("=" * 72)
    print(f"  {'指标':<36} {'ImprovedAStar':>14} {'AdaptiveSNH':>14} {'改善':>8}")
    print(f"  {'-'*36} {'-'*14} {'-'*14} {'-'*8}")
    print(f"  {'疏散时间 (s)':<36} {result_baseline['evacuation_time']:>14.1f} {result_our['evacuation_time']:>14.1f} {format_pct(or_time):>8}")
    print(f"  {'停滞时间 (人*秒)':<36} {result_baseline['stationary_time']:>14.1f} {result_our['stationary_time']:>14.1f} {format_pct(or_queue):>8}")
    print(f"  {'峰值密度 (人/m2)':<36} {result_baseline['peak_density']:>14.2f} {result_our['peak_density']:>14.2f}")
    print(f"  {'峰值溢出排队 (人)':<36} {result_baseline['peak_overflow_queue']:>14.1f} {result_our['peak_overflow_queue']:>14.1f}")
    print(f"  {'移动中平均速度 (m/s)':<36} {result_baseline['avg_speed']:>14.3f} {result_our['avg_speed']:>14.3f}")
    print(f"  {'出口负荷 Jain 指数':<36} {result_baseline['exit_load_jain_index']:>14.4f} {result_our['exit_load_jain_index']:>14.4f}")
    print(f"  {'关键设施负荷 Jain 指数':<36} {result_baseline['key_facility_load_jain_index']:>14.4f} {result_our['key_facility_load_jain_index']:>14.4f}")
    print(f"  {'含等待有效速度 (m/s)':<36} {result_baseline['effective_evacuation_speed']:>14.3f} {result_our['effective_evacuation_speed']:>14.3f}")
    print(f"  {'出口使用 Gini':<36} {result_baseline['exit_gini']:>14.4f} {result_our['exit_gini']:>14.4f}")

    print("\n" + "=" * 72)
    print("  计算开销")
    print("=" * 72)
    print(f"  {'指标':<36} {'ImprovedAStar':>14} {'AdaptiveSNH':>14}")
    print(f"  {'-'*36} {'-'*14} {'-'*14}")
    print(f"  {'墙钟时间 (s)':<36} {result_baseline['wall_clock_s']:>14.2f} {result_our['wall_clock_s']:>14.2f}")

    print("\n" + "=" * 72)
    print("  各线路清空时间")
    print("=" * 72)
    lines = sorted(result_baseline["clearance_times"].keys())
    print(f"  {'线路':<8} {'ImprovedAStar':>14} {'AdaptiveSNH':>14}")
    print(f"  {'-'*8} {'-'*14} {'-'*14}")
    for line in lines:
        bt = result_baseline["clearance_times"].get(line)
        ot = result_our["clearance_times"].get(line)
        b_str = f"{bt:.1f}" if bt is not None else "N/A"
        o_str = f"{ot:.1f}" if ot is not None else "N/A"
        print(f"  {line:<8} {b_str:>14} {o_str:>14}")

    print("\n" + "=" * 72)
    print("  出口使用分布")
    print("=" * 72)
    exits = sorted(result_baseline["exit_usage"].keys())
    print(f"  {'出口':<18} {'ImprovedAStar':>10} {'AdaptiveSNH':>10} {'占比变化':>10}")
    print(f"  {'-'*18} {'-'*10} {'-'*10} {'-'*10}")
    total_exit_base = sum(result_baseline["exit_usage"].values()) or 1.0
    total_exit_our = sum(result_our["exit_usage"].values()) or 1.0
    for ext in exits:
        b = result_baseline["exit_usage"].get(ext, 0)
        o = result_our["exit_usage"].get(ext, 0)
        bp = b / total_exit_base * 100
        op = o / total_exit_our * 100
        delta = op - bp
        d_str = f"{delta:+.1f}pp"
        print(f"  {ext:<18} {bp:>9.1f}% {op:>9.1f}% {d_str:>10}")

    # 5. 各设施通过人数（从边流推算节点吞吐量）
    def _node_throughput(edge_flows):
        """Count arrivals at each node once (not both incident edge ends)."""
        tp = {}
        for ek, flow in edge_flows.items():
            parts = ek.split("->")
            if len(parts) == 2:
                v = parts[1].strip()
                tp[v] = tp.get(v, 0.0) + flow
        return tp

    tp_base = _node_throughput(result_baseline["_raw_metrics"].get("edge_flow_totals", {}))
    tp_our = _node_throughput(result_our["_raw_metrics"].get("edge_flow_totals", {}))

    # 按节点类型分组展示（平台→楼扶梯→闸机→虚拟通道→出口）
    TYPE_ORDER = ["platform", "stair", "escalator", "gate", "virtual", "exit"]
    TYPE_NAMES = {"platform":"站台","stair":"楼梯","escalator":"扶梯","gate":"闸机","virtual":"通道节点","exit":"出口"}

    if not tp_base and not tp_our:
        print("\n  [WARNING] edge_flow_totals is empty — 边流量追踪可能未生效")
    else:
        total_flow = sum(tp_base.values()) + sum(tp_our.values())
        print(f"\n  [DEBUG] 边流记录数: baseline={len(tp_base)} our={len(tp_our)} 总流量={total_flow:.0f}")

    # 获取节点类型
    G_ref = net.build_graph()
    def _node_type(name):
        if name in G_ref.nodes:
            return G_ref.nodes[name].get("type", "")
        return ""

    # 按类型分组
    from collections import defaultdict
    groups = defaultdict(list)
    all_fac = set(tp_base.keys()) | set(tp_our.keys())
    for n in all_fac:
        t = _node_type(n)
        if t:
            groups[t].append(n)

    print("\n" + "=" * 72)
    print("  各设施通过人数")
    print("=" * 72)
    for t in TYPE_ORDER:
        nodes = sorted(groups.get(t, []))
        if not nodes:
            continue
        print(f"\n  --- {TYPE_NAMES.get(t, t)} ---")
        print(f"  {'设施':<32} {'ImprovedAStar':>12} {'AdaptiveSNH':>12} {'变化':>8}")
        print(f"  {'-'*32} {'-'*12} {'-'*12} {'-'*8}")
        for node in nodes:
            b = tp_base.get(node, 0)
            o = tp_our.get(node, 0)
            if b < 0.5 and o < 0.5:
                continue
            d = o - b
            d_str = f"{d:+.0f}" if abs(d) >= 0.5 else "-"
            print(f"  {node:<32} {b:>12.0f} {o:>12.0f} {d_str:>8}")

    # 6. 路由链路分解：起点→中间设施→出口
    nt_base = result_baseline["_raw_metrics"].get("node_throughput_by_sg", {})
    nt_our = result_our["_raw_metrics"].get("node_throughput_by_sg", {})
    exit_sg_base = result_baseline["_raw_metrics"].get("exit_usage_by_source_group", {})
    exit_sg_our = result_our["_raw_metrics"].get("exit_usage_by_source_group", {})

    # 确定 source groups
    all_sg = set()
    for nt in [nt_base, nt_our]:
        for node_sg in nt.values():
            all_sg.update(node_sg.keys())
    for esg in [exit_sg_base, exit_sg_our]:
        for sg_map in esg.values():
            all_sg.update(sg_map.keys())

    if all_sg:
        print("\n" + "=" * 72)
        print("  路由链路分解（起点 → 中间设施 → 出口）")
        print("=" * 72)
        for sg in sorted(all_sg):
            line_id, source_type, zone = net._parse_source_group_id(sg)
            # 总人数（从 pop_dict 取）
            sg_total = 0.0
            for esg in [exit_sg_base, exit_sg_our]:
                for sg_map in esg.values():
                    sg_total = max(sg_total, sg_map.get(sg, 0))

            print(f"\n  [{sg}] {source_type} ({sg_total:.0f}人)")

            # 中间设施（从 node_throughput_by_sg 取）
            for label, nt in [("ImprovedAStar", nt_base), ("AdaptiveSNH", nt_our)]:
                facilities = {}
                for fac, sg_map in nt.items():
                    if sg in sg_map and sg_map[sg] > 0.5:
                        facilities[fac] = sg_map[sg]
                if facilities:
                    top_fac = sorted(facilities.items(), key=lambda x: -x[1])[:8]
                    fac_strs = [f"{f}={v:.0f}" for f, v in top_fac]
                    print(f"    {label}: 经 {', '.join(fac_strs)}")

            # 出口（从 exit_usage_by_source_group 取）
            for label, esg in [("ImprovedAStar", exit_sg_base), ("AdaptiveSNH", exit_sg_our)]:
                exits = {}
                for ext, sg_map in esg.items():
                    if sg in sg_map and sg_map[sg] > 0.5:
                        exits[ext] = sg_map[sg]
                if exits:
                    top_exit = sorted(exits.items(), key=lambda x: -x[1])[:8]
                    ext_strs = [f"{e}={v:.0f}" for e, v in top_exit]
                    print(f"    {label}: 至 {', '.join(ext_strs)}")

    # 7. 保存全部数据到时间戳目录
    import os, datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("outputs", "algorithm_compare", f"mode{MODE}_{ts}")
    save_all_results(
        comparison_results,
        pop_dict,
        output_dir=output_dir,
        scenario_name=scenario_name,
    )


def _largest_remainder_percentages(route_rows, source_group_total):
    """Return deterministic one-decimal percentages summing to exactly 100.0."""
    positive_rows = [row for row in route_rows if int(row["route_people"]) > 0]
    if not positive_rows:
        return {}
    total = max(int(source_group_total), 1)
    working = []
    for row in positive_rows:
        raw_units = int(row["route_people"]) * 1000.0 / total
        base_units = math.floor(raw_units)
        working.append({
            "route_id": row["route_id"],
            "people": int(row["route_people"]),
            "remainder": raw_units - base_units,
            "units": base_units,
        })
    difference = 1000 - sum(item["units"] for item in working)
    if difference > 0:
        order = sorted(
            working,
            key=lambda item: (
                -item["remainder"], -item["people"], item["route_id"]
            ),
        )
        for index in range(difference):
            order[index % len(order)]["units"] += 1
    elif difference < 0:
        order = sorted(
            working,
            key=lambda item: (
                item["remainder"], item["people"], item["route_id"]
            ),
        )
        remaining = -difference
        index = 0
        while remaining > 0 and any(item["units"] > 0 for item in order):
            item = order[index % len(order)]
            if item["units"] > 0:
                item["units"] -= 1
                remaining -= 1
            index += 1
    percentages = {
        item["route_id"]: item["units"] / 10.0 for item in working
    }
    if abs(sum(percentages.values()) - 100.0) > 1e-9:
        raise AssertionError("display route percentages do not sum to 100.0")
    return percentages


def _pathfinder_node_roles(graph, node):
    node_type = str(graph.nodes[node].get("type", "")).lower()
    text = f"{node_type} {node}".lower()
    return {
        "vertical": any(word in text for word in (
            "stair", "escalator", "elevator", "lift", "vertical",
        )),
        "gate": "gate" in text,
        "exit": node_type == "exit" or str(node).lower().startswith("exit_"),
        "platform": "platform" in text and "door" not in text,
        "transfer": any(word in text for word in (
            "transfer", "passage", "corridor", "merge", "bottleneck",
        )),
    }


def _pathfinder_control_path(graph, raw_path):
    if not raw_path:
        return []
    control = []
    for index, node in enumerate(raw_path):
        roles = _pathfinder_node_roles(graph, node)
        keep = (
            index == 0
            or index == len(raw_path) - 1
            or any(roles.values())
        )
        if keep:
            control.append(node)
    return control


def _stable_route_id(source_group, raw_path):
    payload = source_group + "\0" + "\0".join(map(str, raw_path))
    return "PF_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _stable_canonical_route_id(source_group, canonical_signature):
    payload = source_group + "\0" + repr(canonical_signature)
    return "PFM_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _pathfinder_canonical_signature(graph, raw_path):
    verticals = [
        node for node in raw_path
        if node in graph and _pathfinder_node_roles(graph, node)["vertical"]
    ]
    gates = [
        node for node in raw_path
        if node in graph and _pathfinder_node_roles(graph, node)["gate"]
    ]
    first_vertical = verticals[0] if verticals else "NONE"
    transfer_facilities = []
    for node in raw_path:
        if node not in graph:
            continue
        roles = _pathfinder_node_roles(graph, node)
        if (roles["vertical"] and node != first_vertical) or roles["transfer"]:
            if node not in transfer_facilities:
                transfer_facilities.append(node)
    exit_node = raw_path[-1] if raw_path else "NONE"
    return (
        first_vertical,
        tuple(transfer_facilities),
        tuple(gates),
        exit_node,
    )


def _canonical_path_from_signature(canonical_signature):
    first_vertical, transfers, gates, exit_node = canonical_signature
    nodes = []
    if first_vertical and first_vertical != "NONE":
        nodes.append(first_vertical)
    for node in transfers:
        if node not in nodes and node != "NONE":
            nodes.append(node)
    for node in gates:
        if node not in nodes and node != "NONE":
            nodes.append(node)
    if exit_node and exit_node != "NONE":
        nodes.append(exit_node)
    return " -> ".join(map(str, nodes))


def _sanitize_pathfinder_name(value):
    return re.sub(r"[^0-9A-Za-z_.\-/]+", "_", str(value)).strip("_")


def _build_pathfinder_route_exports(result, mode, total_people):
    """Build Pathfinder rows solely from completed, actually executed routes."""
    raw = result["_raw_metrics"]
    graph = result.get("_simulation_graph")
    if graph is None:
        return [], [], [], {
            "source_groups": 0,
            "complete_routes": 0,
            "total_allocated_people": 0,
            "people_conservation_error": int(total_people),
            "source_group_percentage_errors": 0,
            "discontinuous_routes": 0,
            "routes_with_cycles": 0,
        }
    scenario_name = {
        1: "Mode 1 - Regular emergency",
        4: "Mode 4 - Bidirectional full train",
    }.get(mode, f"Mode {mode}")
    source_totals = {
        str(group): int(round(float(amount)))
        for group, amount in raw.get("source_group_totals", {}).items()
        if int(round(float(amount))) > 0
    }
    aggregated = {}
    for record in raw.get("completed_executed_routes", []):
        source_group = str(record.get("source_group", ""))
        path = tuple(record.get("raw_full_path", []))
        amount = int(record.get("route_people", 0))
        if source_group and path and amount > 0:
            aggregated[(source_group, path)] = (
                aggregated.get((source_group, path), 0) + amount
            )

    raw_route_rows = []
    for (source_group, raw_path), route_people in sorted(
        aggregated.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        line_id, source_type, _ = net._parse_source_group_id(source_group)
        route_id = _stable_route_id(source_group, raw_path)
        continuous = all(
            graph.has_edge(raw_path[index], raw_path[index + 1])
            for index in range(len(raw_path) - 1)
        )
        contains_cycle = len(set(raw_path)) != len(raw_path)
        seen_edges = set()
        contains_reverse = False
        for edge in zip(raw_path, raw_path[1:]):
            if (edge[1], edge[0]) in seen_edges:
                contains_reverse = True
            seen_edges.add(edge)
        control_path = _pathfinder_control_path(graph, raw_path)
        verticals = [
            node for node in raw_path
            if _pathfinder_node_roles(graph, node)["vertical"]
        ]
        gates = [
            node for node in raw_path
            if _pathfinder_node_roles(graph, node)["gate"]
        ]
        transfer_facilities = []
        first_vertical = verticals[0] if verticals else "NONE"
        for node in raw_path:
            roles = _pathfinder_node_roles(graph, node)
            if (roles["vertical"] and node != first_vertical) or roles["transfer"]:
                if node not in transfer_facilities:
                    transfer_facilities.append(node)
        exit_node = raw_path[-1]
        errors = []
        if raw_path[0] not in graph:
            errors.append("source start node is absent from graph")
        if not continuous:
            errors.append("raw path is discontinuous")
        if not _pathfinder_node_roles(graph, exit_node)["exit"]:
            errors.append("raw path does not terminate at an exit")
        if route_people <= 0:
            errors.append("route_people is not a positive integer")
        if errors:
            status = "ERROR"
        elif contains_cycle or contains_reverse:
            status = "WARNING"
        else:
            status = "OK"
        warnings = []
        if contains_cycle:
            warnings.append("route contains a repeated node")
        if contains_reverse:
            warnings.append("route contains a reverse move")
        message = "; ".join(errors + warnings) if errors or warnings else "valid"
        source_total = source_totals.get(source_group, 0)
        raw_percentage = (
            route_people / source_total * 100.0 if source_total > 0 else 0.0
        )
        canonical_signature = _pathfinder_canonical_signature(graph, raw_path)
        raw_route_rows.append({
            "scenario_mode": mode,
            "scenario_name": scenario_name,
            "scenario_people": int(total_people),
            "algorithm": result["method"],
            "line_id": line_id,
            "source_type": source_type,
            "source_group": source_group,
            "source_start_node": raw_path[0],
            "first_vertical_facility": first_vertical,
            "transfer_facilities": (
                ";".join(map(str, transfer_facilities))
                if transfer_facilities else "NONE"
            ),
            "gate_facility": ";".join(map(str, gates)) if gates else "NONE",
            "exit_node": exit_node,
            "raw_full_path": " -> ".join(map(str, raw_path)),
            "pathfinder_control_path": " -> ".join(map(str, control_path)),
            "canonical_path": _canonical_path_from_signature(canonical_signature),
            "route_people": route_people,
            "source_group_total_people": source_total,
            "raw_route_percentage": raw_percentage,
            "route_percentage": 0.0,
            "route_id": route_id,
            "contains_cycle": contains_cycle,
            "contains_reverse_move": contains_reverse,
            "validation_status": status,
            "validation_message": message,
            "_raw_path_nodes": raw_path,
            "_control_path_nodes": tuple(control_path),
            "_canonical_signature": canonical_signature,
        })

    merged = {}
    for row in raw_route_rows:
        key = (row["source_group"], row["_canonical_signature"])
        if key not in merged:
            signature = row["_canonical_signature"]
            first_vertical, transfer_facilities, gates, exit_node = signature
            merged[key] = {
                **row,
                "route_id": _stable_canonical_route_id(row["source_group"], signature),
                "source_display_name": row["source_group"],
                "first_vertical_facility": first_vertical,
                "transfer_facilities": (
                    ";".join(map(str, transfer_facilities))
                    if transfer_facilities else "NONE"
                ),
                "gate_facility": (
                    ";".join(map(str, gates)) if gates else "NONE"
                ),
                "exit_node": exit_node,
                "raw_full_path": row["raw_full_path"],
                "pathfinder_control_path": row["canonical_path"],
                "route_people": 0,
                "raw_route_percentage": 0.0,
                "route_percentage": 0.0,
                "contains_cycle": False,
                "contains_reverse_move": False,
                "validation_status": "OK",
                "validation_message": "valid",
                "_raw_path_nodes": tuple(),
                "_control_path_nodes": tuple(
                    node
                    for part in (
                        (first_vertical,) if first_vertical != "NONE" else (),
                        transfer_facilities,
                        gates,
                        (exit_node,) if exit_node != "NONE" else (),
                    )
                    for node in part
                ),
                "_facility_nodes": tuple(
                    node
                    for node in (
                        (first_vertical,) + transfer_facilities + gates
                    )
                    if node != "NONE"
                ),
            }
        target = merged[key]
        target["route_people"] += int(row["route_people"])
        target["contains_cycle"] = (
            bool(target["contains_cycle"]) or bool(row["contains_cycle"])
        )
        target["contains_reverse_move"] = (
            bool(target["contains_reverse_move"])
            or bool(row["contains_reverse_move"])
        )
        if row["validation_status"] == "ERROR":
            target["validation_status"] = "ERROR"
        elif (
            target["validation_status"] != "ERROR"
            and row["validation_status"] == "WARNING"
        ):
            target["validation_status"] = "WARNING"
        if row["validation_message"] != "valid":
            previous = target["validation_message"]
            target["validation_message"] = (
                row["validation_message"]
                if previous == "valid"
                else previous + "; " + row["validation_message"]
            )
        elif row["raw_full_path"] not in str(target.get("raw_full_path", "")):
            target["raw_full_path"] = (
                str(target.get("raw_full_path", ""))
                + " | "
                + row["raw_full_path"]
            )
    route_rows = sorted(
        merged.values(),
        key=lambda row: (
            row["source_group"],
            row["first_vertical_facility"],
            row["transfer_facilities"],
            row["gate_facility"],
            row["exit_node"],
        ),
    )
    for row in route_rows:
        source_total = source_totals.get(row["source_group"], 0)
        row["source_group_total_people"] = source_total
        row["raw_route_percentage"] = (
            row["route_people"] / source_total * 100.0
            if source_total > 0 else 0.0
        )

    merged_rows_by_group = {}
    for row in route_rows:
        merged_rows_by_group.setdefault(row["source_group"], []).append(row)
    for source_group, rows in merged_rows_by_group.items():
        percentages = _largest_remainder_percentages(
            rows, source_totals.get(source_group, 0)
        )
        for row in rows:
            row["route_percentage"] = percentages[row["route_id"]]

    group_rows = []
    used_group_names = set()
    for row in route_rows:
        control_nodes = list(row["_control_path_nodes"])
        intermediates = control_nodes[1:-1]
        visible_chain = intermediates + [row["exit_node"]]
        base_name = "__".join(
            [_sanitize_pathfinder_name(row["source_group"])]
            + [_sanitize_pathfinder_name(node) for node in visible_chain]
        )
        group_name = base_name
        if group_name in used_group_names:
            group_name = f"{base_name}__{row['route_id']}"
        used_group_names.add(group_name)
        setup = {
            "scenario_mode": mode,
            "scenario_people": int(total_people),
            "line_id": row["line_id"],
            "source_type": row["source_type"],
            "source_group": row["source_group"],
            "group_name": group_name,
            "source_area": row["source_start_node"],
            "exact_people": row["route_people"],
            "route_percentage": row["route_percentage"],
            "target_exit": row["exit_node"],
            "pathfinder_behavior_name": f"Behavior__{group_name}",
            "pathfinder_control_path": row["pathfinder_control_path"],
        }
        for index in range(10):
            setup[f"waypoint_{index + 1}"] = (
                intermediates[index] if index < len(intermediates) else "NONE"
            )
        group_rows.append(setup)

    expected_exits = raw.get("exit_usage_by_source_group", {})
    node_throughput = raw.get("node_throughput_by_sg", {})
    key_facilities = set(raw.get("key_facility_throughput", {}))
    tracking_errors = raw.get("route_tracking_errors", [])
    raw_rows_by_group = {}
    for row in raw_route_rows:
        raw_rows_by_group.setdefault(row["source_group"], []).append(row)

    raw_validation_rows = []
    merged_validation_rows = []
    car_name_pattern = re.compile(r"(^|[^0-9A-Za-z])(Car\d*|C[1-6])([^0-9A-Za-z]|$)")
    for source_group in sorted(source_totals):
        raw_rows = raw_rows_by_group.get(source_group, [])
        merged_rows = merged_rows_by_group.get(source_group, [])
        expected_exit_map = {
            exit_node: int(round(float(group_map.get(source_group, 0.0))))
            for exit_node, group_map in expected_exits.items()
            if int(round(float(group_map.get(source_group, 0.0)))) > 0
        }

        raw_route_people = sum(int(row["route_people"]) for row in raw_rows)
        raw_exit_map = {}
        raw_facility_map = {}
        for row in raw_rows:
            raw_exit_map[row["exit_node"]] = (
                raw_exit_map.get(row["exit_node"], 0) + int(row["route_people"])
            )
            for node in row["_raw_path_nodes"][1:]:
                if node in key_facilities:
                    raw_facility_map[node] = (
                        raw_facility_map.get(node, 0) + int(row["route_people"])
                    )
        expected_facility_map = {
            facility: int(round(float(
                node_throughput.get(facility, {}).get(source_group, 0.0)
            )))
            for facility in key_facilities
        }
        relevant_tracking_errors = [
            error for error in tracking_errors
            if error.get("source_group") == source_group
        ]
        raw_people_error = raw_route_people - source_totals[source_group]
        raw_percentage = (
            raw_route_people / source_totals[source_group] * 100.0
            if source_totals[source_group] > 0 else 0.0
        )
        raw_percentage_error = raw_percentage - 100.0 if raw_rows else -100.0
        raw_exit_consistent = raw_exit_map == expected_exit_map
        raw_facility_consistent = all(
            raw_facility_map.get(facility, 0) == expected
            for facility, expected in expected_facility_map.items()
        )
        raw_continuity_valid = all(
            row["validation_status"] != "ERROR" for row in raw_rows
        )
        raw_passed = (
            raw_people_error == 0
            and raw_exit_consistent
            and raw_facility_consistent
            and raw_continuity_valid
            and not relevant_tracking_errors
        )
        raw_validation_rows.append({
            "scenario_mode": mode,
            "source_group": source_group,
            "initial_people": source_totals[source_group],
            "raw_route_count": len(raw_rows),
            "route_count": len(raw_rows),
            "summed_route_people": raw_route_people,
            "people_error": raw_people_error,
            "summed_route_percentage": raw_percentage,
            "percentage_error": raw_percentage_error,
            "exit_consistency": raw_exit_consistent,
            "exit_sum_consistent": raw_exit_consistent,
            "facility_throughput_consistency": raw_facility_consistent,
            "facility_sum_consistent": raw_facility_consistent,
            "raw_path_continuity": raw_continuity_valid,
            "path_continuity_valid": raw_continuity_valid,
            "validation_passed": raw_passed,
        })

        merged_route_people = sum(int(row["route_people"]) for row in merged_rows)
        merged_percentage = sum(float(row["route_percentage"]) for row in merged_rows)
        merged_exit_map = {}
        for row in merged_rows:
            merged_exit_map[row["exit_node"]] = (
                merged_exit_map.get(row["exit_node"], 0) + int(row["route_people"])
            )
        merged_people_error = merged_route_people - source_totals[source_group]
        merged_percentage_error = merged_percentage - 100.0 if merged_rows else -100.0
        merged_exit_consistent = merged_exit_map == expected_exit_map
        canonical_path_valid = all(
            row["validation_status"] != "ERROR"
            and row.get("canonical_path")
            and row.get("exit_node") in graph
            and _pathfinder_node_roles(graph, row.get("exit_node"))["exit"]
            for row in merged_rows
        )
        no_car_names = all(
            not car_name_pattern.search(str(row.get("canonical_path", "")))
            for row in merged_rows
        )
        merged_passed = (
            merged_people_error == 0
            and abs(merged_percentage_error) <= 1e-9
            and merged_exit_consistent
            and canonical_path_valid
            and no_car_names
        )
        merged_validation_rows.append({
            "scenario_mode": mode,
            "source_group": source_group,
            "initial_people": source_totals[source_group],
            "merged_route_count": len(merged_rows),
            "route_count": len(merged_rows),
            "summed_route_people": merged_route_people,
            "people_error": merged_people_error,
            "summed_route_percentage": merged_percentage,
            "percentage_error": merged_percentage_error,
            "exit_consistency": merged_exit_consistent,
            "exit_sum_consistent": merged_exit_consistent,
            "canonical_path_valid": canonical_path_valid,
            "no_car_names": no_car_names,
            "validation_passed": merged_passed,
        })

    summary = {
        "source_groups": len(source_totals),
        "complete_routes": len(route_rows),
        "total_allocated_people": sum(
            int(row["route_people"]) for row in route_rows
        ),
        "people_conservation_error": (
            sum(int(row["route_people"]) for row in route_rows) - int(total_people)
        ),
        "source_group_percentage_errors": sum(
            abs(float(row["percentage_error"])) > 1e-9
            for row in merged_validation_rows
        ),
        "discontinuous_routes": sum(
            row["validation_status"] == "ERROR" for row in raw_route_rows
        ),
        "routes_with_cycles": sum(
            bool(row["contains_cycle"]) for row in raw_route_rows
        ),
        "routes_with_reverse_moves": sum(
            bool(row["contains_reverse_move"]) for row in raw_route_rows
        ),
        # Audit-only threshold for route fragmentation; it does not affect
        # routing, capacity, movement, or any formal comparison metric.
        "small_route_people_threshold": 5,
        "small_routes": sum(
            int(row["route_people"]) <= 5 for row in route_rows
        ),
        "_raw_route_rows": raw_route_rows,
        "_raw_validation_rows": raw_validation_rows,
        "_merged_validation_rows": merged_validation_rows,
    }
    return route_rows, group_rows, raw_validation_rows, summary


def _exit_line_id(exit_name):
    """Return the physical line label encoded by a final exit node name."""
    text = str(exit_name or "")
    if text.startswith("Exit_L2_"):
        return "L2"
    if text.startswith("Exit_L7_"):
        return "L7"
    if text.startswith("Exit_Maglev_"):
        return "Maglev"
    match = re.match(r"^Exit_(L\d+)_", text)
    return match.group(1) if match else ""


def _write_l2_l7_exit_reports(run_dir, raw_route_rows):
    """Write source-to-final-exit details for all L2/L7-related flows.

    The rows come from executed raw routes.  A flow is included when either
    its source line or its final exit is on L2/L7, so cross-line evacuation is
    visible in both directions (for example L7 -> Exit_L2_2 and L16 ->
    Exit_L2_6).
    """
    scope_lines = {"L2", "L7"}
    details = []
    for row in raw_route_rows:
        source_line = str(row.get("line_id", ""))
        final_exit = str(row.get("exit_node", ""))
        final_exit_line = _exit_line_id(final_exit)
        if source_line not in scope_lines and final_exit_line not in scope_lines:
            continue
        source_total = int(row.get("source_group_total_people", 0) or 0)
        people = int(row.get("route_people", 0) or 0)
        details.append({
            "algorithm": row.get("algorithm", ""),
            "scope_line": (
                source_line if source_line in scope_lines else final_exit_line
            ),
            "source_line": source_line,
            "source_type": row.get("source_type", ""),
            "source_group": row.get("source_group", ""),
            "source_start_node": row.get("source_start_node", ""),
            "source_group_total_people": source_total,
            "final_exit": final_exit,
            "final_exit_line": final_exit_line,
            "cross_line": "YES" if source_line != final_exit_line else "NO",
            "people": people,
            "share_within_source_group": (
                people / source_total if source_total > 0 else 0.0
            ),
            "raw_full_path": row.get("raw_full_path", ""),
        })

    detail_fields = [
        "algorithm", "scope_line", "source_line", "source_type",
        "source_group", "source_start_node", "source_group_total_people",
        "final_exit", "final_exit_line", "cross_line", "people",
        "share_within_source_group", "raw_full_path",
    ]
    with (Path(run_dir) / "l2_l7_exit_details.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        for row in sorted(
            details,
            key=lambda item: (
                item["scope_line"], item["final_exit"],
                item["source_line"], item["source_group"],
                item["source_start_node"], item["raw_full_path"],
            ),
        ):
            output = dict(row)
            output["share_within_source_group"] = (
                f"{float(row['share_within_source_group']):.6f}"
            )
            writer.writerow(output)

    grouped = {}
    for row in details:
        key = (
            row["scope_line"], row["final_exit"], row["final_exit_line"],
            row["source_line"], row["source_type"], row["source_group"],
            row["source_start_node"], row["cross_line"],
        )
        grouped[key] = grouped.get(key, 0) + int(row["people"])
    final_totals = {}
    for row in details:
        final_totals[row["final_exit"]] = (
            final_totals.get(row["final_exit"], 0) + int(row["people"])
        )
    summary_fields = [
        "algorithm", "scope_line", "final_exit", "final_exit_line",
        "final_exit_total_people", "source_line", "source_type",
        "source_group", "source_start_node", "cross_line", "people",
        "share_of_final_exit",
    ]
    with (Path(run_dir) / "l2_l7_exit_summary.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        for key, people in sorted(grouped.items()):
            (
                scope_line, final_exit, final_exit_line, source_line,
                source_type, source_group, source_start_node, cross_line,
            ) = key
            exit_total = final_totals[final_exit]
            writer.writerow({
                "algorithm": details[0]["algorithm"] if details else "",
                "scope_line": scope_line,
                "final_exit": final_exit,
                "final_exit_line": final_exit_line,
                "final_exit_total_people": exit_total,
                "source_line": source_line,
                "source_type": source_type,
                "source_group": source_group,
                "source_start_node": source_start_node,
                "cross_line": cross_line,
                "people": people,
                "share_of_final_exit": f"{people / max(exit_total, 1) :.6f}",
            })

    return len(details)


def _write_pathfinder_route_outputs(result, run_dir, mode, total_people):
    route_rows, group_rows, validation_rows, summary = (
        _build_pathfinder_route_exports(result, mode, total_people)
    )
    raw_route_rows = summary.pop("_raw_route_rows", [])
    raw_validation_rows = summary.pop("_raw_validation_rows", validation_rows)
    merged_validation_rows = summary.pop("_merged_validation_rows", [])
    raw_route_fields = [
        "scenario_mode", "scenario_name", "scenario_people", "algorithm",
        "line_id", "source_type", "source_group", "source_start_node",
        "first_vertical_facility", "transfer_facilities", "gate_facility",
        "exit_node", "raw_full_path", "pathfinder_control_path",
        "route_people", "source_group_total_people", "raw_route_percentage",
        "route_id", "contains_cycle", "contains_reverse_move",
        "validation_status", "validation_message",
    ]
    with (run_dir / "pathfinder_route_allocation_raw.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=raw_route_fields)
        writer.writeheader()
        for row in raw_route_rows:
            output = {field: row.get(field, "") for field in raw_route_fields}
            output["raw_route_percentage"] = f"{row['raw_route_percentage']:.6f}"
            writer.writerow(output)

    route_fields = [
        "scenario_mode", "scenario_name", "scenario_people", "algorithm",
        "line_id", "source_type", "source_group", "source_display_name",
        "first_vertical_facility", "transfer_facilities", "gate_facility",
        "exit_node", "route_people", "source_group_total_people",
        "route_percentage", "canonical_path", "route_id", "contains_cycle",
        "contains_reverse_move", "validation_status", "validation_message",
    ]
    for output_name in (
        "pathfinder_route_allocation_merged.csv",
        "pathfinder_route_allocation.csv",
    ):
        with (run_dir / output_name).open(
        "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=route_fields)
            writer.writeheader()
            for row in route_rows:
                output = {field: row.get(field, "") for field in route_fields}
                output["route_percentage"] = f"{row['route_percentage']:.1f}"
                writer.writerow(output)

    waypoint_fields = [f"waypoint_{index}" for index in range(1, 11)]
    group_fields = [
        "scenario_mode", "scenario_people", "line_id", "source_type",
        "source_group", "group_name", "source_area", "exact_people",
        "route_percentage", *waypoint_fields, "target_exit",
        "pathfinder_behavior_name", "pathfinder_control_path",
    ]
    with (run_dir / "pathfinder_group_setup.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=group_fields)
        writer.writeheader()
        for row in group_rows:
            output = {field: row.get(field, "") for field in group_fields}
            output["route_percentage"] = f"{row['route_percentage']:.1f}"
            writer.writerow(output)

    raw_validation_fields = [
        "scenario_mode", "source_group", "initial_people", "raw_route_count",
        "route_count", "summed_route_people", "people_error",
        "exit_consistency", "exit_sum_consistent",
        "facility_throughput_consistency", "facility_sum_consistent",
        "raw_path_continuity", "path_continuity_valid",
        "validation_passed",
    ]
    for output_name in (
        "raw_route_validation.csv",
        "pathfinder_route_validation.csv",
    ):
        with (run_dir / output_name).open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=raw_validation_fields)
            writer.writeheader()
            for row in raw_validation_rows:
                writer.writerow({
                    field: row.get(field, "")
                    for field in raw_validation_fields
                })

    merged_validation_fields = [
        "scenario_mode", "source_group", "initial_people",
        "merged_route_count", "route_count", "summed_route_people",
        "people_error", "summed_route_percentage", "percentage_error",
        "exit_consistency", "exit_sum_consistent", "canonical_path_valid",
        "no_car_names", "validation_passed",
    ]
    with (run_dir / "merged_route_validation.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=merged_validation_fields)
        writer.writeheader()
        for row in merged_validation_rows:
            output = {
                field: row.get(field, "")
                for field in merged_validation_fields
            }
            output["summed_route_percentage"] = (
                f"{row['summed_route_percentage']:.1f}"
            )
            output["percentage_error"] = f"{row['percentage_error']:.1f}"
            writer.writerow(output)
    l2_l7_rows = _write_l2_l7_exit_reports(run_dir, raw_route_rows)
    summary["l2_l7_exit_detail_rows"] = l2_l7_rows
    return summary


def _write_run_readme(run_dir, result, pathfinder_written):
    lines = [
        f"Algorithm: {result['method']}",
        "",
        "summary_metrics.csv - formal performance metrics.",
        "exit_usage.csv - cumulative exit use.",
        "exit_by_source_group.csv - source-group by exit cross-check.",
        "l2_l7_exit_details.csv - raw L2/L7 source-to-final-exit details, including cross-line flows.",
        "l2_l7_exit_summary.csv - L2/L7 final-exit totals split by source group.",
        "facility_throughput.csv - cumulative key-facility throughput.",
        "line_clearance.csv - line T95 and clearance time.",
        "edge_state_diagnostics.csv - per-edge near-jam state diagnostics.",
        "receiving_block_diagnostics.csv - separate edge-limit and destination-spillback rejections.",
        "edge_lowest_speed_top20.csv - slowest occupied physical edges.",
        "edge_low_speed_person_seconds_top20.csv - highest <0.3 m/s person-seconds.",
        "edge_low_speed_by_line.csv - low-speed transit person-seconds by source line.",
        "final_in_transit_edges.csv - edges occupied in the last nonempty transit snapshot.",
        "diagnostics.json - runtime diagnostics.",
        "gate_approach_replan_diagnostics.csv - Gate Approach replan attempt reasons.",
        "l7_hall_common_decisions.csv - L7 common-hall candidate costs and executed decisions.",
        "l7_common_hall_topology_audit.csv - L7 vertical-to-hall topology and CAD-derived lengths.",
        "gate_approach_connectivity.csv - directed connectivity between recognized Gate Approach nodes.",
        "improved_ordinary_crossline_controls.csv - Improved admission state for every recognized transfer branch.",
        "run_config.json - run configuration.",
        "run.log - progress log.",
    ]
    if pathfinder_written:
        lines.extend([
            "",
            "pathfinder_route_allocation.csv",
            f"- {result['method']}实际执行的起点—楼扶梯—闸机—出口完整路线分配；",
            "- route_people为Pathfinder应使用的准确整数人数；",
            "- route_percentage保留小数点后一位；",
            "- 同一source_group下比例合计严格为100.0%。",
            "",
            "pathfinder_group_setup.csv",
            "- 用于Pathfinder逐组创建Occupant Group与固定Behavior；",
            "- exact_people用于实际建模；",
            "- route_percentage仅用于核查和报告。",
            "",
            "pathfinder_route_validation.csv",
            "- 人数守恒、比例合计、路径连续性及出口/设施交叉校验结果。",
        ])
    (run_dir / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_single_algorithm_outputs(
    result, run_dir, mode, total_people, *, diagnostic_metrics=False
):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    raw = result["_raw_metrics"]
    summary_fields = [
        "method", "target_people", "evacuated_people", "remaining_people",
        "completed", "termination_reason", "T95_seconds", "T99_seconds",
        "T100_seconds",
        "cumulative_stationary_person_seconds",
        "mean_stationary_time_seconds_per_person",
        "mean_station_throughput_people_per_second",
        "moving_average_speed_m_per_s", "edge_traversal_average_speed_m_per_s",
        "effective_evacuation_speed_m_per_s", "total_movement_distance_m",
        "moving_person_seconds", "total_system_person_seconds",
        "mean_moving_time_seconds_per_person",
        "mean_total_evacuation_time_seconds_per_person",
        "exit_load_jain_index",
        "key_facility_load_jain_index", "wall_clock_runtime_seconds",
    ]
    summary_row = {
        "method": result["method"],
        "target_people": result["target_people"],
        "evacuated_people": result["evacuated_people"],
        "remaining_people": result["remaining_people"],
        "completed": result["completed"],
        "termination_reason": result["termination_reason"],
        "T95_seconds": result["eval"]["t95"],
        "T99_seconds": result["eval"].get(
            "t99", result["eval"].get("t100", 0.0)
        ),
        "T100_seconds": result["eval"]["t100"],
        "cumulative_stationary_person_seconds": result["stationary_time"],
        "mean_stationary_time_seconds_per_person": result["mean_stationary_time"],
        "mean_station_throughput_people_per_second": result["mean_station_throughput"],
        "moving_average_speed_m_per_s": result["moving_average_speed"],
        "edge_traversal_average_speed_m_per_s": result["edge_traversal_avg_speed"],
        "effective_evacuation_speed_m_per_s": result["effective_evacuation_speed"],
        "total_movement_distance_m": result["total_movement_distance"],
        "moving_person_seconds": result["moving_person_seconds"],
        "total_system_person_seconds": result["total_system_person_seconds"],
        "mean_moving_time_seconds_per_person": result["mean_moving_time"],
        "mean_total_evacuation_time_seconds_per_person": result["mean_total_evacuation_time"],
        "exit_load_jain_index": result["exit_load_jain_index"],
        "key_facility_load_jain_index": result["key_facility_load_jain_index"],
        "wall_clock_runtime_seconds": result["wall_clock_s"],
    }
    with (run_dir / "summary_metrics.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerow(summary_row)

    with (run_dir / "exit_usage.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["exit", "cumulative_people"])
        for exit_name, people in sorted(result["exit_usage"].items()):
            writer.writerow([exit_name, people])

    exit_source_rows = net.build_exit_source_group_rows(
        raw, method_label=result["method"]
    )
    exit_source_fields = [
        "method_label", "source_group", "line", "source_type",
        "source_zone", "configured_people", "evacuated_people",
        "exit_name", "people", "share_within_group",
    ]
    with (run_dir / "exit_by_source_group.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=exit_source_fields)
        writer.writeheader()
        writer.writerows(exit_source_rows)

    facilities = raw.get("key_facility_throughput", {})
    with (run_dir / "facility_throughput.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["facility", "cumulative_people"])
        for facility, people in sorted(facilities.items()):
            writer.writerow([facility, people])

    with (run_dir / "load_balance.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["category", "item", "cumulative_people", "jain_index"])
        for exit_name, people in sorted(result["exit_usage"].items()):
            writer.writerow(["exit", exit_name, people, ""])
        writer.writerow(["exit", "ALL", "", result["exit_load_jain_index"]])
        for facility, people in sorted(facilities.items()):
            writer.writerow(["key_facility", facility, people, ""])
        writer.writerow(["key_facility", "ALL", "", result["key_facility_load_jain_index"]])

    line_rows = []
    for line_id in net.ALL_LINE_IDS:
        t95 = result["line_t95"].get(line_id)
        clearance = result["clearance_times"].get(line_id)
        if t95 is None and clearance is None:
            continue
        line_rows.append((line_id, t95, clearance))
    finite_clearances = [
        (line_id, float(clearance))
        for line_id, _, clearance in line_rows
        if clearance is not None
    ]
    last_clearance_line = (
        max(finite_clearances, key=lambda item: item[1])[0]
        if finite_clearances else ""
    )
    with (run_dir / "line_clearance.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "line", "T95_seconds", "clearance_time_seconds",
            "is_last_clearance_line",
        ])
        for line_id, t95, clearance in line_rows:
            writer.writerow([
                line_id,
                "" if t95 is None else t95,
                "" if clearance is None else clearance,
                line_id == last_clearance_line,
            ])

    diagnostic_fields = [
        "algorithm", "location_type", "location_id", "node_or_edge_type",
        "area", "area_source", "people", "physical_people", "overflow_queue",
        "density", "exposure_person_seconds", "first_time", "last_time",
        "time_bin_100s", "is_at_density_cap", "spatial_storage_enabled",
        "initial_exposure_person_seconds",
    ]
    diagnostic_rows = []
    for row in raw.get("high_density_diagnostics", []):
        diagnostic_rows.append({"algorithm": result["method"], **row})
    diagnostic_handle = (
        (run_dir / "high_density_diagnostics.csv").open(
            "w", newline="", encoding="utf-8-sig"
        )
        if diagnostic_metrics else io.StringIO()
    )
    with diagnostic_handle as handle:
        writer = csv.DictWriter(handle, fieldnames=diagnostic_fields)
        writer.writeheader()
        for row in diagnostic_rows:
            writer.writerow({field: row.get(field, "") for field in diagnostic_fields})

        node_sum = sum(
            float(row.get("exposure_person_seconds", 0.0))
            for row in diagnostic_rows if row.get("location_type") == "node"
        )
        edge_sum = sum(
            float(row.get("exposure_person_seconds", 0.0))
            for row in diagnostic_rows if row.get("location_type") == "edge"
        )
        initial_sum = sum(
            float(row.get("initial_exposure_person_seconds", 0.0))
            for row in diagnostic_rows
        )
        for location_type, exposure in (
            ("summary_node", node_sum),
            ("summary_edge", edge_sum),
            ("summary_initial", initial_sum),
            ("summary_total", node_sum + edge_sum),
        ):
            writer.writerow({
                "algorithm": result["method"],
                "location_type": location_type,
                "location_id": "ALL",
                "exposure_person_seconds": exposure,
                "initial_exposure_person_seconds": (
                    initial_sum if location_type == "summary_initial" else ""
                ),
            })

    edge_state_fields = [
        "algorithm", "edge", "source_node", "destination_node", "edge_type",
        "length_m", "effective_area_m2", "area_source", "density_exempt",
        "is_physical_edge", "maximum_density_p_per_m2",
        "minimum_speed_m_per_s", "maximum_in_transit_people",
        "cumulative_in_transit_person_seconds",
        "speed_below_0_3_person_seconds",
        "speed_below_0_1_person_seconds",
        "speed_below_0_05_person_seconds",
        "density_2_0_to_3_0_person_seconds",
        "density_3_0_to_3_5_person_seconds",
        "density_3_5_to_4_0_person_seconds",
        "last_occupied_time_seconds",
        "last_observed_in_transit_people",
    ]

    def write_edge_state_rows(filename, rows, *, ranked=False):
        fields = (["rank"] if ranked else []) + edge_state_fields
        with (run_dir / filename).open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for rank, row in enumerate(rows, start=1):
                output = {"algorithm": result["method"], **row}
                if ranked:
                    output["rank"] = rank
                writer.writerow({
                    field: output.get(field, "")
                    for field in fields
                })

    edge_state_rows = list(raw.get("edge_state_diagnostics", []))
    write_edge_state_rows(
        "edge_state_diagnostics.csv",
        edge_state_rows,
    )
    write_edge_state_rows(
        "edge_lowest_speed_top20.csv",
        raw.get("edge_lowest_speed_top20", []),
        ranked=True,
    )
    write_edge_state_rows(
        "edge_low_speed_person_seconds_top20.csv",
        raw.get("edge_low_speed_person_seconds_top20", []),
        ranked=True,
    )
    write_edge_state_rows(
        "final_in_transit_edges.csv",
        raw.get("final_in_transit_edges", []),
    )

    receiving_block_fields = [
        "algorithm", "block_type", "edge", "source_node",
        "destination_node", "rejection_event_count", "rejected_people",
        "blocked_person_seconds",
    ]
    with (run_dir / "receiving_block_diagnostics.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=receiving_block_fields,
        )
        writer.writeheader()
        for row in raw.get("receiving_block_diagnostics", []):
            output = {"algorithm": result["method"], **row}
            writer.writerow({
                field: output.get(field, "")
                for field in receiving_block_fields
            })

    line_low_speed_fields = [
        "algorithm", "line", "cumulative_in_transit_person_seconds",
        "speed_below_0_3_person_seconds",
        "speed_below_0_1_person_seconds",
        "speed_below_0_05_person_seconds",
    ]
    with (run_dir / "edge_low_speed_by_line.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=line_low_speed_fields,
        )
        writer.writeheader()
        for row in raw.get(
            "edge_low_speed_person_seconds_by_line",
            [],
        ):
            output = {"algorithm": result["method"], **row}
            writer.writerow({
                field: output.get(field, "")
                for field in line_low_speed_fields
            })

    high_density_total = float(raw.get("high_density_exposure_person_seconds", 0.0))
    high_density_diag_sum = node_sum + edge_sum
    threshold_equals_cap = abs(
        float(net.HIGH_LOAD_JAM_DENSITY_P_PER_M2) - 4.0
    ) <= 1e-9
    config_diagnostics = raw.get("configuration_density_diagnostics", {})
    diagnosis = [
        "# Metric diagnostics",
        "",
        "## High-density exposure",
        "",
        f"- Jam density: {net.HIGH_LOAD_JAM_DENSITY_P_PER_M2:.6f} p/m².",
        f"- Threshold equals density cap: {threshold_equals_cap}.",
        f"- Node exposure: {node_sum:.6f} person·s.",
        f"- Edge exposure: {edge_sum:.6f} person·s.",
        f"- Initial-state exposure: {initial_sum:.6f} person·s.",
        f"- Independently summed total: {high_density_diag_sum:.6f} person·s.",
        f"- Formal diagnostic total: {high_density_total:.6f} person·s.",
        f"- Sum error: {high_density_diag_sum - high_density_total:.12f} person·s.",
        "- Overflow queues have no unique physical location and are excluded from density exposure; they remain represented in queueing metrics.",
        f"- Default-area nodes: {config_diagnostics.get('default_area_node_count', 0)}; spatially active among them: {config_diagnostics.get('default_area_spatial_node_count', 0)}.",
        f"- Euclidean-fallback edges: {config_diagnostics.get('euclidean_fallback_edge_count', 0)}; included physical exposure edges: {config_diagnostics.get('euclidean_fallback_monitored_edge_count', 0)}.",
        "- Default gate areas cannot affect physical-density exposure while those gates remain spatial-storage exempt. Euclidean-fallback lengths can affect edge area and therefore remain explicitly identified in the CSV.",
        "- This diagnostic is excluded from the formal algorithm comparison.",
        "",
        "## Speed composition",
        "",
        f"- moving_average_speed: {result['moving_average_speed']:.9f} m/s.",
        f"- edge_traversal_average_speed: {result['edge_traversal_avg_speed']:.9f} m/s.",
        f"- effective_evacuation_speed: {result['effective_evacuation_speed']:.9f} m/s.",
        f"- total_movement_distance: {result['total_movement_distance']:.6f} m.",
        f"- moving_person_seconds: {result['moving_person_seconds']:.6f} person·s.",
        f"- total_system_person_seconds: {result['total_system_person_seconds']:.6f} person·s.",
        f"- stationary_person_seconds: {result['stationary_time']:.6f} person·s.",
        f"- resource_queueing_time: {result['resource_queueing_time']:.6f} person·s.",
        f"- spatial_blocked_person_seconds: {result['_diagnostic_spatial_blocked_person_seconds']:.6f} person·s.",
        f"- mean_moving_time: {result['mean_moving_time']:.6f} s/person.",
        f"- mean_stationary_time: {result['mean_stationary_time']:.6f} s/person.",
        f"- diagnostic_mean_resource_queueing_time: {result['mean_queueing_time']:.6f} s/person.",
        f"- mean_total_evacuation_time: {result['mean_total_evacuation_time']:.6f} s/person.",
        f"- Excluded zero-length/topological transition traversals: {raw.get('zero_or_topological_movement_people', 0.0):.0f} people-traversals.",
        "",
        "## Population representation check",
        "",
        f"- Maximum |node occupants + in-transit occupants - remaining occupants|: {raw.get('occupancy_partition_max_error', 0.0):.12f}.",
        "",
        "## Line clearance",
        "",
        f"- Last clearance line: {last_clearance_line or 'unavailable'}.",
    ]
    if diagnostic_metrics:
        (run_dir / "metric_diagnostics.md").write_text(
            "\n".join(diagnosis), encoding="utf-8"
        )

    diagnostics = dict(raw.get("aa_diagnostics", {}))
    edge_receiving_hard_limit = {
        "parameter_name": config_diagnostics.get(
            "edge_receiving_density_parameter_name",
            net.EDGE_RECEIVING_DENSITY_PARAMETER_NAME,
        ),
        "value_people_per_m2": float(config_diagnostics.get(
            "edge_receiving_density_limit_p_per_m2",
            net.EDGE_RECEIVING_DENSITY_LIMIT_P_PER_M2,
        )),
        "formula": config_diagnostics.get(
            "edge_receiving_density_formula",
            net.EDGE_RECEIVING_DENSITY_FORMULA,
        ),
        "source": config_diagnostics.get(
            "edge_receiving_density_source",
            net.EDGE_RECEIVING_DENSITY_SOURCE,
        ),
        "enabled": bool(config_diagnostics.get(
            "edge_receiving_hard_limit_enabled",
            False,
        )),
    }
    for field, default in {
        "astar_call_count": 0,
        "astar_runtime_seconds": 0.0,
        "old_path_evaluation_count": 0,
        "old_path_evaluation_runtime_seconds": 0.0,
        "predicted_queue_query_count": 0,
        "predicted_queue_query_runtime_seconds": 0.0,
        "predicted_queue_scanned_event_count": 0,
        "max_active_batch_count": 0,
        "simulation_step_count": 0,
    }.items():
        diagnostics.setdefault(field, default)
    diagnostics.setdefault("simulation_step_count", int(round(result["evacuation_time"] / net.DELTA_T)))
    diagnostics["edge_receiving_hard_limit"] = (
        edge_receiving_hard_limit
    )
    diagnostics["receiving_block_summary"] = dict(
        raw.get("receiving_block_summary", {})
    )
    diagnostics["edge_state_diagnostics_summary"] = {
        "edge_count": len(edge_state_rows),
        "physical_occupied_edge_count": sum(
            1
            for row in edge_state_rows
            if bool(row.get("is_physical_edge"))
            and row.get("minimum_speed_m_per_s") is not None
        ),
        "lowest_speed_top20_count": len(
            raw.get("edge_lowest_speed_top20", [])
        ),
        "low_speed_person_seconds_top20_count": len(
            raw.get("edge_low_speed_person_seconds_top20", [])
        ),
        "last_in_transit_snapshot_time_seconds": raw.get(
            "last_in_transit_snapshot_time_seconds"
        ),
        "final_in_transit_edge_count": len(
            raw.get("final_in_transit_edges", [])
        ),
        "density_band_intervals": {
            "density_2_0_to_3_0_person_seconds": "[2.0, 3.0)",
            "density_3_0_to_3_5_person_seconds": "[3.0, 3.5)",
            "density_3_5_to_4_0_person_seconds": "[3.5, 4.0)",
        },
        "low_speed_thresholds_are_strictly_below_m_per_s": [
            0.3,
            0.1,
            0.05,
        ],
    }
    diagnostics["mesoscopic_diagnostics"] = raw.get("mesoscopic_diagnostics", {})
    diagnostics["gate_service_diagnostics"] = list(
        raw.get("gate_service_diagnostics", [])
    )
    diagnostics["gate_service_diagnostics_summary"] = dict(
        raw.get("gate_service_diagnostics_summary", {})
    )
    diagnostics["gate_backlog_diagnostics"] = list(
        raw.get("gate_backlog_diagnostics", [])
    )
    diagnostics["improved_gate_density_diagnostics"] = list(
        raw.get("improved_gate_density_diagnostics", [])
    )
    diagnostics["improved_gate_density_diagnostics_summary"] = dict(
        raw.get("improved_gate_density_diagnostics_summary", {})
    )
    diagnostics["improved_temporary_high_cost_diagnostics"] = dict(
        raw.get("improved_temporary_high_cost_diagnostics", {})
    )
    diagnostics["improved_ordinary_crossline_controls"] = list(
        raw.get("improved_ordinary_crossline_controls", [])
    )
    diagnostics["gate_approach_replan_diagnostics_summary"] = {
        "row_count": len(raw.get("gate_approach_replan_diagnostics", [])),
        "connectivity_row_count": len(raw.get("gate_approach_connectivity", [])),
    }
    diagnostics["l7_hall_common_decision_summary"] = dict(
        raw.get("l7_hall_common_decision_summary", {})
    )
    diagnostics["l7_common_hall_topology_audit"] = list(
        raw.get("l7_common_hall_topology_audit", [])
    )
    diagnostics["l7_common_hall_vertical_integration_enabled"] = bool(
        raw.get("l7_common_hall_vertical_integration_enabled", False)
    )
    with (run_dir / "diagnostics.json").open("w", encoding="utf-8") as handle:
        json.dump(diagnostics, handle, ensure_ascii=False, indent=2, default=str)

    gate_replan_rows = list(raw.get("gate_approach_replan_diagnostics", []))
    gate_replan_fields = [
        "simulation_time", "gate_approach", "source_group",
        "passenger_count", "current_gate", "alternative_gates",
        "directed_path_exists", "directed_path_nodes",
        "found_alternative_path", "stay_cost", "best_alternative_cost",
        "gain_ratio", "no_switch_reason",
    ]
    with (run_dir / "gate_approach_replan_diagnostics.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=gate_replan_fields)
        writer.writeheader()
        for row in gate_replan_rows:
            writer.writerow({
                field: row.get(field, "")
                for field in gate_replan_fields
            })

    gate_connectivity_rows = list(raw.get("gate_approach_connectivity", []))
    gate_connectivity_fields = [
        "from_gate_approach", "current_gate", "to_gate",
        "to_gate_approach", "directed_path_exists", "path_nodes",
        "path_length", "contains_stair_or_platform",
        "contains_current_gate", "passes_target_gate",
    ]
    with (run_dir / "gate_approach_connectivity.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=gate_connectivity_fields)
        writer.writeheader()
        for row in gate_connectivity_rows:
            writer.writerow({
                field: row.get(field, "")
                for field in gate_connectivity_fields
            })

    hall_decision_rows = list(
        raw.get("l7_hall_common_decision_diagnostics", [])
    )
    hall_decision_fields = [
        "sim_time", "method", "decision_node", "batch_id",
        "batch_amount", "old_queue", "old_gate", "selected_queue",
        "selected_gate", "candidate_queue_states",
        "candidate_path_costs", "candidate_paths",
        "improvement_ratio", "decision_people",
        "accepted_people", "residual_people",
    ]
    with (run_dir / "l7_hall_common_decisions.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=hall_decision_fields
        )
        writer.writeheader()
        for row in hall_decision_rows:
            writer.writerow({
                field: row.get(field, "")
                for field in hall_decision_fields
            })

    hall_topology_rows = list(
        raw.get("l7_common_hall_topology_audit", [])
    )
    hall_topology_fields = [
        "upstream_node", "decision_node", "length_m",
        "capacity_per_second", "removed_direct_targets",
        "removed_direct_target_count",
    ]
    with (run_dir / "l7_common_hall_topology_audit.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=hall_topology_fields
        )
        writer.writeheader()
        for row in hall_topology_rows:
            writer.writerow({
                field: row.get(field, "")
                for field in hall_topology_fields
            })

    backlog_trace_rows = list(raw.get("gate_backlog_step_trace", []))
    backlog_trace_fields = [
        "sim_time_seconds",
        "gate",
        "gate_node_waiting_people",
        "gate_node_occupancy_people",
        "gate_upstream_blocked_people",
        "gate_spillback_queue_people",
        "gate_routing_queue_people",
        "gate_service_backlog_people",
        "improved_queue_q_used",
        "service_rate_people_per_second",
        "queue_wait_cost_seconds",
        "selected_people_this_step",
        "served_people_this_step",
    ]
    with (run_dir / "gate_backlog_step_trace.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=backlog_trace_fields)
        writer.writeheader()
        writer.writerows(backlog_trace_rows)

    high_cost_trace_rows = list(
        raw.get("improved_temporary_high_cost_trace", [])
    )
    high_cost_trace_fields = [
        "sim_time_seconds",
        "target_type",
        "target_gate",
        "exit_direction",
        "current_density_p_per_m2",
        "temporary_high_cost_active",
        "latest_recovery_time_seconds",
        "current_path_cost",
        "selected_people_this_step",
    ]
    with (run_dir / "improved_temporary_high_cost_trace.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=high_cost_trace_fields,
        )
        writer.writeheader()
        writer.writerows(high_cost_trace_rows)

    high_cost_step_rows = list(
        raw.get(
            "improved_temporary_high_cost_step_diagnostics", []
        )
    )
    high_cost_step_fields = [
        "sim_time_seconds",
        "temporary_high_cost_events",
        "recovered_next_step_events",
        "high_cost_active_edges",
        "stale_high_cost_state_count",
    ]
    with (
        run_dir / "improved_temporary_high_cost_step_diagnostics.csv"
    ).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=high_cost_step_fields,
        )
        writer.writeheader()
        writer.writerows(high_cost_step_rows)

    crossline_rows = list(
        raw.get("improved_ordinary_crossline_controls", [])
    )
    crossline_fields = [
        "entry_edge", "source_line", "target_line", "target_gates",
        "eligible_target_gates", "blocked_target_gates",
        "source_all_congested", "allowed",
    ]
    with (run_dir / "improved_ordinary_crossline_controls.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=crossline_fields)
        writer.writeheader()
        for row in crossline_rows:
            writer.writerow({
                field: row.get(field, "")
                for field in crossline_fields
            })

    candidate_rows = list(raw.get("step0_aa_candidate_diagnostics", []))
    candidate_fields = [
        "category", "sim_time", "source_group", "start_node",
        "batch_people", "chosen_exit", "candidate_exit", "feasible",
        "walking_time", "front_queue_people_sum", "queue_wait_time",
        "current_batch_gate_service_time",
        "current_batch_gate_service_time_formula",
        "terminal_edge_batch_mean_discharge_time",
        "objective_with_terminal_discharge_diagnostic", "spatial_wait_time",
        "density_risk", "objective_cost", "path",
    ]
    with (run_dir / "candidate_route_costs.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_fields)
        writer.writeheader()
        for row in candidate_rows:
            output = dict(row)
            output["path"] = " -> ".join(
                map(str, row.get("path", []))
            )
            writer.writerow({
                field: output.get(field, "")
                for field in candidate_fields
            })

    simulation_graph = result.get("_simulation_graph")
    graph_depths = {}
    graph_line_ids = list(net.GATE_QUEUE_AREA_LINES_DEFAULT)
    if simulation_graph is not None:
        graph_depths = dict(
            simulation_graph.graph.get(
                "gate_queue_area_depth_m_by_line", {}
            )
        )
        graph_line_ids = list(
            simulation_graph.graph.get(
                "gate_queue_area_lines", graph_line_ids
            )
        )
    if not graph_depths:
        graph_depths = {
            line_id: float(
                net.GATE_QUEUE_DEPTH_M_BY_LINE_DEFAULT.get(
                    line_id, net.GATE_QUEUE_DEPTH_M_DEFAULT
                )
            )
            for line_id in graph_line_ids
        }
    graph_settings = simulation_graph.graph if simulation_graph is not None else {}
    run_config = {
        "mode": mode,
        "algorithm": result["method"],
        "population": total_people,
        "gain_min": 0.20 if mode == 4 else None,
        "delta_t_seconds": net.DELTA_T,
        "collect_detailed_series": False,
        "diagnostic_metrics": bool(diagnostic_metrics),
        "density_dependent_flow": True,
        "spillback_enabled": True,
        "service_node_spatial_storage_mode": str(
            graph_settings.get("service_node_spatial_storage_mode", "exempt")
        ),
        "gate_storage_area_formula": (
            "finite Gate service buffer uses the corresponding Gate Queue effective area"
        ),
        "improved_gate_queue_term": bool(
            graph_settings.get("improved_gate_queue_term", False)
        ),
        "improved_shared_travel_time": bool(
            graph_settings.get("improved_shared_travel_time", False)
        ),
        "high_density_threshold_p_per_m2": float(
            spr.PAPER_HIGH_DENSITY_THRESHOLD
        ),
        "gate_queue_areas": {
            "enabled": bool(net.GATE_QUEUE_AREAS_ENABLED_DEFAULT),
            "line_ids": graph_line_ids,
            "uniform_depth_m": None,
            "depth_m_by_line": graph_depths,
            "service_edge_length_m": float(net.GATE_QUEUE_SERVICE_EDGE_LENGTH_M),
            "area_formula": "configured_gate_bank_width_m * depth_m_by_line[line_id]",
            "area_source": "line_specific_gate_queue_depth",
        },
        "edge_receiving_hard_limit": edge_receiving_hard_limit,
        "network_module": str(Path(net.__file__).resolve()),
        "model_revision": MODEL_REVISION,
    }
    with (run_dir / "run_config.json").open("w", encoding="utf-8") as handle:
        json.dump(run_config, handle, ensure_ascii=False, indent=2)
    pathfinder_written = (
        result["method"] in {
            "ImprovedAStar",
            "AdaptiveQueueAwareAStar",
        }
        and result.get("_simulation_graph") is not None
    )
    if pathfinder_written:
        route_summary = _write_pathfinder_route_outputs(
            result, run_dir, mode, total_people
        )
        diagnostics_path = run_dir / "diagnostics.json"
        with diagnostics_path.open("r", encoding="utf-8") as handle:
            diagnostics_payload = json.load(handle)
        diagnostics_payload.update({
            "complete_path_count": int(
                route_summary["complete_routes"]
            ),
            "small_path_people_threshold": int(
                route_summary["small_route_people_threshold"]
            ),
            "small_path_count": int(
                route_summary["small_routes"]
            ),
            "discontinuous_path_count": int(
                route_summary["discontinuous_routes"]
            ),
            "cycle_path_count": int(
                route_summary["routes_with_cycles"]
            ),
            "reverse_path_count": int(
                route_summary["routes_with_reverse_moves"]
            ),
        })
        with diagnostics_path.open("w", encoding="utf-8") as handle:
            json.dump(
                diagnostics_payload,
                handle,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        print("Pathfinder route allocation:", flush=True)
        print(f"  source groups: {route_summary['source_groups']}", flush=True)
        print(f"  complete routes: {route_summary['complete_routes']}", flush=True)
        print(
            f"  total allocated people: {route_summary['total_allocated_people']}",
            flush=True,
        )
        print(
            "  people conservation error: "
            f"{route_summary['people_conservation_error']}",
            flush=True,
        )
        print(
            "  source-group percentage errors: "
            f"{route_summary['source_group_percentage_errors']}",
            flush=True,
        )
        print(
            f"  discontinuous routes: {route_summary['discontinuous_routes']}",
            flush=True,
        )
        print(
            f"  routes with cycles: {route_summary['routes_with_cycles']}",
            flush=True,
        )
        print(
            "  routes with reverse moves: "
            f"{route_summary['routes_with_reverse_moves']}",
            flush=True,
        )
        print(
            "  small routes "
            f"(<= {route_summary['small_route_people_threshold']} people): "
            f"{route_summary['small_routes']}",
            flush=True,
        )
        print("  output: pathfinder_route_allocation.csv", flush=True)
        print("  output: pathfinder_group_setup.csv", flush=True)
        print("  output: pathfinder_route_validation.csv", flush=True)
        print("  output: raw_route_validation.csv", flush=True)
        print("  output: merged_route_validation.csv", flush=True)
        print("  output: l2_l7_exit_details.csv", flush=True)
        print("  output: l2_l7_exit_summary.csv", flush=True)
    _write_run_readme(run_dir, result, pathfinder_written)


def _read_single_summary(run_dir):
    path = Path(run_dir) / "summary_metrics.csv"
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        row = next(csv.DictReader(handle))
    numeric_fields = {
        "target_people", "evacuated_people", "remaining_people",
        "T95_seconds", "T100_seconds",
        "cumulative_stationary_person_seconds",
        "mean_stationary_time_seconds_per_person",
        "mean_station_throughput_people_per_second",
        "moving_average_speed_m_per_s", "edge_traversal_average_speed_m_per_s",
        "effective_evacuation_speed_m_per_s", "total_movement_distance_m",
        "moving_person_seconds", "total_system_person_seconds",
        "mean_moving_time_seconds_per_person",
        "mean_total_evacuation_time_seconds_per_person", "exit_load_jain_index",
        "key_facility_load_jain_index", "wall_clock_runtime_seconds",
    }
    for field in numeric_fields:
        if field in row and row[field] != "":
            row[field] = float(row[field])
    # Read-only compatibility for old result folders. New formal outputs write
    # exactly one canonical name for each metric.
    compatibility_names = {
        "T95_seconds": ("T95",),
        "T100_seconds": ("T100",),
        "cumulative_stationary_person_seconds": (
            "cumulative_queueing_person_seconds",
            "queueing_time_person_seconds",
            "resource_queueing_time_person_seconds",
        ),
        "mean_stationary_time_seconds_per_person": (
            "mean_queueing_time_seconds_per_person",
            "mean_queueing_time_seconds",
        ),
        "mean_station_throughput_people_per_second": ("mean_station_throughput",),
        "mean_moving_time_seconds_per_person": ("mean_moving_time_seconds",),
        "mean_total_evacuation_time_seconds_per_person": (
            "mean_total_evacuation_time_seconds",
        ),
    }
    for canonical, old_names in compatibility_names.items():
        if canonical in row and row[canonical] != "":
            continue
        for old_name in old_names:
            if row.get(old_name, "") != "":
                row[canonical] = float(row[old_name])
                break
        else:
            row[canonical] = 0.0
    if "moving_average_speed_m_per_s" not in row:
        row["moving_average_speed_m_per_s"] = float(
            row.get("average_speed_m_per_s", 0.0)
        )
    row.setdefault("edge_traversal_average_speed_m_per_s", 0.0)
    row.setdefault("effective_evacuation_speed_m_per_s", 0.0)
    return row


def compare_saved_results(first_dir, second_dir):
    rows = [_read_single_summary(first_dir), _read_single_summary(second_dir)]
    by_method = {row["method"]: row for row in rows}
    if "ImprovedAStar" not in by_method or "AdaptiveQueueAwareAStar" not in by_method:
        raise ValueError("The two result directories must contain ImprovedAStar and AdaptiveQueueAwareAStar respectively.")
    improved = by_method["ImprovedAStar"]
    adaptive = by_method["AdaptiveQueueAwareAStar"]
    common_parent = Path(first_dir).resolve().parent
    if Path(second_dir).resolve().parent != common_parent:
        common_parent = Path("outputs") / "algorithm_compare" / "merged_results"
    common_parent.mkdir(parents=True, exist_ok=True)
    fields = [
        ("T95_seconds", False), ("T100_seconds", False),
        ("cumulative_stationary_person_seconds", False),
        ("mean_stationary_time_seconds_per_person", False),
        ("effective_evacuation_speed_m_per_s", True),
        ("mean_total_evacuation_time_seconds_per_person", False),
        ("mean_station_throughput_people_per_second", True),
        ("moving_average_speed_m_per_s", True),
        ("edge_traversal_average_speed_m_per_s", True),
        ("mean_moving_time_seconds_per_person", False),
        ("total_movement_distance_m", None),
        ("exit_load_jain_index", True),
        ("key_facility_load_jain_index", True),
        ("wall_clock_runtime_seconds", False),
    ]
    comparison_rows = []
    for field, higher_is_better in fields:
        baseline = improved[field]
        ours = adaptive[field]
        if higher_is_better is None:
            improvement = ""
        else:
            improvement = (
                (ours - baseline) / max(abs(baseline), 1e-9) * 100.0
                if higher_is_better
                else (baseline - ours) / max(abs(baseline), 1e-9) * 100.0
            )
        comparison_rows.append((field, baseline, ours, improvement))
    with (common_parent / "comparison_summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "ImprovedAStar", "AdaptiveQueueAwareAStar", "improvement_pct"])
        writer.writerows(comparison_rows)
    report = [
        "# Mode 4 formal comparison report", "",
        "| Metric | ImprovedAStar | AdaptiveQueueAwareAStar | Improvement |",
        "|---|---:|---:|---:|",
    ]
    for field, baseline, ours, improvement in comparison_rows:
        improvement_text = (
            "diagnostic" if improvement == "" else f"{improvement:+.2f}%"
        )
        report.append(
            f"| {field} | {baseline:.6f} | {ours:.6f} | {improvement_text} |"
        )
    report.extend([
        "", "## Conservation", "",
        f"- ImprovedAStar: target={improved['target_people']:.0f}, evacuated={improved['evacuated_people']:.0f}, remaining={improved['remaining_people']:.0f}, completed={improved.get('completed', '')}, termination={improved.get('termination_reason', '')}.",
        f"- AdaptiveQueueAwareAStar: target={adaptive['target_people']:.0f}, evacuated={adaptive['evacuated_people']:.0f}, remaining={adaptive['remaining_people']:.0f}, completed={adaptive.get('completed', '')}, termination={adaptive.get('termination_reason', '')}.",
        "",
        "## Metric interpretation",
        "",
        "- High-density exposure was removed from the formal comparison because the configured density cap equals the exposure threshold and the observed exposure is dominated by the common initial train-unloading state.",
        "- Formal waiting uses `cumulative_stationary_person_seconds`, which includes resource queues, spatially blocked people, and other non-moving in-station people.",
        "- Primary speed comparison: `effective_evacuation_speed_m_per_s`.",
        "- `moving_average_speed_m_per_s` and `edge_traversal_average_speed_m_per_s` diagnose motion only and exclude waiting.",
    ])

    report.extend([
        "",
        "## Speed composition",
        "",
        "| Component | ImprovedAStar | AdaptiveQueueAwareAStar | AA change |",
        "|---|---:|---:|---:|",
    ])
    for field in (
        "total_movement_distance_m",
        "moving_person_seconds",
        "total_system_person_seconds",
        "mean_moving_time_seconds_per_person",
        "mean_stationary_time_seconds_per_person",
        "mean_total_evacuation_time_seconds_per_person",
    ):
        baseline = float(improved.get(field, 0.0))
        ours = float(adaptive.get(field, 0.0))
        change = (ours - baseline) / max(abs(baseline), 1e-9) * 100.0
        report.append(
            f"| {field} | {baseline:.6f} | {ours:.6f} | {change:+.2f}% |"
        )

    report.extend(["", "## Line T95 and clearance", ""])
    for method, run_dir in (
        ("ImprovedAStar", first_dir if improved is rows[0] else second_dir),
        ("AdaptiveQueueAwareAStar", first_dir if adaptive is rows[0] else second_dir),
    ):
        line_path = Path(run_dir) / "line_clearance.csv"
        if not line_path.exists():
            report.append(f"- {method}: line_clearance.csv unavailable.")
            continue
        with line_path.open("r", newline="", encoding="utf-8-sig") as handle:
            line_data = list(csv.DictReader(handle))
        last_line = next(
            (
                row["line"] for row in line_data
                if str(row.get("is_last_clearance_line", "")).lower() == "true"
            ),
            "unavailable",
        )
        report.append(f"- {method} last clearance line: {last_line}.")
        for row in line_data:
            report.append(
                f"  - {row['line']}: T95={row.get('T95_seconds', row.get('T95', ''))} s, "
                f"clearance={row.get('clearance_time_seconds', row.get('clearance_time', ''))} s."
            )
    (common_parent / "mode4_formal_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Comparison written to: {common_parent}", flush=True)


def main():
    import argparse
    import datetime

    parser = argparse.ArgumentParser(description="Formal ImprovedAStar / AdaptiveQueueAwareAStar comparison")
    parser.add_argument("--mode", type=int, default=4, choices=[1, 4])
    parser.add_argument("--algorithm", choices=["improved", "aa", "both"], default="both")
    parser.add_argument("--compare-results", nargs=2, metavar=("IMPROVED_DIR", "AA_DIR"))
    parser.add_argument(
        "--edge-receiving-density-limit",
        type=float,
        default=net.EDGE_RECEIVING_DENSITY_LIMIT_P_PER_M2,
        metavar="PEOPLE_PER_M2",
        help=(
            "shared AA/Improved edge receiving hard-limit density in people/m^2 "
            f"(default: {net.EDGE_RECEIVING_DENSITY_LIMIT_P_PER_M2!r})"
        ),
    )
    parser.add_argument(
        "--diagnostic-metrics",
        action="store_true",
        help="write optional high-density diagnostic files; excluded from formal comparison",
    )
    args = parser.parse_args()
    if (
        not math.isfinite(args.edge_receiving_density_limit)
        or args.edge_receiving_density_limit <= 0.0
    ):
        parser.error(
            "--edge-receiving-density-limit must be a finite value greater than 0"
        )

    # Direct "Run Python File" execution uses the parser defaults:
    # Mode 4 and both algorithms in sequence. Explicit CLI arguments may still
    # select a single algorithm for targeted diagnostics.
    if False:
        print("\n请选择疏散场景：")
        print("  [1] Mode 1 低负荷（2187人）")
        print("  [4] Mode 4 高负荷（17905人）")
        while True:
            choice = input("请输入 1 或 4：").strip()
            if choice in {"1", "4"}:
                args.mode = int(choice)
                break
            print("输入无效，请重新输入。")

        print("\n请选择运行算法：")
        print("  [1] ImprovedAStar（生成Pathfinder完整路线文件）")
        print("  [2] AdaptiveQueueAwareAStar")
        print("  [3] 两种算法依次运行并生成合并报告")
        algorithm_choices = {
            "1": "improved",
            "2": "aa",
            "3": "both",
        }
        while True:
            choice = input("请输入 1、2 或 3：").strip()
            if choice in algorithm_choices:
                args.algorithm = algorithm_choices[choice]
                break
            print("输入无效，请重新输入。")

        diagnostic_choice = input(
            "\n是否额外生成高密度内部诊断文件？[y/N]："
        ).strip().lower()
        args.diagnostic_metrics = diagnostic_choice in {"y", "yes"}

        print(
            f"\n即将运行：Mode {args.mode}，algorithm={args.algorithm}，"
            f"diagnostic_metrics={args.diagnostic_metrics}\n",
            flush=True,
        )

    if args.compare_results:
        compare_saved_results(*args.compare_results)
        return

    global MODE
    MODE = args.mode
    net.OUTPUT_DIR = None
    graph = net.build_graph()
    # Formal Improved baseline: exclude the non-published Q/mu gate-wait term.
    graph.graph["improved_gate_queue_term"] = False
    # Formal Improved baseline: use the literature density-speed travel time.
    graph.graph["improved_shared_travel_time"] = False
    graph.graph["density_dependent_flow"] = True
    graph.graph["spillback_enabled"] = True
    graph.graph[net.EDGE_RECEIVING_DENSITY_PARAMETER_NAME] = (
        args.edge_receiving_density_limit
    )
    graph.graph["aa_reroute_gain_min"] = 0.20
    graph.graph["aa_spatial_batch_arrival_spread_enabled"] = True
    graph.graph["aa_spatial_arrival_spread_seconds"] = 1.0
    if MODE == 4:
        graph.graph["split_l2_train_source_groups_by_zone"] = True
    pop_dict, total_people = build_population()
    if MODE == 4 and total_people != 17905:
        raise RuntimeError(f"Mode 4 population must be 17905, got {total_people}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root_dir = Path("outputs") / "algorithm_compare" / f"mode{MODE}_{timestamp}"
    root_dir.mkdir(parents=True, exist_ok=True)
    selected = []
    if args.algorithm in {"improved", "both"}:
        selected.append((net.PAPER_SINGLE_PATH_METHOD, "ImprovedAStar"))
    if args.algorithm in {"aa", "both"}:
        selected.append((net.OUR_SINGLE_PATH_METHOD, "AdaptiveQueueAwareAStar"))

    completed_dirs = []
    for method, method_name in selected:
        run_dir = root_dir / method_name
        run_dir.mkdir(parents=True, exist_ok=True)
        with (run_dir / "run.log").open("w", encoding="utf-8") as log_handle:
            log_handle.write(
                f"started method={method_name} mode={MODE} population={total_people} "
                f"gain_min={0.20 if MODE == 4 else 'n/a'} "
                "collect_detailed_series=False "
                f"{net.EDGE_RECEIVING_DENSITY_PARAMETER_NAME}="
                f"{args.edge_receiving_density_limit!r}\n"
            )
        print(f"Running {method_name}; output={run_dir}", flush=True)
        result = run_one(
            graph,
            pop_dict,
            method,
            method_name,
            collect_detailed_series=False,
            run_directory=run_dir,
        )
        _write_single_algorithm_outputs(
            result,
            run_dir,
            MODE,
            total_people,
            diagnostic_metrics=args.diagnostic_metrics,
        )
        result.pop("_simulation_graph", None)
        completed_dirs.append(run_dir)
        print(f"Saved {method_name}: {run_dir}", flush=True)

    if len(completed_dirs) == 2:
        compare_saved_results(completed_dirs[0], completed_dirs[1])


if __name__ == "__main__":
    main()
