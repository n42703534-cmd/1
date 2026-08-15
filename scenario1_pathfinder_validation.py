from __future__ import annotations

import copy
import csv
import html
import math
import statistics
import sys
import types
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENDORED_SITE_PACKAGES = ROOT / "__vendor_site_packages"
PY38_SITE_PACKAGES = ROOT / "__tmp_py38_deps"

OUTPUT_METHOD_SUMMARY = ROOT / "201_scenario1_pathfinder_method_summary.csv"
OUTPUT_LINE_CLEARANCE = ROOT / "202_scenario1_pathfinder_line_clearance.csv"
OUTPUT_EXIT_SUMMARY = ROOT / "203_scenario1_pathfinder_exit_summary.csv"
OUTPUT_EXIT_SOURCE_GROUP_SUMMARY = ROOT / "203b_scenario1_pathfinder_exit_by_source_group.csv"
OUTPUT_SPATIAL_BOTTLENECK_SUMMARY = ROOT / "203c_scenario1_pathfinder_spatial_bottlenecks.csv"
OUTPUT_ROUTE_SUMMARY = ROOT / "204_scenario1_pathfinder_reroute_summary.csv"
OUTPUT_ABLATION_SUMMARY = ROOT / "205_scenario1_pathfinder_ablation_summary.csv"
OUTPUT_MECHANISM_DETAIL = ROOT / "206_scenario1_pathfinder_mechanism_detail.csv"
OUTPUT_MACRO_CHART = ROOT / "207_scenario1_pathfinder_macro_metrics.svg"
OUTPUT_CLEARANCE_CHART = ROOT / "208_scenario1_pathfinder_line_clearance.svg"
OUTPUT_REROUTE_CHART = ROOT / "209_scenario1_pathfinder_reroute_summary.svg"
OUTPUT_ABLATION_CHART = ROOT / "210_scenario1_pathfinder_ablation.svg"
OUTPUT_MECHANISM_CHART = ROOT / "211_scenario1_pathfinder_mechanism.svg"
OUTPUT_REPORT = ROOT / "212_scenario1_pathfinder_validation_report.md"

METHOD_COLORS = {
    "PaperImprovedAStar": "#59A14F",
    "AdaptiveQueueAwareAStar": "#E15759",
    "NoWaitingTime": "#F28E2B",
}

SPATIAL_BOTTLENECK_MIN_START_S = 5.0
SPATIAL_BOTTLENECK_MIN_SUSTAIN_S = 5.0


def _bootstrap_runtime():
    # `__vendor_site_packages` only contains pure-Python helpers and is safe
    # across interpreters, while `__tmp_py38_deps` includes Python 3.8 binary
    # wheels (notably numpy) and must not be injected into 3.12+ runtimes.
    if VENDORED_SITE_PACKAGES.exists():
        sys.path.insert(0, str(VENDORED_SITE_PACKAGES))

    if sys.version_info[:2] == (3, 8) and PY38_SITE_PACKAGES.exists():
        sys.path.insert(0, str(PY38_SITE_PACKAGES))

    try:
        import pandas  # noqa: F401
    except Exception:
        pd = types.ModuleType("pandas")

        class _DummyDataFrame:
            def __init__(self, rows=None, *args, **kwargs):
                self.rows = list(rows or [])

            def to_csv(self, *args, **kwargs):
                raise RuntimeError("Dummy pandas.DataFrame cannot write CSV in this script.")

        pd.DataFrame = _DummyDataFrame
        sys.modules["pandas"] = pd

    try:
        import matplotlib.pyplot  # noqa: F401
        import matplotlib.patches  # noqa: F401
    except Exception:
        matplotlib = types.ModuleType("matplotlib")
        pyplot = types.ModuleType("matplotlib.pyplot")
        patches = types.ModuleType("matplotlib.patches")

        def _noop(*args, **kwargs):
            return None

        pyplot.figure = _noop
        pyplot.subplots = lambda *args, **kwargs: (None, None)
        pyplot.plot = _noop
        pyplot.bar = _noop
        pyplot.savefig = _noop
        pyplot.close = _noop
        pyplot.tight_layout = _noop
        pyplot.grid = _noop
        pyplot.xlabel = _noop
        pyplot.ylabel = _noop
        pyplot.title = _noop
        pyplot.legend = _noop
        pyplot.suptitle = _noop
        pyplot.rcParams = {}
        patches.Patch = object

        matplotlib.pyplot = pyplot
        matplotlib.patches = patches
        sys.modules["matplotlib"] = matplotlib
        sys.modules["matplotlib.pyplot"] = pyplot
        sys.modules["matplotlib.patches"] = patches


_bootstrap_runtime()

import network  # noqa: E402
import single_path_routing as spr  # noqa: E402


SCENARIO1_METHODS = [
    ("PaperImprovedAStar", spr.PAPER_SINGLE_PATH_METHOD),
    ("AdaptiveQueueAwareAStar", spr.OUR_SINGLE_PATH_METHOD),
]

ABLATION_METHODS = [
    ("AdaptiveQueueAwareAStar", spr.OUR_SINGLE_PATH_METHOD),
    ("NoWaitingTime", spr.OUR_NO_WAITING_TIME_METHOD),
]

STATION_BASE_LOADS = {
    "L2": {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
    "L7": {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
    "L16": {"platform_waiting": 42, "hall_people": 15, "transfer_people": 27},
    "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
    "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
}


def build_scenario1_pop_dict():
    current_pop_dict = {}
    for line in network.TRAIN_PHYSICS:
        base = STATION_BASE_LOADS[line]
        current_pop_dict[line] = {
            "train_1": 0,
            "train_2": 0,
            "platform_waiting": int(base["platform_waiting"]),
            "hall_people": int(base["hall_people"]),
            "transfer_people": int(base["transfer_people"]),
        }
    return current_pop_dict


def write_csv(path, rows, fieldnames):
    target_path = Path(path)
    try_paths = [target_path, target_path.with_name(f"{target_path.stem}__updated{target_path.suffix}")]
    last_error = None
    for candidate in try_paths:
        try:
            with open(candidate, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            return candidate
        except PermissionError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error


def flatten_values(series_map):
    values = []
    for series in series_map.values():
        values.extend(float(value) for value in series)
    return values or [0.0]


def nice_tick_step(min_value, max_value, target_ticks=5):
    span = max(max_value - min_value, 1e-9)
    raw = span / max(target_ticks, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    residual = raw / magnitude
    if residual <= 1:
        nice = 1
    elif residual <= 2:
        nice = 2
    elif residual <= 5:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


def axis_bounds(values):
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        if maximum == 0:
            maximum = 1.0
        else:
            minimum = min(0.0, minimum * 0.9)
            maximum = maximum * 1.1

    if minimum >= 0:
        minimum = 0.0
        maximum *= 1.08
    else:
        padding = (maximum - minimum) * 0.08
        minimum -= padding
        maximum += padding

    step = nice_tick_step(minimum, maximum)
    axis_min = math.floor(minimum / step) * step
    axis_max = math.ceil(maximum / step) * step
    if axis_max <= axis_min:
        axis_max = axis_min + step
    return axis_min, axis_max, step


def svg_text(text):
    return html.escape(str(text), quote=True)


def write_grouped_bar_chart_svg(path, title, categories, series_map, colors, y_label):
    width = 1040
    height = 620
    margin_left = 96
    margin_right = 24
    margin_top = 72
    margin_bottom = 92
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    values = flatten_values(series_map)
    axis_min, axis_max, step = axis_bounds(values)
    axis_span = axis_max - axis_min
    zero_y = margin_top + plot_height - ((0.0 - axis_min) / axis_span) * plot_height

    def y_to_svg(value):
        return margin_top + plot_height - ((value - axis_min) / axis_span) * plot_height

    series_names = list(series_map.keys())
    group_width = plot_width / max(len(categories), 1)
    inner_width = group_width * 0.72
    bar_width = inner_width / max(len(series_names), 1)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2:.1f}" y="34" text-anchor="middle" font-size="24" font-family="Arial" font-weight="bold">{svg_text(title)}</text>',
        f'<text x="18" y="{margin_top + plot_height / 2:.1f}" transform="rotate(-90 18,{margin_top + plot_height / 2:.1f})" text-anchor="middle" font-size="14" font-family="Arial">{svg_text(y_label)}</text>',
    ]

    tick = axis_min
    while tick <= axis_max + step * 0.5:
        y = y_to_svg(tick)
        lines.append(f'<line x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#E3E3E3" stroke-width="1"/>')
        lines.append(f'<text x="{margin_left - 12}" y="{y + 5:.2f}" text-anchor="end" font-size="12" font-family="Arial" fill="#444">{svg_text(round(tick, 3))}</text>')
        tick += step

    lines.append(f'<line x1="{margin_left}" y1="{zero_y:.2f}" x2="{width - margin_right}" y2="{zero_y:.2f}" stroke="#666" stroke-width="1.2"/>')

    for idx, category in enumerate(categories):
        group_left = margin_left + idx * group_width + (group_width - inner_width) / 2.0
        label_x = margin_left + (idx + 0.5) * group_width
        lines.append(f'<text x="{label_x:.2f}" y="{height - 26}" text-anchor="middle" font-size="12" font-family="Arial">{svg_text(category)}</text>')
        for series_idx, series_name in enumerate(series_names):
            value = float(series_map[series_name][idx])
            bar_x = group_left + series_idx * bar_width + bar_width * 0.08
            actual_bar_width = bar_width * 0.84
            bar_y = y_to_svg(max(value, 0.0))
            bar_base_y = y_to_svg(min(value, 0.0))
            rect_y = min(bar_y, bar_base_y)
            rect_h = max(abs(bar_base_y - bar_y), 1.0)
            color = colors.get(series_name, "#4E79A7")
            lines.append(
                f'<rect x="{bar_x:.2f}" y="{rect_y:.2f}" width="{actual_bar_width:.2f}" height="{rect_h:.2f}" '
                f'fill="{color}" stroke="#333" stroke-width="0.8"/>'
            )

    legend_x = margin_left
    legend_y = height - 58
    for idx, series_name in enumerate(series_names):
        x = legend_x + idx * 188
        color = colors.get(series_name, "#4E79A7")
        lines.append(f'<rect x="{x}" y="{legend_y}" width="16" height="16" fill="{color}" stroke="#333" stroke-width="0.7"/>')
        lines.append(f'<text x="{x + 24}" y="{legend_y + 13}" font-size="13" font-family="Arial">{svg_text(series_name)}</text>')

    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_stacked_bar_chart_svg(path, title, categories, stack_order, values_by_category, colors, y_label):
    width = 980
    height = 580
    margin_left = 96
    margin_right = 24
    margin_top = 72
    margin_bottom = 92
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    totals = [sum(max(0.0, float(values_by_category[category].get(stack_key, 0.0))) for stack_key in stack_order) for category in categories]
    axis_min, axis_max, step = axis_bounds(totals)
    axis_span = axis_max - axis_min

    def y_to_svg(value):
        return margin_top + plot_height - ((value - axis_min) / axis_span) * plot_height

    group_width = plot_width / max(len(categories), 1)
    bar_width = group_width * 0.38

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2:.1f}" y="34" text-anchor="middle" font-size="24" font-family="Arial" font-weight="bold">{svg_text(title)}</text>',
        f'<text x="18" y="{margin_top + plot_height / 2:.1f}" transform="rotate(-90 18,{margin_top + plot_height / 2:.1f})" text-anchor="middle" font-size="14" font-family="Arial">{svg_text(y_label)}</text>',
    ]

    tick = axis_min
    while tick <= axis_max + step * 0.5:
        y = y_to_svg(tick)
        lines.append(f'<line x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#E3E3E3" stroke-width="1"/>')
        lines.append(f'<text x="{margin_left - 12}" y="{y + 5:.2f}" text-anchor="end" font-size="12" font-family="Arial" fill="#444">{svg_text(round(tick, 3))}</text>')
        tick += step

    for idx, category in enumerate(categories):
        bar_x = margin_left + (idx + 0.5) * group_width - bar_width / 2.0
        running_total = 0.0
        for stack_key in stack_order:
            value = max(0.0, float(values_by_category[category].get(stack_key, 0.0)))
            if value <= 0:
                continue
            y_top = y_to_svg(running_total + value)
            y_bottom = y_to_svg(running_total)
            lines.append(
                f'<rect x="{bar_x:.2f}" y="{y_top:.2f}" width="{bar_width:.2f}" height="{(y_bottom - y_top):.2f}" '
                f'fill="{colors.get(stack_key, "#4E79A7")}" stroke="#333" stroke-width="0.8"/>'
            )
            running_total += value
        label_x = margin_left + (idx + 0.5) * group_width
        lines.append(f'<text x="{label_x:.2f}" y="{height - 26}" text-anchor="middle" font-size="12" font-family="Arial">{svg_text(category)}</text>')

    legend_x = margin_left
    legend_y = height - 58
    for idx, stack_key in enumerate(stack_order):
        x = legend_x + idx * 180
        lines.append(f'<rect x="{x}" y="{legend_y}" width="16" height="16" fill="{colors.get(stack_key, "#4E79A7")}" stroke="#333" stroke-width="0.7"/>')
        lines.append(f'<text x="{x + 24}" y="{legend_y + 13}" font-size="13" font-family="Arial">{svg_text(stack_key)}</text>')

    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def initial_state_for_sources(graph, pop_dict):
    state = copy.deepcopy(graph)
    network.init_people(state, pop_dict, apply_noise=False)
    return state


def tracked_source_nodes(graph, pop_dict):
    state = initial_state_for_sources(graph, pop_dict)
    sources = []
    allowed_types = {
        "platform_waiting_zone",
        "platform",
        "train",
        "train_car",
        "stair",
        "escalator",
        "virtual",
    }
    for node, data in state.nodes(data=True):
        if float(data.get("people", 0.0)) <= 0.1:
            continue
        if data.get("type") == "exit":
            continue
        if data.get("type") not in allowed_types:
            continue
        if state.out_degree(node) <= 1:
            continue
        sources.append(node)
    return sorted(sources)


def exit_balance_metrics(metrics):
    usage = metrics.get("exit_usage", {})
    total = sum(float(value) for value in usage.values())
    shares = [float(value) / total for value in usage.values() if total > 0 and float(value) > 0]
    hhi = sum(share * share for share in shares)
    max_share = max(shares) if shares else 0.0
    return {
        "active_exit_count": len(shares),
        "exit_hhi": hhi,
        "max_exit_share": max_share,
    }


def bottleneck_summary(metrics, top_k=5):
    rows = []
    for node, stat in metrics.get("node_stats", {}).items():
        queue_seconds = float(stat.get("queue_seconds", 0.0))
        if queue_seconds <= 0:
            continue
        rows.append(
            {
                "node": node,
                "queue_seconds": queue_seconds,
                "peak_people": float(stat.get("peak_people", 0.0)),
                "peak_density": float(stat.get("peak_density", 0.0)),
            }
        )
    rows.sort(key=lambda row: (row["queue_seconds"], row["peak_density"]), reverse=True)
    return rows[:top_k]


def dimension2_node_class(node):
    if node.startswith("Gate_"):
        return "gate"
    if node.startswith("Escalator_"):
        return "escalator"
    if node.startswith("Stair_"):
        return "stair"
    if node.startswith("Transfer_"):
        return "transfer"
    return ""


def dimension2_node_usable_in_pathfinder(node):
    node_class = dimension2_node_class(node)
    if not node_class:
        return False
    if node_class == "escalator" and "_Exit" in node:
        return False
    return True


def sustained_over_threshold_window(
    times,
    values,
    area,
    density_threshold,
    min_start_s=SPATIAL_BOTTLENECK_MIN_START_S,
    min_sustain_s=SPATIAL_BOTTLENECK_MIN_SUSTAIN_S,
):
    if not times or not values:
        return None, None

    filtered = [
        (float(t), float(v) / max(area, 0.001))
        for t, v in zip(times, values)
        if float(t) >= float(min_start_s)
    ]
    if not filtered:
        return None, None

    if len(filtered) >= 2:
        deltas = [filtered[idx + 1][0] - filtered[idx][0] for idx in range(len(filtered) - 1)]
        positive_deltas = [delta for delta in deltas if delta > 0]
        step = min(positive_deltas) if positive_deltas else 1.0
    else:
        step = 1.0

    runs = []
    run_start = None
    run_end = None
    prev_time = None

    for time_value, density in filtered:
        if density > density_threshold:
            if run_start is None:
                run_start = time_value
                run_end = time_value
            elif prev_time is not None and time_value - prev_time <= step * 1.5:
                run_end = time_value
            else:
                duration = (run_end - run_start) + step
                if duration >= min_sustain_s:
                    runs.append((run_start, run_end))
                run_start = time_value
                run_end = time_value
        else:
            if run_start is not None:
                duration = (run_end - run_start) + step
                if duration >= min_sustain_s:
                    runs.append((run_start, run_end))
                run_start = None
                run_end = None
        prev_time = time_value

    if run_start is not None:
        duration = (run_end - run_start) + step
        if duration >= min_sustain_s:
            runs.append((run_start, run_end))

    if not runs:
        return None, None
    return runs[0][0], runs[-1][1]


def spatial_bottleneck_rows(graph, method_label, metrics, top_k=10, density_threshold=3.0):
    rows = []
    node_stats = metrics.get("node_stats", {})
    node_series = metrics.get("node_series", {})

    for node, stat in node_stats.items():
        node_class = dimension2_node_class(node)
        if not node_class:
            continue

        queue_seconds = float(stat.get("queue_seconds", 0.0))
        peak_people = float(stat.get("peak_people", 0.0))
        peak_density = float(stat.get("peak_density", 0.0))
        area = max(float(graph.nodes[node].get("area", 1.0)), 0.001) if node in graph.nodes else 1.0

        series = node_series.get(node, {})
        times = series.get("times", []) or []
        queues = series.get("queue", []) or []
        first_over, last_over = sustained_over_threshold_window(
            times,
            queues,
            area,
            density_threshold,
        )

        rows.append(
            {
                "method_label": method_label,
                "node": node,
                "node_class": node_class,
                "pathfinder_usable": "yes" if dimension2_node_usable_in_pathfinder(node) else "no",
                "queue_seconds": queue_seconds,
                "peak_people": peak_people,
                "peak_density": peak_density,
                "first_over3_time_s": first_over,
                "last_over3_time_s": last_over,
            }
        )

    rows.sort(key=lambda row: (row["queue_seconds"], row["peak_density"]), reverse=True)
    trimmed = rows[:top_k]
    for idx, row in enumerate(trimmed, start=1):
        row["rank"] = idx
    return trimmed


def summarize_method(graph, pop_dict, label, method):
    metrics = network.run_simulation_for_metrics_timed(graph, pop_dict, method=method)
    exit_metrics = exit_balance_metrics(metrics)
    top_bottlenecks = bottleneck_summary(metrics, top_k=3)
    return {
        "method_label": label,
        "method": method,
        "evacuation_time_s": float(metrics["time"]),
        "avg_travel_time_s": float(metrics.get("avg_travel_time", 0.0)),
        "queueing_time_person_s": float(metrics["queueing_time"]),
        "congestion_exposure_time_person_s": float(metrics["congestion_exposure_time"]),
        "moderate_congestion_exposure_time_person_s": float(metrics.get("moderate_congestion_exposure_time", metrics["congestion_exposure_time"])),
        "severe_congestion_exposure_time_person_s": float(metrics.get("severe_congestion_exposure_time", 0.0)),
        "peak_density_p_per_m2": float(metrics.get("peak_density", 0.0)),
        "avg_speed_m_per_s": float(metrics.get("avg_speed", 0.0)),
        "wall_clock_runtime_s": float(metrics.get("wall_clock_runtime_s", 0.0)),
        "exit_hhi": float(exit_metrics["exit_hhi"]),
        "max_exit_share": float(exit_metrics["max_exit_share"]),
        "active_exit_count": int(exit_metrics["active_exit_count"]),
        "top_bottleneck_1": top_bottlenecks[0]["node"] if len(top_bottlenecks) >= 1 else "",
        "top_bottleneck_1_queue": top_bottlenecks[0]["queue_seconds"] if len(top_bottlenecks) >= 1 else 0.0,
        "top_bottleneck_2": top_bottlenecks[1]["node"] if len(top_bottlenecks) >= 2 else "",
        "top_bottleneck_2_queue": top_bottlenecks[1]["queue_seconds"] if len(top_bottlenecks) >= 2 else 0.0,
        "top_bottleneck_3": top_bottlenecks[2]["node"] if len(top_bottlenecks) >= 3 else "",
        "top_bottleneck_3_queue": top_bottlenecks[2]["queue_seconds"] if len(top_bottlenecks) >= 3 else 0.0,
        "clearance_times_by_line": metrics.get("clearance_times_by_line", {}),
        "exit_usage": metrics.get("exit_usage", {}),
        "metrics": metrics,
    }


def collect_pairwise_route_events(graph, pop_dict, source_nodes, baseline_label, baseline_method, guided_label, guided_method, target_time=2400):
    baseline_state = copy.deepcopy(graph)
    guided_state = copy.deepcopy(graph)
    network.init_people(baseline_state, pop_dict, apply_noise=False)
    network.init_people(guided_state, pop_dict, apply_noise=False)
    shortest_dists = dict(network.nx.all_pairs_dijkstra_path_length(graph, weight="length"))

    previous_baseline = {source: None for source in source_nodes}
    previous_guided = {source: None for source in source_nodes}
    events = []
    current_time = 0.0

    while current_time <= target_time:
        baseline_hot = network.rank_instantaneous_bottlenecks(baseline_state, top_k=1)
        guided_hot = network.rank_instantaneous_bottlenecks(guided_state, top_k=1)

        for source in source_nodes:
            if source not in baseline_state.nodes or source not in guided_state.nodes:
                continue

            baseline_path = network.get_best_path_to_exit(baseline_state, source, baseline_method, shortest_dists)
            guided_path = network.get_best_path_to_exit(guided_state, source, guided_method, shortest_dists)
            baseline_next = baseline_path[1] if baseline_path and len(baseline_path) > 1 else None
            guided_next = guided_path[1] if guided_path and len(guided_path) > 1 else None
            baseline_changed = baseline_next != previous_baseline[source]
            guided_changed = guided_next != previous_guided[source]
            route_diverged = baseline_next != guided_next

            if current_time == 0:
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
                    previous_baseline[source] = baseline_next
                    previous_guided[source] = guided_next
                    continue
                event_type = "+".join(flags)

            baseline_next_people = baseline_state.nodes[baseline_next].get("people", 0.0) if baseline_next in baseline_state.nodes else 0.0
            guided_next_people = guided_state.nodes[guided_next].get("people", 0.0) if guided_next in guided_state.nodes else 0.0
            baseline_next_density = (
                baseline_next_people / max(float(baseline_state.nodes[baseline_next].get("area", 1.0)), 0.001)
                if baseline_next in baseline_state.nodes else 0.0
            )
            guided_next_density = (
                guided_next_people / max(float(guided_state.nodes[guided_next].get("area", 1.0)), 0.001)
                if guided_next in guided_state.nodes else 0.0
            )

            events.append(
                {
                    "time": current_time,
                    "pair_label": f"{guided_label} vs {baseline_label}",
                    "baseline_label": baseline_label,
                    "guided_label": guided_label,
                    "source": source,
                    "line": source.split("_")[1] if "_" in source else source,
                    "event_type": event_type,
                    "baseline_changed": baseline_changed,
                    "guided_changed": guided_changed,
                    "route_diverged": route_diverged,
                    "baseline_next": baseline_next or "",
                    "guided_next": guided_next or "",
                    "baseline_next_density": baseline_next_density,
                    "guided_next_density": guided_next_density,
                    "baseline_bottleneck": baseline_hot[0]["node"] if baseline_hot else "",
                    "guided_bottleneck": guided_hot[0]["node"] if guided_hot else "",
                    "baseline_path_length": network._path_total_length(baseline_state, baseline_path) if baseline_path else 0.0,
                    "guided_path_length": network._path_total_length(guided_state, guided_path) if guided_path else 0.0,
                    "baseline_first_divergence": network.first_divergence(baseline_path, guided_path),
                }
            )

            previous_baseline[source] = baseline_next
            previous_guided[source] = guided_next

        network.advance_simulation_step(baseline_state, baseline_method, shortest_dists)
        network.advance_simulation_step(guided_state, guided_method, shortest_dists)
        if not any(baseline_state.nodes[node].get("people", 0.0) > 0.1 and baseline_state.nodes[node].get("type") != "exit" for node in baseline_state.nodes) and not any(
            guided_state.nodes[node].get("people", 0.0) > 0.1 and guided_state.nodes[node].get("type") != "exit" for node in guided_state.nodes
        ):
            break
        current_time += network.DELTA_T

    return events


def summarize_pairwise_events(events):
    summary_rows = []
    by_pair = defaultdict(list)
    for row in events:
        if row["event_type"] == "initial":
            continue
        by_pair[row["pair_label"]].append(row)

    for pair_label, pair_rows in sorted(by_pair.items()):
        summary_rows.append(
            {
                "pair_label": pair_label,
                "event_count": len(pair_rows),
                "baseline_change_count": sum(1 for row in pair_rows if row["baseline_changed"]),
                "guided_change_count": sum(1 for row in pair_rows if row["guided_changed"]),
                "divergence_count": sum(1 for row in pair_rows if row["route_diverged"]),
                "affected_source_count": len({row["source"] for row in pair_rows}),
                "first_change_time_s": min(row["time"] for row in pair_rows),
                "guided_lower_density_count": sum(
                    1 for row in pair_rows
                    if row["route_diverged"] and row["guided_next_density"] < row["baseline_next_density"]
                ),
                "guided_lower_density_share": (
                    sum(1 for row in pair_rows if row["route_diverged"] and row["guided_next_density"] < row["baseline_next_density"])
                    / max(sum(1 for row in pair_rows if row["route_diverged"]), 1)
                ),
            }
        )
    return summary_rows


def collect_mechanism_records(graph, pop_dict, source_nodes, baseline_label, baseline_method, guided_label, guided_method, target_time=2400):
    state = copy.deepcopy(graph)
    network.init_people(state, pop_dict, apply_noise=False)
    shortest_dists = dict(network.nx.all_pairs_dijkstra_path_length(graph, weight="length"))
    records = []
    current_time = 0.0

    while current_time <= target_time:
        for source in source_nodes:
            if source not in state.nodes or state.nodes[source].get("people", 0.0) <= 0.1:
                continue

            baseline_candidates = spr.enumerate_exit_paths(state, source, baseline_method, shortest_dists, network.fruin_speed)
            guided_candidates = spr.enumerate_exit_paths(state, source, guided_method, shortest_dists, network.fruin_speed)
            if not baseline_candidates or not guided_candidates:
                continue

            baseline_path = baseline_candidates[0]["path"]
            guided_path = guided_candidates[0]["path"]
            baseline_next = baseline_path[1] if len(baseline_path) > 1 else None
            guided_next = guided_path[1] if len(guided_path) > 1 else None
            if not baseline_next or not guided_next or baseline_next == guided_next:
                continue

            guided_breakdown = spr.our_path_cost_components(state, guided_path, network.fruin_speed, method=guided_method)
            baseline_breakdown = spr.our_path_cost_components(state, baseline_path, network.fruin_speed, method=guided_method)
            records.append(
                {
                    "time": current_time,
                    "source": source,
                    "line": source.split("_")[1] if "_" in source else source,
                    "baseline_label": baseline_label,
                    "guided_label": guided_label,
                    "baseline_next": baseline_next,
                    "guided_next": guided_next,
                    "baseline_path": network.format_path(baseline_path),
                    "guided_path": network.format_path(guided_path),
                    "baseline_base_cost": baseline_breakdown["base_cost"],
                    "baseline_gate_queue_penalty": baseline_breakdown["gate_queue_penalty"],
                    "baseline_service_penalty": baseline_breakdown["service_penalty"],
                    "baseline_source_release_penalty": baseline_breakdown["source_release_penalty"],
                    "baseline_downstream_release_penalty": baseline_breakdown["downstream_release_penalty"],
                    "baseline_exit_pressure_penalty": baseline_breakdown["exit_pressure_penalty"],
                    "baseline_total_cost": baseline_breakdown["total_cost"],
                    "guided_base_cost": guided_breakdown["base_cost"],
                    "guided_gate_queue_penalty": guided_breakdown["gate_queue_penalty"],
                    "guided_service_penalty": guided_breakdown["service_penalty"],
                    "guided_source_release_penalty": guided_breakdown["source_release_penalty"],
                    "guided_downstream_release_penalty": guided_breakdown["downstream_release_penalty"],
                    "guided_exit_pressure_penalty": guided_breakdown["exit_pressure_penalty"],
                    "guided_total_cost": guided_breakdown["total_cost"],
                }
            )

        network.advance_simulation_step(state, guided_method, shortest_dists)
        if not any(state.nodes[node].get("people", 0.0) > 0.1 and state.nodes[node].get("type") != "exit" for node in state.nodes):
            break
        current_time += network.DELTA_T

    return records


def average_component_rows(records):
    keys = [
        "base_cost",
        "gate_queue_penalty",
        "service_penalty",
        "source_release_penalty",
        "downstream_release_penalty",
        "exit_pressure_penalty",
        "total_cost",
    ]
    if not records:
        return {
            "BaselineStylePath": {key: 0.0 for key in keys},
            "OurChosenPath": {key: 0.0 for key in keys},
        }

    baseline_avg = {}
    guided_avg = {}
    for key in keys:
        baseline_avg[key] = statistics.mean(float(row[f"baseline_{key}"]) for row in records)
        guided_avg[key] = statistics.mean(float(row[f"guided_{key}"]) for row in records)
    return {
        "BaselineStylePath": baseline_avg,
        "OurChosenPath": guided_avg,
    }


def build_macro_chart_rows(method_rows):
    series_map = {}
    categories = [
        "Total evacuation time (s)",
        "Average travel time (s)",
        "Queueing (person-s)",
        "Moderate congestion >3 (person-s)",
        "Severe congestion >5 (person-s)",
        "Peak density (person/m^2)",
    ]
    for row in method_rows:
        series_map[row["method_label"]] = [
            row["evacuation_time_s"],
            row["avg_travel_time_s"],
            row["queueing_time_person_s"],
            row["moderate_congestion_exposure_time_person_s"],
            row["severe_congestion_exposure_time_person_s"],
            row["peak_density_p_per_m2"],
        ]
    return categories, series_map


def build_line_clearance_rows(method_rows):
    categories = ["L2", "L7", "L16", "L18"]
    series_map = {}
    for row in method_rows:
        line_times = row["clearance_times_by_line"]
        series_map[row["method_label"]] = [
            float(line_times.get(line)) if line_times.get(line) is not None else float(row["evacuation_time_s"])
            for line in categories
        ]
    return categories, series_map


def build_reroute_chart_rows(route_summary_rows):
    categories = ["Baseline changes", "Our changes", "Divergences", "Affected sources"]
    series_map = {}
    for row in route_summary_rows:
        series_map[row["pair_label"]] = [
            row["baseline_change_count"],
            row["guided_change_count"],
            row["divergence_count"],
            row["affected_source_count"],
        ]
    return categories, series_map


def build_ablation_chart_rows(ablation_rows):
    full_row = next(row for row in ablation_rows if row["method_label"] == "AdaptiveQueueAwareAStar")
    categories = [row["method_label"] for row in ablation_rows]
    series_map = {
        "Evacuation delta %": [],
        "Queueing delta %": [],
        "Moderate congestion delta %": [],
        "Severe congestion delta %": [],
        "Peak density delta %": [],
    }
    for row in ablation_rows:
        for series_name, field in [
            ("Evacuation delta %", "evacuation_time_s"),
            ("Queueing delta %", "queueing_time_person_s"),
            ("Moderate congestion delta %", "moderate_congestion_exposure_time_person_s"),
            ("Severe congestion delta %", "severe_congestion_exposure_time_person_s"),
            ("Peak density delta %", "peak_density_p_per_m2"),
        ]:
            base = float(full_row[field])
            current = float(row[field])
            if abs(base) <= 1e-9:
                delta = 0.0 if abs(current) <= 1e-9 else 100.0
            else:
                delta = (current - base) / base * 100.0
            series_map[series_name].append(delta)
    return categories, series_map


def build_exit_rows(method_rows):
    rows = []
    for row in method_rows:
        exit_usage = row["exit_usage"]
        total = sum(float(value) for value in exit_usage.values())
        for exit_name, value in sorted(exit_usage.items()):
            if total <= 0:
                share = 0.0
            else:
                share = float(value) / total
            rows.append(
                {
                    "method_label": row["method_label"],
                    "exit_name": exit_name,
                    "people": float(value),
                    "share": share,
                }
            )
    return rows


def report_text(method_rows, route_summary_rows, mechanism_records, ablation_rows):
    method_by_label = {row["method_label"]: row for row in method_rows}
    full = method_by_label["AdaptiveQueueAwareAStar"]
    paper = method_by_label["PaperImprovedAStar"]
    best_time = min(method_rows, key=lambda row: row["evacuation_time_s"])
    best_queue = min(method_rows, key=lambda row: row["queueing_time_person_s"])
    best_moderate_congestion = min(method_rows, key=lambda row: row["moderate_congestion_exposure_time_person_s"])
    best_severe_congestion = min(method_rows, key=lambda row: row["severe_congestion_exposure_time_person_s"])
    best_peak_density = min(method_rows, key=lambda row: row["peak_density_p_per_m2"])

    report_lines = [
        "# Scenario 1 + Pathfinder Validation",
        "",
        "- Scope: system-level Scenario 1 (`常规突发`) with Pathfinder-derived waiting-zone geometry and distance data.",
        "- Compared methods: `PaperImprovedAStar`, `AdaptiveQueueAwareAStar`.",
        "- Ablation: `NoWaitingTime` removes the explicit bottleneck waiting-time term.",
        "",
        "## What To Show In The Paper",
        "",
        f"- Macro comparison: [207_scenario1_pathfinder_macro_metrics.svg]({OUTPUT_MACRO_CHART.as_posix()})",
        f"- Line clearance comparison: [208_scenario1_pathfinder_line_clearance.svg]({OUTPUT_CLEARANCE_CHART.as_posix()})",
        f"- Reroute responsiveness: [209_scenario1_pathfinder_reroute_summary.svg]({OUTPUT_REROUTE_CHART.as_posix()})",
        f"- Ablation sensitivity: [210_scenario1_pathfinder_ablation.svg]({OUTPUT_ABLATION_CHART.as_posix()})",
        f"- Mechanism attribution vs literature method: [211_scenario1_pathfinder_mechanism.svg]({OUTPUT_MECHANISM_CHART.as_posix()})",
        "",
        "## High-Level Findings",
        "",
        f"- Fastest total evacuation among the two main methods: `{best_time['method_label']}` = `{best_time['evacuation_time_s']:.2f}s`.",
        f"- Lowest queueing burden: `{best_queue['method_label']}` = `{best_queue['queueing_time_person_s']:.2f}` person-s.",
        f"- Lowest moderate congestion exposure (`density > 3`): `{best_moderate_congestion['method_label']}` = `{best_moderate_congestion['moderate_congestion_exposure_time_person_s']:.2f}` person-s.",
        f"- Lowest severe congestion exposure (`density > 5`): `{best_severe_congestion['method_label']}` = `{best_severe_congestion['severe_congestion_exposure_time_person_s']:.2f}` person-s.",
        f"- Lowest peak density: `{best_peak_density['method_label']}` = `{best_peak_density['peak_density_p_per_m2']:.2f}` person/m^2.",
        f"- `AdaptiveQueueAwareAStar` vs `PaperImprovedAStar`: evacuation `{full['evacuation_time_s'] - paper['evacuation_time_s']:+.2f}s`, queueing `{full['queueing_time_person_s'] - paper['queueing_time_person_s']:+.2f}` person-s, moderate congestion `{full['moderate_congestion_exposure_time_person_s'] - paper['moderate_congestion_exposure_time_person_s']:+.2f}` person-s, severe congestion `{full['severe_congestion_exposure_time_person_s'] - paper['severe_congestion_exposure_time_person_s']:+.2f}` person-s.",
        "- `congestion_exposure_time_person_s` is now interpreted as the moderate (`density > 3`) exposure metric for backward compatibility.",
        "- Exit allocation is reported directly from the restored source-group and exit-flow bookkeeping.",
        "",
        "## Why The Added Terms Matter",
        "",
    ]

    ablation_by_label = {row["method_label"]: row for row in ablation_rows}
    for label in ["NoWaitingTime"]:
        row = ablation_by_label[label]
        report_lines.append(
            f"- `{label}` relative to `AdaptiveQueueAwareAStar`: evacuation `{row['evacuation_time_s'] - full['evacuation_time_s']:+.2f}s`, "
            f"queueing `{row['queueing_time_person_s'] - full['queueing_time_person_s']:+.2f}` person-s, "
            f"moderate congestion `{row['moderate_congestion_exposure_time_person_s'] - full['moderate_congestion_exposure_time_person_s']:+.2f}` person-s, "
            f"severe congestion `{row['severe_congestion_exposure_time_person_s'] - full['severe_congestion_exposure_time_person_s']:+.2f}` person-s."
        )

    report_lines.extend(
        [
            "",
            "## How To Explain Rerouting",
            "",
        ]
    )
    for row in route_summary_rows:
        report_lines.append(
            f"- `{row['pair_label']}`: divergence `{row['divergence_count']}`, baseline changes `{row['baseline_change_count']}`, "
            f"our changes `{row['guided_change_count']}`, affected sources `{row['affected_source_count']}`, "
            f"guided lower-density share `{row['guided_lower_density_share']:.1%}`."
        )

    report_lines.extend(
        [
            "",
            "## Mechanism Interpretation",
            "",
            f"- Divergence samples used for `PaperImprovedAStar` vs `AdaptiveQueueAwareAStar`: `{len(mechanism_records)}`.",
            "- In the mechanism chart, compare `BaselineStylePath` and `OurChosenPath` under the same crowd state.",
            "- The mechanism chart separates realized travel time from the explicit bottleneck waiting-time term used by the adaptive method.",
            "",
            "## Data Files",
            "",
            f"- [201_scenario1_pathfinder_method_summary.csv]({OUTPUT_METHOD_SUMMARY.as_posix()})",
            f"- [202_scenario1_pathfinder_line_clearance.csv]({OUTPUT_LINE_CLEARANCE.as_posix()})",
            f"- [203_scenario1_pathfinder_exit_summary.csv]({OUTPUT_EXIT_SUMMARY.as_posix()})",
            f"- [203b_scenario1_pathfinder_exit_by_source_group.csv]({OUTPUT_EXIT_SOURCE_GROUP_SUMMARY.as_posix()})",
            f"- [203c_scenario1_pathfinder_spatial_bottlenecks.csv]({OUTPUT_SPATIAL_BOTTLENECK_SUMMARY.as_posix()})",
            f"- [204_scenario1_pathfinder_reroute_summary.csv]({OUTPUT_ROUTE_SUMMARY.as_posix()})",
            f"- [205_scenario1_pathfinder_ablation_summary.csv]({OUTPUT_ABLATION_SUMMARY.as_posix()})",
            f"- [206_scenario1_pathfinder_mechanism_detail.csv]({OUTPUT_MECHANISM_DETAIL.as_posix()})",
        ]
    )
    return "\n".join(report_lines) + "\n"


def main():
    graph = network.build_graph()
    pop_dict = build_scenario1_pop_dict()
    source_nodes = tracked_source_nodes(graph, pop_dict)
    print(f"Tracked routing sources: {len(source_nodes)}")

    method_rows = []
    for label, method in SCENARIO1_METHODS:
        print(f"Running main comparison: {label}")
        method_rows.append(summarize_method(graph, pop_dict, label, method))

    ablation_rows = []
    for label, method in ABLATION_METHODS:
        print(f"Running ablation: {label}")
        ablation_rows.append(summarize_method(graph, pop_dict, label, method))

    method_summary_rows = []
    line_rows = []
    for row in method_rows:
        method_summary_rows.append(
            {
                key: value
                for key, value in row.items()
                if key not in {"metrics", "clearance_times_by_line", "exit_usage"}
            }
        )
        for line_id, value in row["clearance_times_by_line"].items():
            line_rows.append(
                {
                    "method_label": row["method_label"],
                    "line": line_id,
                    "clearance_time_s": None if value is None else float(value),
                }
            )

    ablation_summary_rows = [
        {
            key: value
            for key, value in row.items()
            if key not in {"metrics", "clearance_times_by_line", "exit_usage"}
        }
        for row in ablation_rows
    ]

    exit_rows = build_exit_rows(method_rows)
    exit_source_group_rows = []
    spatial_bottleneck_summary_rows = []
    for row in method_rows:
        exit_source_group_rows.extend(network.build_exit_source_group_rows(row["metrics"], row["method_label"]))
        spatial_bottleneck_summary_rows.extend(
            spatial_bottleneck_rows(graph, row["method_label"], row["metrics"], top_k=10)
        )

    event_horizon = int(max(row["evacuation_time_s"] for row in method_rows + ablation_rows) + 30)
    print(f"Route-analysis horizon: {event_horizon}s")
    route_events = []
    route_events.extend(
        collect_pairwise_route_events(
            graph,
            pop_dict,
            source_nodes,
            baseline_label="PaperImprovedAStar",
            baseline_method=spr.PAPER_SINGLE_PATH_METHOD,
            guided_label="AdaptiveQueueAwareAStar",
            guided_method=spr.OUR_SINGLE_PATH_METHOD,
            target_time=event_horizon,
        )
    )
    route_summary_rows = summarize_pairwise_events(route_events)
    print("Finished pairwise reroute analysis")

    mechanism_records = collect_mechanism_records(
        graph,
        pop_dict,
        source_nodes,
        baseline_label="PaperImprovedAStar",
        baseline_method=spr.PAPER_SINGLE_PATH_METHOD,
        guided_label="AdaptiveQueueAwareAStar",
        guided_method=spr.OUR_SINGLE_PATH_METHOD,
        target_time=event_horizon,
    )
    print("Finished mechanism attribution analysis")

    write_csv(
        OUTPUT_METHOD_SUMMARY,
        method_summary_rows,
        [
            "method_label",
            "method",
            "evacuation_time_s",
            "avg_travel_time_s",
            "queueing_time_person_s",
            "congestion_exposure_time_person_s",
            "moderate_congestion_exposure_time_person_s",
            "severe_congestion_exposure_time_person_s",
            "peak_density_p_per_m2",
            "avg_speed_m_per_s",
            "wall_clock_runtime_s",
            "exit_hhi",
            "max_exit_share",
            "active_exit_count",
            "top_bottleneck_1",
            "top_bottleneck_1_queue",
            "top_bottleneck_2",
            "top_bottleneck_2_queue",
            "top_bottleneck_3",
            "top_bottleneck_3_queue",
        ],
    )
    write_csv(OUTPUT_LINE_CLEARANCE, line_rows, ["method_label", "line", "clearance_time_s"])
    write_csv(OUTPUT_EXIT_SUMMARY, exit_rows, ["method_label", "exit_name", "people", "share"])
    write_csv(
        OUTPUT_EXIT_SOURCE_GROUP_SUMMARY,
        exit_source_group_rows,
        [
            "method_label",
            "source_group",
            "line",
            "source_type",
            "source_zone",
            "configured_people",
            "evacuated_people",
            "exit_name",
            "people",
            "share_within_group",
        ],
    )
    write_csv(
        OUTPUT_SPATIAL_BOTTLENECK_SUMMARY,
        spatial_bottleneck_summary_rows,
        [
            "method_label",
            "rank",
            "node",
            "node_class",
            "pathfinder_usable",
            "queue_seconds",
            "peak_people",
            "peak_density",
            "first_over3_time_s",
            "last_over3_time_s",
        ],
    )
    write_csv(
        OUTPUT_ROUTE_SUMMARY,
        route_summary_rows,
        [
            "pair_label",
            "event_count",
            "baseline_change_count",
            "guided_change_count",
            "divergence_count",
            "affected_source_count",
            "first_change_time_s",
            "guided_lower_density_count",
            "guided_lower_density_share",
        ],
    )
    write_csv(
        OUTPUT_ABLATION_SUMMARY,
        ablation_summary_rows,
        [
            "method_label",
            "method",
            "evacuation_time_s",
            "avg_travel_time_s",
            "queueing_time_person_s",
            "congestion_exposure_time_person_s",
            "moderate_congestion_exposure_time_person_s",
            "severe_congestion_exposure_time_person_s",
            "peak_density_p_per_m2",
            "avg_speed_m_per_s",
            "wall_clock_runtime_s",
            "exit_hhi",
            "max_exit_share",
            "active_exit_count",
            "top_bottleneck_1",
            "top_bottleneck_1_queue",
            "top_bottleneck_2",
            "top_bottleneck_2_queue",
            "top_bottleneck_3",
            "top_bottleneck_3_queue",
        ],
    )
    write_csv(
        OUTPUT_MECHANISM_DETAIL,
        mechanism_records,
        [
            "time",
            "source",
            "line",
            "baseline_label",
            "guided_label",
            "baseline_next",
            "guided_next",
            "baseline_path",
            "guided_path",
            "baseline_base_cost",
            "baseline_gate_queue_penalty",
            "baseline_service_penalty",
            "baseline_source_release_penalty",
            "baseline_downstream_release_penalty",
            "baseline_exit_pressure_penalty",
            "baseline_total_cost",
            "guided_base_cost",
            "guided_gate_queue_penalty",
            "guided_service_penalty",
            "guided_source_release_penalty",
            "guided_downstream_release_penalty",
            "guided_exit_pressure_penalty",
            "guided_total_cost",
        ],
    )

    macro_categories, macro_series = build_macro_chart_rows(method_rows)
    write_grouped_bar_chart_svg(OUTPUT_MACRO_CHART, "Scenario 1 + Pathfinder: Macro Metrics", macro_categories, macro_series, METHOD_COLORS, "Value")

    line_categories, line_series = build_line_clearance_rows(method_rows)
    write_grouped_bar_chart_svg(OUTPUT_CLEARANCE_CHART, "Scenario 1 + Pathfinder: Line Clearance Times", line_categories, line_series, METHOD_COLORS, "Clearance time (s)")

    reroute_categories, reroute_series = build_reroute_chart_rows(route_summary_rows)
    reroute_colors = {
        "AdaptiveQueueAwareAStar vs PaperImprovedAStar": "#4E79A7",
    }
    write_grouped_bar_chart_svg(OUTPUT_REROUTE_CHART, "Scenario 1 + Pathfinder: Reroute Summary", reroute_categories, reroute_series, reroute_colors, "Count")

    ablation_categories, ablation_series = build_ablation_chart_rows(ablation_rows)
    ablation_colors = {
        "Evacuation delta %": "#E15759",
        "Queueing delta %": "#4E79A7",
        "Congestion delta %": "#59A14F",
        "Exit HHI delta %": "#B07AA1",
    }
    write_grouped_bar_chart_svg(OUTPUT_ABLATION_CHART, "Ablation Sensitivity Relative To AdaptiveQueueAwareAStar", ablation_categories, ablation_series, ablation_colors, "Delta (%)")

    mechanism_values = average_component_rows(mechanism_records)
    mechanism_colors = {
        "base_cost": "#BDBDBD",
        "gate_queue_penalty": "#8CD17D",
        "service_penalty": "#76B7B2",
        "source_release_penalty": "#F28E2B",
        "downstream_release_penalty": "#E15759",
        "exit_pressure_penalty": "#4E79A7",
    }
    write_stacked_bar_chart_svg(
        OUTPUT_MECHANISM_CHART,
        "Why Our Method Diverges From PaperImprovedAStar",
        ["BaselineStylePath", "OurChosenPath"],
        [
            "base_cost",
            "gate_queue_penalty",
            "service_penalty",
            "source_release_penalty",
            "downstream_release_penalty",
            "exit_pressure_penalty",
        ],
        mechanism_values,
        mechanism_colors,
        "Average path cost contribution",
    )

    OUTPUT_REPORT.write_text(report_text(method_rows, route_summary_rows, mechanism_records, ablation_rows), encoding="utf-8")

    print(f"Wrote {OUTPUT_METHOD_SUMMARY.name}")
    print(f"Wrote {OUTPUT_LINE_CLEARANCE.name}")
    print(f"Wrote {OUTPUT_EXIT_SUMMARY.name}")
    print(f"Wrote {OUTPUT_EXIT_SOURCE_GROUP_SUMMARY.name}")
    print(f"Wrote {OUTPUT_SPATIAL_BOTTLENECK_SUMMARY.name}")
    print(f"Wrote {OUTPUT_ABLATION_SUMMARY.name}")
    print(f"Wrote {OUTPUT_MACRO_CHART.name}")
    print(f"Wrote {OUTPUT_CLEARANCE_CHART.name}")
    print(f"Wrote {OUTPUT_ABLATION_CHART.name}")
    print(f"Wrote {OUTPUT_ROUTE_SUMMARY.name}")
    print(f"Wrote {OUTPUT_MECHANISM_DETAIL.name}")
    print(f"Wrote {OUTPUT_REROUTE_CHART.name}")
    print(f"Wrote {OUTPUT_MECHANISM_CHART.name}")
    print(f"Wrote {OUTPUT_REPORT.name}")


if __name__ == "__main__":
    main()
