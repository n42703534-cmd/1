from __future__ import annotations

import copy
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from matplotlib.lines import Line2D

import network as nw


OUT_DIR = Path(".")
L2_CASE_SPECS = [spec for spec in nw.SINGLE_PATH_CASE_SPECS if spec["line"] == "L2"]
REP_CASE_ID = "L2_C1"
DISRUPTION_NODE = "Escalator_L2_up1"

METHOD_SPECS = [
    (nw.PAPER_SINGLE_PATH_METHOD, "Paper Improved A*", "#F28E2B", "dashdot"),
    (nw.OUR_SINGLE_PATH_METHOD, "Adaptive Single-Next-Hop Guidance", "#1F77B4", "solid"),
]


def _draw_route_panel(ax, G_plot, path, title, color, linestyle, label):
    pos = nx.get_node_attributes(G_plot, "pos")

    nx.draw_networkx_edges(
        G_plot,
        pos,
        ax=ax,
        edge_color="#D0D0D0",
        width=1.0,
        alpha=0.35,
        arrows=True,
    )
    nx.draw_networkx_nodes(
        G_plot,
        pos,
        ax=ax,
        node_color="#ECECEC",
        node_size=220,
        edgecolors="black",
        linewidths=0.45,
    )

    if path and len(path) > 1:
        edges = list(zip(path, path[1:]))
        nx.draw_networkx_edges(
            G_plot,
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
    source_node = path[0] if path else None
    target_node = path[-1] if path else None
    if source_node is not None:
        labels[source_node] = source_node.replace("Platform_", "").replace("Gate_", "").replace("Exit_", "")
    if target_node is not None and target_node != source_node:
        labels[target_node] = target_node.replace("Platform_", "").replace("Gate_", "").replace("Exit_", "")
    nx.draw_networkx_labels(G_plot, pos, labels=labels, ax=ax, font_size=7, font_weight="bold")

    ax.set_title(title, fontweight="bold", fontsize=12)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    return Line2D([0], [0], color=color, lw=3.2, linestyle=linestyle, label=label)


def make_route_comparison_figure(G_plot, case_state, case_spec, output_file, title_prefix):
    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(case_state, weight="length"))
    paths = {}
    for method, label, color, linestyle in METHOD_SPECS:
        paths[label] = nw.get_best_path_to_exit(case_state, case_spec["origin"], method, shortest_dists)

    fig, axes = plt.subplots(1, len(METHOD_SPECS), figsize=(8 * len(METHOD_SPECS), 8))
    handles = []
    for ax, (_, label, color, linestyle) in zip(axes, METHOD_SPECS):
        handle = _draw_route_panel(
            ax,
            G_plot,
            paths[label],
            f"{case_spec['case_id']} | {label}",
            color,
            linestyle,
            label,
        )
        handles.append(handle)

    fig.suptitle(
        f"{title_prefix} | Start: {case_spec['origin']} | Group size: 100",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )
    fig.legend(handles=handles, loc="lower center", ncol=len(METHOD_SPECS), frameon=False)
    plt.tight_layout(rect=[0, 0.06, 1, 0.95])
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return paths


def evaluate_case_state(case_state, case_spec, label):
    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(case_state, weight="length"))
    rows = []
    paths = {}

    for method, method_label, _, _ in METHOD_SPECS:
        path = nw.get_best_path_to_exit(case_state, case_spec["origin"], method, shortest_dists)
        metrics = nw.run_simulation_for_existing_state(
            case_state,
            method=method,
            target_by_line={case_spec["line"]: 100.0},
        )

        paths[method_label] = path
        rows.append(
            {
                "scenario": label,
                "case_id": case_spec["case_id"],
                "line": case_spec["line"],
                "origin": case_spec["origin"],
                "method": method,
                "method_label": method_label,
                "path": nw.format_path(path),
                "target_exit": path[-1] if path else None,
                "path_length": nw._path_total_length(case_state, path) if path else 0.0,
                "evacuation_time": float(metrics.get("time", 0.0)),
                "queueing_time": float(metrics.get("queueing_time", 0.0)),
                "congestion_exposure_time": float(metrics.get("congestion_exposure_time", 0.0)),
                "avg_speed": float(metrics.get("avg_speed", 0.0)),
            }
        )

    return pd.DataFrame(rows), paths


def _summarize_case_rows(df):
    rows = []
    for method_label, group in df.groupby("method_label", sort=False):
        rows.append(
            {
                "method_label": method_label,
                "path": group.iloc[0]["path"],
                "target_exit": group.iloc[0]["target_exit"],
                "path_length": float(group.iloc[0]["path_length"]),
                "evacuation_time": float(group.iloc[0]["evacuation_time"]),
                "queueing_time": float(group.iloc[0]["queueing_time"]),
                "congestion_exposure_time": float(group.iloc[0]["congestion_exposure_time"]),
                "avg_speed": float(group.iloc[0]["avg_speed"]),
            }
        )
    return pd.DataFrame(rows)


def run_l2_complete_study():
    G = nw.build_graph()

    # 1) Normal L2 benchmark with 4 representative starts
    long_df, wide_df, summary_df = nw.run_single_path_case_suite(
        G,
        case_specs=L2_CASE_SPECS,
        long_csv="15_L2_single_path_case_results.csv",
        wide_csv="16_L2_single_path_case_comparison.csv",
        summary_csv="17_L2_single_path_case_summary.csv",
        plot_file="18_L2_single_path_case_metrics.png",
    )

    rep_case = next(spec for spec in L2_CASE_SPECS if spec["case_id"] == REP_CASE_ID)

    rep_case_state = nw.build_single_path_case_state(G, rep_case)
    normal_paths = make_route_comparison_figure(
        G,
        rep_case_state,
        rep_case,
        OUT_DIR / "19_L2_C1_route_comparison_normal.png",
        "L2 normal route comparison",
    )

    normal_case_df, _ = evaluate_case_state(rep_case_state, rep_case, "normal")
    normal_case_df.to_csv("20_L2_C1_normal_results.csv", index=False, encoding="utf-8-sig")

    # 2) Disruption study: Escalator_L2_up1 is blocked
    disrupted_case_state = nw.build_single_path_case_state(G, rep_case)
    if DISRUPTION_NODE not in disrupted_case_state.nodes:
        raise ValueError(f"Disruption node {DISRUPTION_NODE} not found in graph.")
    nw._apply_node_disruption(disrupted_case_state, DISRUPTION_NODE, factor=0.0)

    disrupted_paths = make_route_comparison_figure(
        disrupted_case_state,
        disrupted_case_state,
        rep_case,
        OUT_DIR / "21_L2_C1_route_comparison_disrupted.png",
        f"L2 disrupted route comparison ({DISRUPTION_NODE} blocked)",
    )

    disrupted_case_df, _ = evaluate_case_state(disrupted_case_state, rep_case, "disrupted")
    disrupted_case_df.to_csv("22_L2_C1_disruption_results.csv", index=False, encoding="utf-8-sig")

    combined_case_df = pd.concat([normal_case_df, disrupted_case_df], ignore_index=True)
    combined_case_df.to_csv("23_L2_C1_normal_vs_disrupted.csv", index=False, encoding="utf-8-sig")

    combined_summary = _summarize_case_rows(combined_case_df)
    combined_summary.to_csv("24_L2_C1_summary_table.csv", index=False, encoding="utf-8-sig")

    # 3) Human-readable summary for the paper draft
    normal_method = normal_case_df.set_index("method_label")
    disrupted_method = disrupted_case_df.set_index("method_label")
    lines = [
        "L2 complete process summary",
        "",
        "1. L2 benchmark setup",
        f"- Four representative starts: {', '.join(spec['origin'] for spec in L2_CASE_SPECS)}",
        "- Two methods compared: Paper Improved A*, Adaptive Single-Next-Hop Guidance",
        "- Population per case: 100",
        "",
        "2. L2_C1 representative case",
        f"- Normal best path (Adaptive Single-Next-Hop Guidance): {normal_method.loc['Adaptive Single-Next-Hop Guidance', 'path']}",
        f"- Normal evacuation time (Adaptive Single-Next-Hop Guidance): {normal_method.loc['Adaptive Single-Next-Hop Guidance', 'evacuation_time']:.1f} s",
        f"- Paper Improved A* path: {normal_method.loc['Paper Improved A*', 'path']}",
        f"- Paper Improved A* evacuation time: {normal_method.loc['Paper Improved A*', 'evacuation_time']:.1f} s",
        "",
        "3. Disruption study",
        f"- Blocked facility: {DISRUPTION_NODE}",
        f"- Disrupted best path (Adaptive Single-Next-Hop Guidance): {disrupted_method.loc['Adaptive Single-Next-Hop Guidance', 'path']}",
        f"- Disrupted evacuation time (Adaptive Single-Next-Hop Guidance): {disrupted_method.loc['Adaptive Single-Next-Hop Guidance', 'evacuation_time']:.1f} s",
        f"- Disrupted Paper Improved A* evacuation time: {disrupted_method.loc['Paper Improved A*', 'evacuation_time']:.1f} s",
        "",
        "4. Normal benchmark summary",
        summary_df.to_string(index=False),
    ]
    Path("25_L2_complete_process_summary.txt").write_text("\n".join(lines), encoding="utf-8")

    print(f"Normal L2 suite: {len(long_df)} rows, {len(wide_df)} cases")
    print(summary_df.to_string(index=False))
    print("\nL2_C1 normal routes:")
    for label, path in normal_paths.items():
        print(f"- {label}: {nw.format_path(path)}")
    print("\nL2_C1 disrupted routes:")
    for label, path in disrupted_paths.items():
        print(f"- {label}: {nw.format_path(path)}")
    print("\nL2_C1 normal vs disrupted results:")
    print(combined_summary.to_string(index=False))


if __name__ == "__main__":
    run_l2_complete_study()
