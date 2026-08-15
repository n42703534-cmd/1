from __future__ import annotations

import copy
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

import network
from select_single_path_cases import LINES, METHODS, SCREEN_METHODS, belongs_to_line


ROOT = Path(__file__).resolve().parent


def apply_node_failure(G: nx.DiGraph, node: str) -> nx.DiGraph:
    H = copy.deepcopy(G)
    if node not in H:
        return H
    H.nodes[node]["capacity"] = 0.0
    H.nodes[node]["blocked"] = True
    for pred, _ in list(H.in_edges(node)):
        if H.has_edge(pred, node):
            H.remove_edge(pred, node)
    for _, succ in list(H.out_edges(node)):
        if H.has_edge(node, succ):
            H.remove_edge(node, succ)
    return H


def failure_facilities(G: nx.DiGraph, line: str, selected_long: pd.DataFrame) -> list[str]:
    useful_types = {"stair", "escalator", "gate_wide", "gate_tripod", "virtual"}
    path_nodes = []
    line_paths = selected_long[selected_long["line"] == line]["path"].dropna().astype(str)
    for path_text in line_paths:
        path_nodes.extend([part.strip() for part in path_text.split("->")])

    # 失效点优先选“正常代表路径实际经过”的设施，否则扫大量没人走的设施没有解释力。
    rows = []
    for node in dict.fromkeys(path_nodes):
        if node not in G:
            continue
        data = G.nodes[node]
        if data.get("type") not in useful_types:
            continue
        if G.in_degree(node) <= 0 or G.out_degree(node) <= 0:
            continue
        rows.append(node)

    if rows:
        return rows

    for node, data in G.nodes(data=True):
        if not belongs_to_line(node, line):
            continue
        if data.get("type") not in useful_types:
            continue
        if G.in_degree(node) <= 0 or G.out_degree(node) <= 0:
            continue
        rows.append(node)
    return rows


def exits_for_line(G: nx.DiGraph, line: str) -> list[str]:
    return [
        n
        for n, data in G.nodes(data=True)
        if data.get("type") == "exit" and belongs_to_line(n, line)
    ]


def all_cases_still_reachable(G: nx.DiGraph, line: str, cases: list[dict[str, str]]) -> bool:
    exits = exits_for_line(G, line)
    if not exits:
        return False
    for case in cases:
        origin = case["origin"]
        if origin not in G:
            return False
        if not any(nx.has_path(G, origin, exit_node) for exit_node in exits):
            return False
    return True


def run_cases(G_base: nx.DiGraph, cases: list[dict[str, str]], methods=SCREEN_METHODS) -> pd.DataFrame:
    rows = []
    for case in cases:
        case_state = network.build_single_path_case_state(G_base, case)
        shortest_dists = dict(nx.all_pairs_dijkstra_path_length(case_state, weight="length"))
        for method in methods:
            path = network.get_best_path_to_exit(case_state, case["origin"], method, shortest_dists)
            metrics = network.run_simulation_for_existing_state(
                case_state,
                method=method,
                target_by_line={case["line"]: network.SINGLE_PATH_CASE_POPULATION},
            )
            rows.append(
                {
                    "case_id": case["case_id"],
                    "line": case["line"],
                    "origin": case["origin"],
                    "start_role": case["start_role"],
                    "method": network._normalize_method(method),
                    "target_exit": path[-1] if path else None,
                    "path": network.format_path(path),
                    "path_length": network._path_total_length(case_state, path),
                    "evacuation_time": metrics["time"],
                    "queueing_time": metrics["queueing_time"],
                    "congestion_exposure_time": metrics["congestion_exposure_time"],
                    "avg_speed": metrics["avg_speed"],
                }
            )
    return pd.DataFrame(rows)


def score_long_results(long_df: pd.DataFrame) -> dict[str, float]:
    wide = long_df.pivot_table(
        index=["case_id", "line", "origin", "start_role"],
        columns="method",
        values=[
            "target_exit",
            "path",
            "path_length",
            "evacuation_time",
            "queueing_time",
            "congestion_exposure_time",
            "avg_speed",
        ],
        aggfunc="first",
    )
    wide.columns = [f"{metric}_{method}" for metric, method in wide.columns]
    wide = wide.reset_index()

    if "evacuation_time_AdaptiveQueueAwareAStar" not in wide or "evacuation_time_PaperImprovedAStar" not in wide:
        return {
            "mean_score": 0.0,
            "max_time_delta": 0.0,
            "max_queue_delta": 0.0,
            "max_exposure_delta": 0.0,
            "path_change_count": 0.0,
        }

    dt = wide["evacuation_time_AdaptiveQueueAwareAStar"].astype(float) - wide[
        "evacuation_time_PaperImprovedAStar"
    ].astype(float)
    dq = wide["queueing_time_AdaptiveQueueAwareAStar"].astype(float) - wide[
        "queueing_time_PaperImprovedAStar"
    ].astype(float)
    de = wide["congestion_exposure_time_AdaptiveQueueAwareAStar"].astype(float) - wide[
        "congestion_exposure_time_PaperImprovedAStar"
    ].astype(float)
    path_changed = (
        wide["path_AdaptiveQueueAwareAStar"].astype(str) != wide["path_PaperImprovedAStar"].astype(str)
    )
    score = dt.abs() + dq.abs() / 80.0 + de.abs() / 80.0 + path_changed.astype(int) * 8.0
    return {
        "mean_score": float(score.mean()),
        "max_time_delta": float(dt.abs().max()),
        "max_queue_delta": float(dq.abs().max()),
        "max_exposure_delta": float(de.abs().max()),
        "path_change_count": float(path_changed.sum()),
    }


def plot_failure_results(long_df: pd.DataFrame, out_file: Path) -> None:
    case_order = list(dict.fromkeys(long_df["case_id"].tolist()))
    method_order = ["PaperImprovedAStar", "AdaptiveQueueAwareAStar"]
    pivots = [
        (long_df.pivot(index="case_id", columns="method", values="evacuation_time"), "疏散时间 (s)"),
        (long_df.pivot(index="case_id", columns="method", values="queueing_time"), "排队时间 (person*s)"),
        (
            long_df.pivot(index="case_id", columns="method", values="congestion_exposure_time"),
            "拥挤暴露 (person*s)",
        ),
    ]
    colors = ["#4E79A7", "#59A14F", "#F28E2B"]
    fig, axes = plt.subplots(3, 1, figsize=(15, 13), sharex=True)
    x = np.arange(len(case_order))
    width = 0.24
    for ax, (pivot, ylabel) in zip(axes, pivots):
        pivot = pivot.reindex(case_order)
        for idx, method in enumerate(method_order):
            vals = pivot[method].to_numpy(dtype=float)
            ax.bar(
                x + (idx - 1) * width,
                vals,
                width=width,
                label=method,
                color=colors[idx],
                edgecolor="black",
            )
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle="--", alpha=0.45)
    axes[0].legend()
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(case_order, rotation=25, ha="right")
    fig.suptitle("逐线筛选后的设施失效单路径对比", fontsize=16, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    G = network.build_graph()
    selected = pd.read_csv(ROOT / "32_selected_top4_single_path_cases.csv")
    selected_long = pd.read_csv(ROOT / "33_selected_top4_single_path_results.csv")
    cases_by_line = {}
    for line in LINES:
        line_rows = selected[selected["line"] == line]
        cases_by_line[line] = [
            {
                "case_id": f"{line}_D{idx}",
                "line": row.line,
                "origin": row.origin,
                "start_role": row.start_role,
            }
            for idx, row in enumerate(line_rows.itertuples(), start=1)
        ]

    failure_rows = []
    for line in LINES:
        facilities = failure_facilities(G, line, selected_long)
        print(line, "failure candidates:", len(facilities), facilities)
        for facility in facilities:
            H = apply_node_failure(G, facility)
            if not all_cases_still_reachable(H, line, cases_by_line[line]):
                continue
            try:
                long_df = run_cases(H, cases_by_line[line], methods=SCREEN_METHODS)
            except Exception:
                continue
            score = score_long_results(long_df)
            failure_rows.append(
                {
                    "line": line,
                    "failed_node": facility,
                    "failed_type": G.nodes[facility].get("type", ""),
                    **score,
                }
            )

    failure_df = pd.DataFrame(failure_rows).sort_values(
        ["line", "mean_score"], ascending=[True, False]
    )
    failure_df.to_csv(ROOT / "37_failure_candidate_scored.csv", index=False, encoding="utf-8-sig")

    selected_failures = failure_df.groupby("line", as_index=False).head(1)
    selected_failures.to_csv(ROOT / "38_selected_failure_by_line.csv", index=False, encoding="utf-8-sig")

    final_rows = []
    for row in selected_failures.itertuples():
        H = apply_node_failure(G, row.failed_node)
        long_df = run_cases(H, cases_by_line[row.line], methods=METHODS)
        long_df["failed_node"] = row.failed_node
        long_df["failed_type"] = row.failed_type
        final_rows.append(long_df)
    final_df = pd.concat(final_rows, ignore_index=True)
    final_df.to_csv(ROOT / "39_selected_failure_single_path_results.csv", index=False, encoding="utf-8-sig")
    plot_failure_results(final_df, ROOT / "40_selected_failure_single_path_metrics.png")

    print("selected failures:")
    print(selected_failures.to_string(index=False))


if __name__ == "__main__":
    main()
