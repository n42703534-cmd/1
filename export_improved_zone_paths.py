from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

import algorithm_comparison as comparison
import network


DEFAULT_LINES = ("L2", "L7", "L16", "L18", "Maglev")
ZONED_TRAIN_LINES = ("L2", "L7")
TRAIN_GROUP_RE = re.compile(r"^(L\d+)_train(\d+)_([^:]+)$")
WHOLE_TRAIN_GROUP_RE = re.compile(r"^(L\d+)_train(\d+)$")


def _car_index(node_name: str) -> int:
    match = re.search(r"_Car(\d+)$", node_name)
    return int(match.group(1)) if match else 0


def _zone_for_car(line_id: str, train_idx: int, car_idx: int) -> str:
    for zone in network._platform_waiting_zone_defs(line_id):
        car_indices = zone.get("car_indices")
        if car_indices is None:
            car_indices = [zone.get("car_index", -1)]
        if car_idx not in {int(value) for value in car_indices}:
            continue
        train_indices = zone.get("train_indices")
        if train_indices is None:
            train_indices = [zone.get("train_index", 1)]
        if train_idx in {int(value) for value in train_indices}:
            return str(zone.get("zone_key") or zone.get("name"))
    raise ValueError(
        f"No platform/hall service zone for {line_id} train {train_idx} car {car_idx}"
    )


def split_train_sources_by_zone(graph, line_ids: tuple[str, ...]) -> dict[str, dict[str, float]]:
    origins: dict[str, dict[str, float]] = defaultdict(dict)
    for line_id in ZONED_TRAIN_LINES:
        if line_id not in line_ids:
            continue
        train_count = int(network.TRAIN_PHYSICS[line_id].get("trains", 2))
        for train_idx in range(1, train_count + 1):
            for car_node in network._sorted_train_car_nodes(graph, line_id, train_idx):
                people = float(graph.nodes[car_node].get("people", 0.0))
                if people <= 0:
                    continue
                car_idx = _car_index(car_node)
                zone_key = _zone_for_car(line_id, train_idx, car_idx)
                source_group = f"{line_id}_train{train_idx}_{zone_key}"
                graph.nodes[car_node]["source_group_dict"] = {source_group: people}
                origins[source_group][car_node] = people

    for node, data in graph.nodes(data=True):
        for source_group, people in data.get("source_group_dict", {}).items():
            if source_group.split("_", 1)[0] not in line_ids or people <= 0:
                continue
            origins[source_group].setdefault(node, float(people))
    return dict(origins)


def _find_positive_path(residual, source: str, exits: set[str], epsilon: float = 1e-9):
    adjacency: dict[str, list[str]] = defaultdict(list)
    for (u, v), flow in residual.items():
        if flow > epsilon:
            adjacency[u].append(v)
    for node in adjacency:
        adjacency[node].sort()

    queue = deque([source])
    previous = {source: None}
    destination = None
    while queue:
        node = queue.popleft()
        if node in exits:
            destination = node
            break
        for successor in adjacency.get(node, []):
            if successor in previous:
                continue
            previous[successor] = node
            queue.append(successor)
    if destination is None:
        return None

    path = []
    cursor = destination
    while cursor is not None:
        path.append(cursor)
        cursor = previous[cursor]
    return list(reversed(path))


def decompose_source_group(graph, edge_flows, origins, source_group: str):
    residual = {
        edge: float(group_flows.get(source_group, 0.0))
        for edge, group_flows in edge_flows.items()
        if float(group_flows.get(source_group, 0.0)) > 1e-9
    }
    root = "__SOURCE__"
    for origin, people in origins.items():
        residual[(root, origin)] = float(people)

    exits = {
        node for node, data in graph.nodes(data=True)
        if data.get("type") == "exit"
    }
    decomposed = defaultdict(float)
    max_iterations = max(len(residual) * 4, 100)
    for _ in range(max_iterations):
        path = _find_positive_path(residual, root, exits)
        if not path:
            break
        edges = list(zip(path[:-1], path[1:]))
        flow = min(residual[edge] for edge in edges)
        if flow <= 1e-9:
            break
        raw_path = tuple(path[1:])
        decomposed[raw_path] += flow
        for edge in edges:
            residual[edge] = max(residual[edge] - flow, 0.0)

    target = sum(float(value) for value in origins.values())
    decomposed_total = sum(decomposed.values())
    leftover_at_source = sum(
        flow for (u, _), flow in residual.items() if u == root and flow > 1e-9
    )
    return dict(decomposed), target, decomposed_total, leftover_at_source


def _source_metadata(source_group: str):
    train_match = TRAIN_GROUP_RE.match(source_group)
    if train_match:
        line_id, train_idx, zone_key = train_match.groups()
        return {
            "line": line_id,
            "source_type": "train",
            "train": f"train{train_idx}",
            "zone": zone_key,
            "display": f"{line_id} {train_idx}号列车 {zone_key}区",
        }
    whole_train_match = WHOLE_TRAIN_GROUP_RE.match(source_group)
    if whole_train_match:
        line_id, train_idx = whole_train_match.groups()
        return {
            "line": line_id,
            "source_type": "train",
            "train": f"train{train_idx}",
            "zone": "whole_train",
            "display": f"{line_id} {train_idx}号列车（整列）",
        }
    line_id, source_type, zone = network._parse_source_group_id(source_group)
    return {
        "line": line_id,
        "source_type": source_type,
        "train": "",
        "zone": zone,
        "display": source_group,
    }


def _display_path(graph, source_group: str, raw_path: tuple[str, ...]) -> tuple[str, ...]:
    meta = _source_metadata(source_group)
    if meta["source_type"] != "train":
        return (meta["display"],) + raw_path
    first_zone_index = next(
        (
            index for index, node in enumerate(raw_path)
            if graph.nodes.get(node, {}).get("type") == "platform_waiting_zone"
        ),
        None,
    )
    tail = raw_path[first_zone_index:] if first_zone_index is not None else raw_path
    return (meta["display"],) + tuple(tail)


def _percentages_summing_to_100(values, decimals: int):
    """Round shares with a largest-remainder correction to total exactly 100%."""
    total = sum(float(value) for value in values)
    if total <= 0:
        return [0.0 for _ in values]
    scale = 10 ** int(decimals)
    target_units = 100 * scale
    exact_units = [float(value) / total * target_units for value in values]
    rounded_units = [int(math.floor(value + 1e-12)) for value in exact_units]
    remaining = target_units - sum(rounded_units)
    order = sorted(
        range(len(values)),
        key=lambda index: (
            exact_units[index] - rounded_units[index],
            float(values[index]),
            -index,
        ),
        reverse=True,
    )
    for index in order[:remaining]:
        rounded_units[index] += 1
    return [value / scale for value in rounded_units]


def write_outputs(output_dir: Path, graph, metrics, origins, line_ids: tuple[str, ...]):
    output_dir.mkdir(parents=True, exist_ok=True)
    edge_flows = metrics.get("edge_flow_by_source_group", {})
    detail_rows = []
    coverage_rows = []
    display_totals: dict[tuple[str, tuple[str, ...]], float] = defaultdict(float)

    selected_groups = sorted(
        source_group for source_group in origins
        if source_group.split("_", 1)[0] in line_ids
    )
    for source_group in selected_groups:
        paths, target, decomposed_total, leftover = decompose_source_group(
            graph, edge_flows, origins[source_group], source_group
        )
        meta = _source_metadata(source_group)
        coverage_rows.append({
            "source_group": source_group,
            **meta,
            "configured_people": target,
            "decomposed_people": decomposed_total,
            "unresolved_people": leftover,
            "coverage_pct": 100.0 * decomposed_total / target if target > 0 else 0.0,
        })
        sorted_paths = sorted(paths.items(), key=lambda item: (-item[1], item[0]))
        raw_percentages = _percentages_summing_to_100(
            [people for _, people in sorted_paths],
            decimals=3,
        )
        for (raw_path, people), raw_percentage in zip(sorted_paths, raw_percentages):
            display_path = _display_path(graph, source_group, raw_path)
            display_totals[(source_group, display_path)] += people
            detail_rows.append({
                "line": meta["line"],
                "source_group": source_group,
                "source_type": meta["source_type"],
                "train": meta["train"],
                "zone": meta["zone"],
                "people": people,
                "share_within_source_pct": raw_percentage,
                "raw_complete_path": " -> ".join(raw_path),
                "display_complete_path": " -> ".join(display_path),
            })

    detail_path = output_dir / "improved_complete_paths_all_lines.csv"
    with detail_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "line", "source_group", "source_type", "train", "zone", "people",
            "share_within_source_pct", "raw_complete_path", "display_complete_path",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in detail_rows:
            output = dict(row)
            output["people"] = round(float(output["people"]), 3)
            output["share_within_source_pct"] = round(float(output["share_within_source_pct"]), 3)
            writer.writerow(output)

    coverage_path = output_dir / "source_group_coverage_all_lines.csv"
    with coverage_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "source_group", "line", "source_type", "train", "zone", "display",
            "configured_people", "decomposed_people", "unresolved_people", "coverage_pct",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in coverage_rows:
            output = dict(row)
            for field in ("configured_people", "decomposed_people", "unresolved_people", "coverage_pct"):
                output[field] = round(float(output[field]), 3)
            writer.writerow(output)

    clearance_path = output_dir / "line_clearance_improved.csv"
    with clearance_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["line", "clearance_time_s"])
        writer.writeheader()
        for line_id, clearance_time in metrics.get("clearance_times_by_line", {}).items():
            writer.writerow({"line": line_id, "clearance_time_s": clearance_time})

    report_path = output_dir / "improved_complete_paths_all_lines.md"
    lines = [
        "# ImprovedAStar：2号线与7号线完整路径",
        "",
        f"- mode4 疏散完成时间：{metrics['time']:.1f}s",
        f"- 总疏散人数：{sum(metrics.get('exit_usage', {}).values()):.0f}人",
        "- 2号线列车分区：Z1–Z4，每区对应相邻2节车厢。",
        "- 7号线列车分区：C1–C6，每区对应相邻车厢区域。",
        "- 路径由仿真实际的“来源组—边流量”分解得到，不使用楼梯/闸机/出口边际量的贪心拼接。",
        "",
    ]
    for line_id in line_ids:
        lines.extend([f"## {line_id}", ""])
        groups = [row for row in coverage_rows if row["line"] == line_id]
        groups.sort(key=lambda row: (row["source_type"] != "train", row["train"], row["zone"], row["source_group"]))
        for coverage in groups:
            source_group = coverage["source_group"]
            lines.extend([
                f"### {coverage['display']}（{coverage['configured_people']:.0f}人）",
                "",
            ])
            path_rows = [
                (path, people)
                for (group, path), people in display_totals.items()
                if group == source_group
            ]
            path_rows.sort(key=lambda item: (-item[1], item[0]))
            display_percentages = _percentages_summing_to_100(
                [people for _, people in path_rows],
                decimals=1,
            )
            for (path, people), share in zip(path_rows, display_percentages):
                lines.append(f"- {' -> '.join(path)}：{people:.0f}人（{share:.1f}%）")
            if coverage["unresolved_people"] > 1e-6:
                lines.append(f"- 未分解流量：{coverage['unresolved_people']:.1f}人")
            lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    readme_path = output_dir / "README.txt"
    readme_path.write_text(
        "ImprovedAStar zone-based complete route export\n"
        f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"Evacuation time: {metrics['time']:.1f}s\n"
        f"Lines: {', '.join(line_ids)}\n"
        "Train zoning: L2=Z1-Z4 (2 cars/zone); L7=C1-C6; other lines use existing source groups.\n",
        encoding="utf-8",
    )
    return detail_path, coverage_path, clearance_path, report_path, readme_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ImprovedAStar complete paths by source group.")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    comparison.MODE = 4
    population, total_people = comparison.build_population()
    graph = network.build_graph()
    graph.graph["density_dependent_flow"] = True
    network.init_people(graph, population, apply_noise=False)
    origins = split_train_sources_by_zone(graph, DEFAULT_LINES)
    source_group_totals = network._source_group_totals_from_graph(graph)
    targets = network._infer_target_by_line_from_graph_state(graph)
    metrics = network._run_simulation_for_metrics_core(
        graph,
        network.PAPER_SINGLE_PATH_METHOD,
        targets,
        stop_at_time=6000.0,
    )
    metrics["source_group_totals"] = source_group_totals
    evacuated = sum(float(value) for value in metrics.get("exit_usage", {}).values())
    if abs(evacuated - total_people) > 1e-6:
        raise RuntimeError(f"Evacuation mismatch: {evacuated} != {total_people}")

    output_dir = args.output_dir or (
        Path("outputs") / f"improved_zone_paths_all_lines_{datetime.now():%Y%m%d_%H%M%S}"
    )
    paths = write_outputs(output_dir, graph, metrics, origins, DEFAULT_LINES)
    print(f"ImprovedAStar T100={metrics['time']:.1f}s, evacuated={evacuated:.0f}/{total_people}")
    print("Line clearance times:", metrics.get("clearance_times_by_line", {}))
    for path in paths:
        print(path.resolve())


if __name__ == "__main__":
    main()
