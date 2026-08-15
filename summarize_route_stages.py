from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


DEFAULT_METHOD = "AdaptiveQueueAwareAStar"


def method_suffix(method: str) -> str:
    if method == "AdaptiveQueueAwareAStar":
        return "AA"
    if method == "ImprovedAStar":
        return "improved"
    return method.replace(" ", "_")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def stage_for(node: str, chain_type: str) -> str:
    if chain_type == "exit" or node.startswith("Exit_"):
        return "exit"
    if node.startswith("Gate_"):
        return "gate"
    if node.startswith("Stair_") or node.startswith("Escalator_"):
        return "vertical"
    if node.startswith("Transfer_"):
        return "transfer"
    if node.startswith("VN_"):
        return "virtual"
    if node.startswith("Train_") or node.startswith("Platform_"):
        return "origin_internal"
    return "other_facility"


def pct(value: float, denominator: float) -> float:
    return 100.0 * value / denominator if denominator > 0 else 0.0


def fmt_number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.2f}"


def fmt_distribution(rows: list[dict], source_total: float) -> str:
    if not rows:
        return "—"
    stage_total = sum(row["people"] for row in rows)
    parts = []
    for row in sorted(rows, key=lambda item: (-item["people"], item["node"])):
        parts.append(
            f"{row['node']}: {fmt_number(row['people'])}人 "
            f"({pct(row['people'], source_total):.1f}%来源; "
            f"{pct(row['people'], stage_total):.1f}%本层)"
        )
    return "; ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize source-to-vertical/gate/exit stage distributions."
    )
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--method", default=DEFAULT_METHOD)
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    route_rows = read_rows(input_dir / "route_chain.csv")
    exit_rows = read_rows(input_dir / "exit_by_source_group.csv")

    metadata: dict[tuple[str, str], dict] = {}
    exit_totals: dict[tuple[str, str, str], float] = defaultdict(float)
    for row in exit_rows:
        method = row["method_label"]
        source_group = row["source_group"]
        key = (method, source_group)
        metadata[key] = {
            "method": method,
            "source_group": source_group,
            "line": row["line"],
            "source_type": row["source_type"],
            "source_zone": row.get("source_zone", ""),
            "configured_people": float(row["configured_people"]),
            "evacuated_people": float(row["evacuated_people"]),
        }
        exit_totals[(method, source_group, row["exit_name"])] += float(row["people"])

    node_totals: dict[tuple[str, str, str, str], float] = defaultdict(float)
    for row in route_rows:
        method = row["method"]
        source_group = row["source_group"]
        node = row["node"]
        stage = stage_for(node, row["chain_type"])
        if stage == "exit":
            continue
        node_totals[(method, source_group, stage, node)] += float(row["people"])

    stage_rows: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for (method, source_group, stage, node), people in node_totals.items():
        stage_rows[(method, source_group)][stage].append(
            {"node": node, "people": people}
        )
    for (method, source_group, exit_name), people in exit_totals.items():
        stage_rows[(method, source_group)]["exit"].append(
            {"node": exit_name, "people": people}
        )

    selected_keys = sorted(
        [key for key in metadata if key[0] == args.method],
        key=lambda key: (
            metadata[key]["line"],
            metadata[key]["source_type"],
            key[1],
        ),
    )

    detail_rows = []
    catalog_rows = []
    for key in selected_keys:
        meta = metadata[key]
        total = meta["configured_people"]
        stages = stage_rows[key]
        for stage in [
            "origin_internal",
            "vertical",
            "transfer",
            "virtual",
            "other_facility",
            "gate",
            "exit",
        ]:
            rows = stages.get(stage, [])
            stage_total = sum(item["people"] for item in rows)
            for item in sorted(rows, key=lambda value: (-value["people"], value["node"])):
                detail_rows.append(
                    {
                        **meta,
                        "stage": stage,
                        "node": item["node"],
                        "people": item["people"],
                        "pct_of_source": pct(item["people"], total),
                        "pct_within_stage": pct(item["people"], stage_total),
                    }
                )

        verticals = stages.get("vertical", [])
        gates = stages.get("gate", [])
        exits = stages.get("exit", [])
        unique_stages = [rows for rows in (verticals, gates, exits) if rows]
        exact_joint = all(len(rows) <= 1 for rows in unique_stages)
        exact_nodes = []
        if exact_joint:
            exact_nodes = [key[1]]
            exact_nodes.extend(rows[0]["node"] for rows in unique_stages)

        catalog_rows.append(
            {
                **meta,
                "vertical_distribution": fmt_distribution(verticals, total),
                "gate_distribution": fmt_distribution(gates, total),
                "exit_distribution": fmt_distribution(exits, total),
                "joint_path_exact": "yes" if exact_joint else "no",
                "exact_path_if_unique": " -> ".join(exact_nodes),
            }
        )

    suffix = method_suffix(args.method)
    detail_path = input_dir / f"route_stage_percentages_{suffix}.csv"
    with detail_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "method",
            "line",
            "source_group",
            "source_type",
            "source_zone",
            "configured_people",
            "evacuated_people",
            "stage",
            "node",
            "people",
            "pct_of_source",
            "pct_within_stage",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in detail_rows:
            output = dict(row)
            output["people"] = round(output["people"], 4)
            output["pct_of_source"] = round(output["pct_of_source"], 1)
            output["pct_within_stage"] = round(output["pct_within_stage"], 1)
            writer.writerow(output)

    catalog_path = input_dir / f"route_source_catalog_{suffix}.csv"
    with catalog_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "method",
            "line",
            "source_group",
            "source_type",
            "source_zone",
            "configured_people",
            "evacuated_people",
            "vertical_distribution",
            "gate_distribution",
            "exit_distribution",
            "joint_path_exact",
            "exact_path_if_unique",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(catalog_rows)

    report_path = input_dir / f"route_source_summary_{suffix}.md"
    lines = [
        "# AdaptiveQueueAwareAStar 完整路径分层汇总",
        "",
        f"输入目录：`{input_dir.name}`；方法：`{args.method}`。",
        "",
        "百分比说明：`%来源`以该来源组人数为分母；`%本层`以该来源组在当前设施层的通过量为分母。",
        "",
        "> 当前仿真输出保存的是来源组在各节点的边际通过量，没有保存“楼梯→闸机”的按来源组联合边流。只有各层均唯一时，完整联合路径才可由现有文件严格确定；其余条目不会虚构联合比例。",
        "",
        "## L2闸机到出口的确定映射",
        "",
        "- `Gate_L2_N_West -> Exit_L2_2`",
        "- `Gate_L2_N_East -> Exit_L2_6`",
        "- `Gate_L2_S_West -> Exit_L2_4`",
        "- `Gate_L2_S_East -> Exit_L2_3`",
        "",
    ]

    current_line = None
    for row in catalog_rows:
        if row["line"] != current_line:
            current_line = row["line"]
            lines.extend([f"## {current_line}", ""])
        lines.extend(
            [
                f"### {row['source_group']}（{fmt_number(row['configured_people'])}人）",
                "",
                f"- 楼梯/扶梯：{row['vertical_distribution']}",
                f"- 闸机：{row['gate_distribution']}",
                f"- 出口：{row['exit_distribution']}",
            ]
        )
        if row["joint_path_exact"] == "yes" and row["exact_path_if_unique"]:
            lines.append(f"- 可严格确定的路径：`{row['exact_path_if_unique']}`")
        else:
            lines.append("- 联合路径：现有输出只能确定上述分层比例，不能唯一还原楼梯→闸机配对。")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(detail_path)
    print(catalog_path)
    print(report_path)


if __name__ == "__main__":
    main()
