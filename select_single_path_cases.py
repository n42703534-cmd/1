from __future__ import annotations

import copy
from pathlib import Path

import networkx as nx
import pandas as pd

import network


ROOT = Path(__file__).resolve().parent
LINES = ["L2", "L7", "L18"]
METHODS = (
    network.PAPER_SINGLE_PATH_METHOD,
    network.OUR_SINGLE_PATH_METHOD,
)
SCREEN_METHODS = (
    network.PAPER_SINGLE_PATH_METHOD,
    network.OUR_SINGLE_PATH_METHOD,
)


def belongs_to_line(node: str, line: str) -> bool:
    return (
        node == f"Platform_{line}"
        or node.startswith(f"{line}_")
        or node.startswith(f"Gate_{line}_")
        or node.startswith(f"Stair_{line}_")
        or node.startswith(f"Escalator_{line}_")
        or node.startswith(f"VN_{line}_")
        or f"_{line}_" in node
    )


def line_exits(G: nx.DiGraph, line: str) -> list[str]:
    return [
        n
        for n, data in G.nodes(data=True)
        if data.get("type") == "exit" and belongs_to_line(n, line)
    ]


def candidate_origins(G: nx.DiGraph, line: str) -> list[dict[str, str]]:
    exits = line_exits(G, line)
    rows = []
    for node, data in G.nodes(data=True):
        node_type = data.get("type", "")
        if node_type in {"exit", "train", "train_car"} or node.startswith("Train_"):
            continue
        if not belongs_to_line(node, line):
            continue
        if G.out_degree(node) <= 0:
            continue
        if not any(nx.has_path(G, node, exit_node) for exit_node in exits):
            continue
        rows.append(
            {
                "case_id": f"{line}_ALL_{len(rows) + 1:02d}",
                "line": line,
                "origin": node,
                "start_role": node_type or "unknown",
            }
        )
    return rows


def add_selection_scores(wide_df: pd.DataFrame) -> pd.DataFrame:
    df = wide_df.copy()

    def diff(metric: str, baseline: str) -> pd.Series:
        return df[f"{metric}_AdaptiveQueueAwareAStar"].astype(float) - df[f"{metric}_{baseline}"].astype(float)

    baselines = [
        baseline
        for baseline in ["PaperImprovedAStar"]
        if f"evacuation_time_{baseline}" in df.columns
    ]
    for baseline in baselines:
        df[f"delta_time_vs_{baseline}"] = diff("evacuation_time", baseline)
        df[f"delta_queue_vs_{baseline}"] = diff("queueing_time", baseline)
        df[f"delta_exposure_vs_{baseline}"] = diff("congestion_exposure_time", baseline)
        df[f"delta_path_vs_{baseline}"] = diff("path_length", baseline)
        df[f"exit_changed_vs_{baseline}"] = (
            df["target_exit_AdaptiveQueueAwareAStar"].astype(str) != df[f"target_exit_{baseline}"].astype(str)
        )
        df[f"path_changed_vs_{baseline}"] = (
            df["path_AdaptiveQueueAwareAStar"].astype(str) != df[f"path_{baseline}"].astype(str)
        )

    score = pd.Series(0.0, index=df.index)
    for baseline in baselines:
        score += df[f"delta_time_vs_{baseline}"].abs()
        score += df[f"delta_queue_vs_{baseline}"].abs() / 80.0
        score += df[f"delta_exposure_vs_{baseline}"].abs() / 80.0
        score += df[f"delta_path_vs_{baseline}"].abs() * 0.5
        score += df[f"exit_changed_vs_{baseline}"].astype(int) * 20.0
        score += df[f"path_changed_vs_{baseline}"].astype(int) * 8.0
    df["selection_score"] = score
    return df.sort_values(["line", "selection_score"], ascending=[True, False])


def select_top_four(scored_df: pd.DataFrame) -> pd.DataFrame:
    selected = []
    for line in LINES:
        line_df = scored_df[scored_df["line"] == line].copy()
        selected.append(line_df.head(4))
    return pd.concat(selected, ignore_index=True)


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


def failure_candidates(G: nx.DiGraph, selected_cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for line in LINES:
        cases = [
            {
                "case_id": row.case_id,
                "line": row.line,
                "origin": row.origin,
                "start_role": row.start_role,
            }
            for row in selected_cases[selected_cases["line"] == line].itertuples()
        ]
        facilities = [
            n
            for n, data in G.nodes(data=True)
            if belongs_to_line(n, line)
            and data.get("type") in {"stair", "escalator", "gate_wide", "gate_tripod", "virtual"}
            and G.in_degree(n) > 0
            and G.out_degree(n) > 0
        ]
        for facility in facilities:
            H = apply_node_failure(G, facility)
            try:
                long_df, wide_df, _ = network.run_single_path_case_suite(
                    H,
                    case_specs=cases,
                    methods=METHODS,
                    long_csv=ROOT / f"32_failure_probe_{line}_{facility}_long.csv",
                    wide_csv=ROOT / f"32_failure_probe_{line}_{facility}_wide.csv",
                    summary_csv=ROOT / f"32_failure_probe_{line}_{facility}_summary.csv",
                    plot_file=ROOT / f"32_failure_probe_{line}_{facility}.png",
                )
            except Exception:
                continue
            scored = add_selection_scores(wide_df)
            rows.append(
                {
                    "line": line,
                    "failed_node": facility,
                    "failed_type": G.nodes[facility].get("type", ""),
                    "mean_selection_score": scored["selection_score"].mean(),
                    "max_abs_time_delta_vs_paper": scored["delta_time_vs_PaperImprovedAStar"].abs().max(),
                    "max_abs_queue_delta_vs_paper": scored["delta_queue_vs_PaperImprovedAStar"].abs().max(),
                    "max_abs_exposure_delta_vs_paper": scored[
                        "delta_exposure_vs_PaperImprovedAStar"
                    ].abs().max(),
                }
            )
    return pd.DataFrame(rows).sort_values(["line", "mean_selection_score"], ascending=[True, False])


def main() -> None:
    G = network.build_graph()
    all_cases = []
    for line in LINES:
        all_cases.extend(candidate_origins(G, line))

    pd.DataFrame(all_cases).to_csv(ROOT / "30_all_candidate_origins.csv", index=False, encoding="utf-8-sig")
    # 第一阶段和最终阶段均使用同一组 Paper vs Adaptive 方法。
    long_df, wide_df, summary_df = network.run_single_path_case_suite(
        G,
        case_specs=all_cases,
        methods=SCREEN_METHODS,
        long_csv=ROOT / "30_all_candidate_single_path_results.csv",
        wide_csv=ROOT / "31_all_candidate_single_path_comparison.csv",
        summary_csv=ROOT / "31_all_candidate_single_path_summary.csv",
        plot_file=ROOT / "31_all_candidate_single_path_metrics.png",
    )

    scored_df = add_selection_scores(wide_df)
    selected_df = select_top_four(scored_df)

    scored_df.to_csv(ROOT / "31_all_candidate_single_path_scored.csv", index=False, encoding="utf-8-sig")
    selected_df.to_csv(ROOT / "32_selected_top4_single_path_cases.csv", index=False, encoding="utf-8-sig")

    selected_cases = []
    for line in LINES:
        line_selected = selected_df[selected_df["line"] == line]
        for idx, row in enumerate(line_selected.itertuples(), start=1):
            selected_cases.append(
                {
                    "case_id": f"{line}_C{idx}",
                    "line": row.line,
                    "origin": row.origin,
                    "start_role": row.start_role,
                }
            )
    network.run_single_path_case_suite(
        G,
        case_specs=selected_cases,
        methods=METHODS,
        long_csv=ROOT / "33_selected_top4_single_path_results.csv",
        wide_csv=ROOT / "34_selected_top4_single_path_comparison.csv",
        summary_csv=ROOT / "35_selected_top4_single_path_summary.csv",
        plot_file=ROOT / "36_selected_top4_single_path_metrics.png",
    )

    print("candidate origins:", len(all_cases))
    print(pd.DataFrame(all_cases).groupby("line").size().to_string())
    print("\nselected top4:")
    print(
        selected_df[
            [
                "line",
                "origin",
                "start_role",
                "selection_score",
                "delta_time_vs_PaperImprovedAStar",
                "delta_queue_vs_PaperImprovedAStar",
                "delta_exposure_vs_PaperImprovedAStar",
                "path_changed_vs_PaperImprovedAStar",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
