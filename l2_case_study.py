from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

import network as nw


OUT_DIR = Path(".")
L2_CASE_SPECS = [spec for spec in nw.SINGLE_PATH_CASE_SPECS if spec["line"] == "L2"]


def _draw_route_panel(ax, G_base, path, title, color, linestyle, label):
    pos = nx.get_node_attributes(G_base, "pos")

    nx.draw_networkx_edges(
        G_base,
        pos,
        ax=ax,
        edge_color="#D0D0D0",
        width=1.0,
        alpha=0.35,
        arrows=True,
    )
    nx.draw_networkx_nodes(
        G_base,
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
    source_node = path[0] if path else None
    target_node = path[-1] if path else None
    if source_node is not None:
        labels[source_node] = source_node.replace("Platform_", "").replace("Gate_", "").replace("Exit_", "")
    if target_node is not None and target_node != source_node:
        labels[target_node] = target_node.replace("Platform_", "").replace("Gate_", "").replace("Exit_", "")
    nx.draw_networkx_labels(G_base, pos, labels=labels, ax=ax, font_size=7, font_weight="bold")

    ax.set_title(title, fontweight="bold", fontsize=12)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    return Line2D([0], [0], color=color, lw=3.2, linestyle=linestyle, label=label)


def make_route_comparison_figure(G_base, case_spec, output_file):
    case_state = nw.build_single_path_case_state(G_base, case_spec)
    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(case_state, weight="length"))

    method_specs = [
        (nw.PAPER_SINGLE_PATH_METHOD, "Paper Improved A*", "#F28E2B", "dashdot"),
        (nw.OUR_SINGLE_PATH_METHOD, "Adaptive Single-Next-Hop Guidance", "#1F77B4", "solid"),
    ]

    paths = {}
    for method, label, color, linestyle in method_specs:
        paths[label] = nw.get_best_path_to_exit(case_state, case_spec["origin"], method, shortest_dists)

    fig, axes = plt.subplots(1, len(method_specs), figsize=(8 * len(method_specs), 8))
    handles = []
    for ax, (_, label, color, linestyle) in zip(axes, method_specs):
        handle = _draw_route_panel(
            ax,
            G_base,
            paths[label],
            f"{case_spec['case_id']} | {label}",
            color,
            linestyle,
            label,
        )
        handles.append(handle)

    fig.suptitle(
        f"L2 代表性起点路径对比 | 起点: {case_spec['origin']} | 每组 100 人",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )
    fig.legend(handles=handles, loc="lower center", ncol=len(method_specs), frameon=False)
    plt.tight_layout(rect=[0, 0.06, 1, 0.95])
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return paths


def run_l2_study():
    G = nw.build_graph()

    long_df, wide_df, summary_df = nw.run_single_path_case_suite(
        G,
        case_specs=L2_CASE_SPECS,
        long_csv="15_L2_single_path_case_results.csv",
        wide_csv="16_L2_single_path_case_comparison.csv",
        summary_csv="17_L2_single_path_case_summary.csv",
        plot_file="18_L2_single_path_case_metrics.png",
    )

    rep_case = next(spec for spec in L2_CASE_SPECS if spec["case_id"] == "L2_C1")
    paths = make_route_comparison_figure(
        G,
        rep_case,
        OUT_DIR / "19_L2_route_comparison_like_fig4.png",
    )

    print(f"已生成 L2 单路径结果: {len(long_df)} 条记录, {len(wide_df)} 个案例")
    print(summary_df.to_string(index=False))
    for label, path in paths.items():
        print(f"{label}: {nw.format_path(path)}")


if __name__ == "__main__":
    run_l2_study()
