from __future__ import annotations

import time
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

import network


ROOT = Path(__file__).resolve().parent
METHODS = (
    network.PAPER_SINGLE_PATH_METHOD,
    network.OUR_SINGLE_PATH_METHOD,
)
METHOD_LABELS = {
    network.PAPER_SINGLE_PATH_METHOD: "PaperImprovedAStar",
    network.OUR_SINGLE_PATH_METHOD: "AdaptiveQueueAwareAStar",
}


def main() -> None:
    G = network.build_graph()
    case_specs = [
        spec
        for spec in network.SINGLE_PATH_CASE_SPECS
        if spec["line"] in {"L2", "L7", "L18"}
    ]

    rows = []
    for case in case_specs:
        case_state = network.build_single_path_case_state(G, case)
        shortest_dists = dict(nx.all_pairs_dijkstra_path_length(case_state, weight="length"))
        for method in METHODS:
            start = time.perf_counter()
            path = network.get_best_path_to_exit(case_state, case["origin"], method, shortest_dists)
            elapsed = time.perf_counter() - start
            rows.append(
                {
                    "case_id": case["case_id"],
                    "line": case["line"],
                    "origin": case["origin"],
                    "method": METHOD_LABELS[method],
                    "target_exit": path[-1] if path else None,
                    "path_length": network._path_total_length(case_state, path),
                    "planning_time_s": elapsed,
                    "path": network.format_path(path),
                }
            )

    df = pd.DataFrame(rows)
    out_csv = ROOT / "57_planning_methods_like_bjut_results.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    summary = (
        df.groupby(["line", "method"])
        .agg(
            case_count=("case_id", "count"),
            mean_path_length=("path_length", "mean"),
            mean_planning_time_s=("planning_time_s", "mean"),
            max_planning_time_s=("planning_time_s", "max"),
        )
        .reset_index()
    )
    out_summary = ROOT / "58_planning_methods_like_bjut_summary.csv"
    summary.to_csv(out_summary, index=False, encoding="utf-8-sig")

    lines = ["L2", "L7", "L18"]
    methods = [METHOD_LABELS[m] for m in METHODS]
    colors = {
        "PaperImprovedAStar": "#4E79A7",
        "AdaptiveQueueAwareAStar": "#F28E2B",
    }
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), dpi=220)
    width = 0.24
    x = range(len(lines))
    for idx, method in enumerate(methods):
        line_rows = summary[summary["method"] == method]
        vals_len = [
            float(line_rows[line_rows["line"] == line]["mean_path_length"].iloc[0])
            for line in lines
        ]
        vals_time = [
            float(line_rows[line_rows["line"] == line]["mean_planning_time_s"].iloc[0])
            for line in lines
        ]
        pos = [i + (idx - 1) * width for i in x]
        axes[0].bar(pos, vals_len, width=width, label=method, color=colors[method], edgecolor="black")
        axes[1].bar(pos, vals_time, width=width, label=method, color=colors[method], edgecolor="black")

    axes[0].set_title("平均规划路径长度")
    axes[0].set_ylabel("Path length (m)")
    axes[1].set_title("平均路径规划计算时间")
    axes[1].set_ylabel("Planning time (s)")
    for ax in axes:
        ax.set_xticks(list(x))
        ax.set_xticklabels(lines)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
    axes[1].legend()
    fig.suptitle("按 BJUT 文章口径的路径规划算法对比", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out_png = ROOT / "59_planning_methods_like_bjut.png"
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)

    print("Wrote", out_csv)
    print("Wrote", out_summary)
    print("Wrote", out_png)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
