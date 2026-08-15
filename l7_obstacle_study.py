from __future__ import annotations

import copy
from contextlib import contextmanager
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

import lines_config as lc
import network as nw


OUT_DIR = Path(".")
L7_CASE_SPECS = [spec for spec in nw.SINGLE_PATH_CASE_SPECS if spec["line"] == "L7"]
REP_CASE = next(spec for spec in L7_CASE_SPECS if spec["case_id"] == "L7_C1")

METHOD_SPECS = [
    (nw.PAPER_SINGLE_PATH_METHOD, "Paper Improved A*", "#F28E2B", "dashdot"),
    (nw.OUR_SINGLE_PATH_METHOD, "Adaptive Single-Next-Hop Guidance", "#1F77B4", "solid"),
]


@contextmanager
def obstacle_mode(enabled: bool):
    original_nw = copy.deepcopy(nw.OBSTACLE_AREAS)
    original_lc = copy.deepcopy(lc.OBSTACLE_AREAS)
    try:
        if not enabled:
            empty = {"nodes": {}, "edges": {}}
            nw.OBSTACLE_AREAS = empty
            lc.OBSTACLE_AREAS = empty
        yield
    finally:
        nw.OBSTACLE_AREAS = original_nw
        lc.OBSTACLE_AREAS = original_lc


def _draw_route_panel(ax, G_base, path, title, color, linestyle, label):
    pos = nx.get_node_attributes(G_base, "pos")
    nx.draw_networkx_edges(G_base, pos, ax=ax, edge_color="#D0D0D0", width=1.0, alpha=0.35, arrows=True)
    nx.draw_networkx_nodes(
        G_base, pos, ax=ax, node_color="#ECECEC", node_size=220, edgecolors="black", linewidths=0.45
    )

    if path and len(path) > 1:
        edges = list(zip(path, path[1:]))
        nx.draw_networkx_edges(
            G_base,
            pos,
            ax=ax,
            edgelist=edges,
            edge_color=color,
            width=3.2,
            style=linestyle,
            arrows=True,
        )

    if path:
        xs = [pos[n][0] for n in path if n in pos]
        ys = [pos[n][1] for n in path if n in pos]
        if xs and ys:
            pad_x = max((max(xs) - min(xs)) * 0.35, 8.0)
            pad_y = max((max(ys) - min(ys)) * 0.35, 8.0)
            ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
            ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)

    labels = {}
    if path:
        source_node = path[0]
        target_node = path[-1]
        labels[source_node] = source_node.replace("Platform_", "").replace("Gate_", "").replace("Exit_", "")
        if target_node != source_node:
            labels[target_node] = target_node.replace("Platform_", "").replace("Gate_", "").replace("Exit_", "")
    nx.draw_networkx_labels(G_base, pos, labels=labels, ax=ax, font_size=7, font_weight="bold")

    ax.set_title(title, fontweight="bold", fontsize=12)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")


def make_route_figure(G_base, case_spec, output_file):
    case_state = nw.build_single_path_case_state(G_base, case_spec)
    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(case_state, weight="length"))

    fig, axes = plt.subplots(1, len(METHOD_SPECS), figsize=(8 * len(METHOD_SPECS), 8))
    for ax, (method, label, color, linestyle) in zip(axes, METHOD_SPECS):
        path = nw.get_best_path_to_exit(case_state, case_spec["origin"], method, shortest_dists)
        _draw_route_panel(ax, G_base, path, f"{case_spec['case_id']} | {label}", color, linestyle, label)

    fig.suptitle(f"L7 representative case | Start: {case_spec['origin']} | Group size: 100", fontsize=16, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.02, 1, 0.95])
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(fig)


def run_suite(obstacle_enabled: bool, prefix: str):
    with obstacle_mode(obstacle_enabled):
        G = nw.build_graph()
        long_df, wide_df, summary_df = nw.run_single_path_case_suite(
            G,
            case_specs=L7_CASE_SPECS,
            long_csv=f"{prefix}_L7_single_path_case_results.csv",
            wide_csv=f"{prefix}_L7_single_path_case_comparison.csv",
            summary_csv=f"{prefix}_L7_single_path_case_summary.csv",
            plot_file=f"{prefix}_L7_single_path_case_metrics.png",
        )
        make_route_figure(G, REP_CASE, OUT_DIR / f"{prefix}_L7_C1_route_comparison.png")
        return long_df, wide_df, summary_df


def run_l7_obstacle_study():
    base_long, base_wide, base_summary = run_suite(False, "15_L7_no_obstacle")
    obs_long, obs_wide, obs_summary = run_suite(True, "20_L7_with_obstacle")

    delta = obs_summary.merge(
        base_summary,
        on=["line", "method", "method_label", "case_count"],
        suffixes=("_obs", "_base"),
    )
    delta["delta_mean_evacuation_time"] = delta["mean_evacuation_time_obs"] - delta["mean_evacuation_time_base"]
    delta["delta_mean_path_length"] = delta["mean_path_length_obs"] - delta["mean_path_length_base"]
    delta["delta_mean_queueing_time"] = delta["mean_queueing_time_obs"] - delta["mean_queueing_time_base"]
    delta["delta_mean_congestion_exposure"] = delta["mean_congestion_exposure_obs"] - delta["mean_congestion_exposure_base"]
    delta.to_csv("25_L7_obstacle_delta_summary.csv", index=False, encoding="utf-8-sig")

    print("Baseline L7 summary:")
    print(base_summary.to_string(index=False))
    print("\nObstacle L7 summary:")
    print(obs_summary.to_string(index=False))
    print("\nDelta summary:")
    print(delta[[
        "line",
        "method_label",
        "delta_mean_path_length",
        "delta_mean_evacuation_time",
        "delta_mean_queueing_time",
        "delta_mean_congestion_exposure",
    ]].to_string(index=False))


if __name__ == "__main__":
    run_l7_obstacle_study()
